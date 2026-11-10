"""The texts a command runs: the command itself, each quoted string and
substitution that may run, and each heredoc body a shell reads. And the
readers over them: the command a segment runs (cmd_index), the files it
writes, whether one command is alone in the call.
"""

import re

from . import lexer                            # lexer.Scan, so a stand-in for it reaches these calls too
from .quoting import strip_heredocs, _ASSIGN, _heredocs
from .lexicon import EXEC, GIT, LOOP, PROSE, SHELL, WRAP, _WRAP_VALUED
from .ladder import TooMany
from .git_calls import git_wrapper
from .lexer import seg_cmd


NESTED_CAP = 64


def _unq(t):
    return t.replace('"', "").replace("'", "")


def writes(b, heredoc_only):
    """The file paths `b` writes with a redirection or `tee`, heredoc bodies
    skipped; with heredoc_only, only those on a line that opens a heredoc --
    the paths whose content is the heredoc body. Quotes are stripped; a path
    built from $VAR comes back unresolved."""
    out, delim = [], ""
    for line in b.split("\n"):
        if delim:
            if re.fullmatch(r"[ \t]*" + re.escape(delim) + r"[ \t]*", line):
                delim = ""
            continue
        m = re.search(r"""<<-?[ \t]*["']?[A-Za-z_][A-Za-z0-9_]*["']?""", line)
        if m:
            delim = _unq(re.sub(r"^<<-?[ \t]*", "", m.group()))
            pre = line[:m.start()]
        else:
            pre = line
        if heredoc_only and not m:
            continue
        pre = re.sub(r"[;|&]", " ; ", pre)
        pre = re.sub(r">>?", " @redir@ ", pre)
        t = [x for x in re.split(r"[ \t]+", pre) if x != ""]
        teeing = False
        for x, tok in enumerate(t):
            if tok == ";":
                teeing = False
                continue
            if tok == "@redir@":
                if x + 1 < len(t) and t[x + 1] not in (";", "@redir@"):
                    out.append(_unq(t[x + 1]))
                continue
            if _unq(tok) == "tee":
                teeing = True
                continue
            if teeing and not tok.startswith("-"):
                out.append(_unq(tok))
    return out


def texts_of(text, prose=PROSE, read=None):
    """[(text, nested)]: the text itself plus, recursively, every quoted string
    in it that holds whitespace and may run. A segment's quoted strings are
    skipped only when it is led by a prose consumer, holds no executor, and no
    segment of its text is a shell. A command substitution inside double
    quotes runs whoever leads the segment, so its body is queued alone,
    heredocs stripped, even where the words around it are prose. `prose`
    widens the consumer set for a guard whose command names also appear as
    arguments (pkill -f). Past NESTED_CAP texts it raises TooMany rather
    than read some and pass the rest unread, so a pathological command can
    neither spin nor hide its last string. `read` scans each text, Scan when
    None: languette.document passes its own, which scans each text once."""
    out = [(text, False)]

    def add(t):
        if len(out) >= NESTED_CAP:
            raise TooMany(f"it holds more than {NESTED_CAP - 1} nested shell strings", "limit")
        out.append((t, True))
    x = 0
    while x < len(out):
        s = (read or lexer.Scan)(out[x][0])
        for a, b in s.segments():
            c = seg_cmd(s, a, b)
            ex = s.shellseg or any(s.k[j] == "w" and s.w[j] in EXEC for j in range(a, b + 1))
            if ex or c is None or s.w[c] not in prose:
                for j in range(a, b + 1):
                    if s.k[j] == "q":
                        add(s.q[j])
        for t in s.subs:
            add(strip_heredocs(t))
        x += 1
    return out


def _is_shell(word):
    return word.rsplit("/", 1)[-1] in SHELL


def shell_heredocs(text, scan=None):
    """[body] of the heredocs in `text` that a shell reads: the HEREDOC marker's
    segment, or one piped on from it, holds a shell word (sh, bash -s), or is
    an ssh whose quoted remote command holds one ('sudo bash -s'). Heredocs
    fed to anything else are data and stay dropped."""
    docs = _heredocs(text)[1]
    # a literal word HEREDOC in the command must not pass for a marker
    s = (scan or lexer.Scan)(_heredocs(re.sub(r"\bHEREDOC\b", "HEREDOC_", text))[0])
    out, k = [], 0
    for a, b in s.segments():
        e = b
        while e + 1 in s.pipes:
            e = next(y for x, y in s.segments() if x == e + 2)
        ssh = any(s.k[i] == "w" and s.w[i] == "ssh" for i in range(a, e + 1))
        shell = any((s.k[i] == "w" and _is_shell(s.w[i])) or (ssh and s.k[i] == "q" and any(map(_is_shell, re.split(r"[\s;&|()]+", s.q[i]))))
                    for i in range(a, e + 1))
        for j in range(a, b + 1):
            if s.k[j] == "w" and s.w[j] == "HEREDOC":
                if shell and k < len(docs):
                    out.append(docs[k][0])
                k += 1
    return out


def texts_of_command(text, prose=PROSE, read=None):
    """texts_of `text` with its heredocs stripped, then each heredoc body a
    shell reads queued as nested text, by the same rule (a heredoc inside it
    that a shell reads is queued too)."""
    out = texts_of(strip_heredocs(text), prose, read)
    for body in shell_heredocs(text, read):
        out += [(t, True) for t, _ in texts_of_command(body, prose, read)]
    return out


def _repo_word(s, a, i):
    """Whether the word at i is the repository name a wrapper such as vcsh takes after its own word."""
    return i > a and s.k[i - 1] == "w" and GIT.search(s.w[i - 1]) is not None and git_wrapper(s.w[i - 1])[1].repo


def cmd_index(s, a, b, cmd, nested, parents=None, prose=PROSE):
    """Index in a..b of the word that is the command `cmd` (a compiled regex)
    describes, or None. Top level: any word counts unless the word before it
    matches `parents` or is a wrapper's repository name, or the segment is led by a prose consumer and no segment
    is a shell. Nested: only the command position, past assignments, wrappers
    with their options, and shell keywords."""
    if not nested:
        c = seg_cmd(s, a, b)
        for i in range(a, b + 1):
            if (s.k[i] == "w" and cmd.search(s.w[i]) and
                    not (i > a and s.k[i - 1] == "w" and parents is not None and
                         (parents.search(s.w[i - 1]) or _repo_word(s, a, i - 1)))):
                return i
            if i == c and s.w[c] in prose and not s.shellseg:
                return None
        return None
    wrap, skip = None, False
    for i in range(a, b + 1):
        if s.k[i] != "w":
            return None
        if skip:                               # a wrapper option's value
            skip = False
            continue
        if cmd.search(s.w[i]):
            return i
        if _ASSIGN.match(s.w[i]):
            continue
        if s.w[i] in WRAP:
            wrap = s.w[i]
            continue
        if wrap and (s.w[i].startswith("-") or re.fullmatch(r"[0-9]+[smhd]?", s.w[i])):
            skip = s.w[i] in _WRAP_VALUED.get(wrap, ())
            continue
        return None
    return None


def segments(doc, prose=PROSE):
    """([(scan, a, b, nested)] for each non-empty segment of every text the
    command runs, whether any text holds a LOOP word): what a guard that spends
    one yes per run walks."""
    out, loop = [], False
    for t, nested in doc.texts(prose):
        s = doc.scan(t)
        loop = loop or any(k == "w" and w in LOOP for k, w in zip(s.k, s.w))
        out += [(s, a, b, nested) for a, b in s.segments() if a <= b]
    return out, loop


# Commands that may share the call with a gh that reads a file. None writes a
# byte to stdout that could become labels, so a redirect on one only
# truncates the file (pushd and popd print the directory stack).
INERT = frozenset("cd true :".split())


def alone(scans, cmd):
    """One segment is the command `cmd`, and every other is a shell running
    quoted text the scan already holds (not built at run time) or a command
    that writes no file."""
    ghs = 0
    for s, nested in scans:
        for a, b in s.segments():
            if a > b:
                continue
            if cmd_index(s, a, b, cmd, nested) is not None:
                ghs += 1                       # a second gh can download into the file
                if ghs > 1:
                    return False
                continue
            c = seg_cmd(s, a, b)
            w = s.w[c].rsplit("/", 1)[-1] if c is not None else None
            if w not in INERT and not (w in SHELL and runs_quoted(s, c, b, w)):
                return False
    return True


def runs_quoted(s, c, b, w):
    """The shell at c runs only quoted text the scan holds: `eval` whose every
    operand is quoted, or `sh … -c SCRIPT` whose operand to -c is quoted and
    no other word before it is an operand (a script file the scan never
    reads). `source` and `.` always run a file."""
    fixed = lambda j: s.k[j] == "q" and not s.live[j]
    if w == "eval":
        return c < b and all(fixed(j) for j in range(c + 1, b + 1))
    if w in ("source", "."):
        return False
    j = c + 1
    while j <= b:
        t = s.w[j] if s.k[j] == "w" else ""
        if t in ("-o", "+o", "-O", "+O"):
            j += 2
        elif t.startswith("--"):
            j += 1
        elif t[:1] in "-+" and len(t) > 1:
            if "c" in t:
                return j < b and fixed(j + 1)
            j += 1
        else:
            return False                       # an operand before -c: a script file
    return False
