"""Shell-text scanner: a port of hooks/lib-shell-words.awk, whose header is
the spec. Nothing here decides anything; it turns the Bash tool's command
string into words a guard judges, and every ambiguity resolves toward MORE
words reaching the guard, never fewer.

Indices are 0-based. A Scan holds parallel lists: w (word text), k ("w", "q"
or ";"), q (raw text of a quoted word holding whitespace, else ""), live (the
word carried a $ or backtick the shell would act on), and shellseg (some
segment is led by a shell, so `echo ... | sh` is executed text).

The parser ladder (docs/decisions.md, "Parser ladder") picks who reads the
text: a user-installed shfmt when it is on PATH and new enough, then a pip
parser (a slot, unruled: #4), then the awk port below. A real parser decides
where words and quotes begin and end; the awk lexer still shapes each piece,
so the tokens are the same contract whichever rung read them.
"""

import functools
import json
import re
import shutil
import subprocess

_DPART = r"""'[^'\n]*'|"[^"\n]*"|\\."""
_OPENER = re.compile(r"(?<!<)<<-?[ \t]*(?:[A-Za-z_]|" + _DPART + r")(?:[A-Za-z0-9_]|" + _DPART + r")*")
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_WS = re.compile(r"[ \t\n]")

PROSE = frozenset("grep egrep fgrep rg ag ack echo printf git yadm gh glab sed awk jq yq "
                  "cat tee test [ diff sort head tail wc tr cut less more".split())
EXEC = frozenset("sh bash zsh dash ksh ash busybox eval exec xargs su ssh sudo doas env nohup "
                 "timeout nice time watch parallel script chroot docker podman kubectl".split())
SHELL = frozenset("sh bash zsh dash ksh ash eval source .".split())
WRAP = frozenset("sudo env command exec time nice nohup timeout doas builtin "
                 "if then else elif while until do !".split())
NESTED_CAP = 64
_CASE = re.compile(r"(?<![A-Za-z0-9_])case(?![A-Za-z0-9_])")


def _sub_end(s, j):
    """Index just past the `)` closing a `$(` whose text starts at j, or len(s)
    when none does or the walk cannot be sure: a quote, backtick, backslash,
    `#` or `case` before the `)` sends it to the end, because a guard must not
    stake a bypass on out-guessing the shell's grammar."""
    L, depth = len(s), 1
    while j < L:
        c = s[j]
        if c in "\"'`\\#" or (c == "c" and _CASE.match(s, j)):
            return L
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if not depth:
                return j + 1
        j += 1
    return L


def _qclose(t):
    """The quote the scanner would still hold open at the end of t ("'", '"'
    or ""), read by its own rules: a backslash escapes outside single quotes,
    and a `#` comments to the end of its line only before a word has begun,
    so `a\\ #'` opens a quote and `a #'` does not."""
    L, i, have = len(t), 0, False
    while i < L:
        c = t[i]
        if c == "\\":
            if i + 1 < L and t[i + 1] != "\n":
                have = True
            i += 2
            continue
        if c == "'":
            have, e = True, t.find("'", i + 1)
            if e < 0:
                return "'"
            i = e + 1
            continue
        if c == '"':
            have, i = True, i + 1
            while i < L and t[i] != '"':
                i += 2 if t[i] == "\\" else 1
            if i >= L:
                return '"'
            i += 1
            continue
        if c == "#" and not have:
            e = t.find("\n", i)
            if e < 0:
                return ""
            i = e
            continue
        if c in " \t\n;|&()`<>":
            have = False
        elif c not in "{}" or have:
            have = True
        i += 1
    return ""


def heredoc_subs(s):
    """The $(...) and `...` command substitutions in an unquoted heredoc's body,
    each on a line of its own with any quote it leaves open closed (_qclose),
    so prose like `don't` cannot swallow the commands after the heredoc. A
    $(...) whose end _sub_end cannot be sure of keeps the rest of the body."""
    out, L, i = "", len(s), 0
    while i < L:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            j = i + 1
            while j < L and s[j] != "`":
                j += 2 if s[j] == "\\" else 1
            t = s[i:j + 1]
            out += "\n" + t + _qclose(t)
            i = j + 1
            continue
        if c == "$" and s[i + 1:i + 2] == "(":
            j = _sub_end(s, i + 2)
            t = s[i:j]
            out += "\n" + t + _qclose(t)
            i = j
            continue
        i += 1
    return out

# --- the parser ladder ---------------------------------------------------

# 3.6.0 has `--to-json` in the shape mvdan/sh#900 gave it; Ubuntu jammy's
# 3.4.3 has only `-tojson`, in the older shape.
SHFMT_MIN = (3, 6, 0)
SHFMT_TIMEOUT = 2                              # seconds; a parse measures ~6 ms
RUNGS = ("shfmt", "pip", "awk")                # tests narrow this to one rung


class Unparseable(Exception):
    """The parser read the command and refused it. Bad input is a deny, never a
    reason to try a weaker parser."""


@functools.lru_cache(maxsize=1)
def shfmt():
    """Path of a usable shfmt, or None: missing, too old, or no version."""
    path = shutil.which("shfmt")
    if not path:
        return None
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=SHFMT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout)
    return path if r.returncode == 0 and m and tuple(map(int, m.groups())) >= SHFMT_MIN else None


@functools.lru_cache(maxsize=256)
def _shfmt_tree(text):
    """shfmt's AST of `text`, or None when shfmt is missing or crashed. Raises
    Unparseable when shfmt reports a syntax error (exit 1, "line:col: why")."""
    path = shfmt()
    if not path:
        return None
    try:
        r = subprocess.run([path, "--to-json", "-ln=bash"], input=text.encode("utf-8", "surrogatepass"),
                           capture_output=True, timeout=SHFMT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode == 1 and re.match(r"(?:<standard input>:)?\d+:\d+: ", err):
        raise Unparseable(err.splitlines()[0])
    if r.returncode:
        return None
    try:
        tree = json.loads(r.stdout)
    except ValueError:
        return None
    return tree if isinstance(tree, dict) and tree.get("Type") == "File" else None


_pip_tree = None                               # rung two: a pip-installed parser, unruled (#4)


def parse(text):
    """(rung, tree) from the first rung on hand; the awk rung's tree is None.
    Raises Unparseable when a parser refuses the text."""
    for rung in RUNGS:
        if rung == "awk":
            return rung, None
        read = {"shfmt": _shfmt_tree, "pip": _pip_tree}[rung]
        tree = read(text) if read else None
        if tree is not None:
            return rung, tree
    raise RuntimeError(f"no parser rung read the text (rungs: {', '.join(RUNGS)})")


def check(command):
    """Raise Unparseable when the top rung refuses the command itself."""
    parse(command)


def _off(node, key="Pos"):
    return node[key]["Offset"]


def _words(node, out):
    """Every Word under node, not descending into one: shfmt's typed JSON
    writes no Type on a Word, since its field is never an interface. A
    heredoc body is left to the awk lexer, as the awk rung reads it."""
    if isinstance(node, dict):
        if "Parts" in node and node.get("Type", "Word") == "Word":
            out.append(node)
            return
        for key, v in node.items():
            if key != "Hdoc":
                _words(v, out)
    elif isinstance(node, list):
        for v in node:
            _words(v, out)

# --- the parser ladder ---------------------------------------------------

# 3.6.0 has `--to-json` in the shape mvdan/sh#900 gave it; Ubuntu jammy's
# 3.4.3 has only `-tojson`, in the older shape.
SHFMT_MIN = (3, 6, 0)
SHFMT_TIMEOUT = 2                              # seconds; a parse measures ~6 ms
RUNGS = ("shfmt", "pip", "awk")                # tests narrow this to one rung


class Unparseable(Exception):
    """The parser read the command and refused it. Bad input is a deny, never a
    reason to try a weaker parser."""


@functools.lru_cache(maxsize=1)
def shfmt():
    """Path of a usable shfmt, or None: missing, too old, or no version."""
    path = shutil.which("shfmt")
    if not path:
        return None
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=SHFMT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout)
    return path if r.returncode == 0 and m and tuple(map(int, m.groups())) >= SHFMT_MIN else None


@functools.lru_cache(maxsize=256)
def _shfmt_tree(text):
    """shfmt's AST of `text`, or None when shfmt is missing or crashed. Raises
    Unparseable when shfmt reports a syntax error (exit 1, "line:col: why")."""
    path = shfmt()
    if not path:
        return None
    try:
        r = subprocess.run([path, "--to-json", "-ln=bash"], input=text.encode("utf-8", "surrogatepass"),
                           capture_output=True, timeout=SHFMT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode == 1 and re.match(r"(?:<standard input>:)?\d+:\d+: ", err):
        raise Unparseable(err.splitlines()[0])
    if r.returncode:
        return None
    try:
        tree = json.loads(r.stdout)
    except ValueError:
        return None
    return tree if isinstance(tree, dict) and tree.get("Type") == "File" else None


_pip_tree = None                               # rung two: a pip-installed parser, unruled (#4)


def parse(text):
    """(rung, tree) from the first rung on hand; the awk rung's tree is None.
    Raises Unparseable when a parser refuses the text."""
    for rung in RUNGS:
        if rung == "awk":
            return rung, None
        read = {"shfmt": _shfmt_tree, "pip": _pip_tree}[rung]
        tree = read(text) if read else None
        if tree is not None:
            return rung, tree
    raise RuntimeError(f"no parser rung read the text (rungs: {', '.join(RUNGS)})")


def check(command):
    """Raise Unparseable when the top rung refuses the command itself."""
    parse(command)


def _off(node, key="Pos"):
    return node[key]["Offset"]


def _words(node, out):
    """Every Word under node, not descending into one: shfmt's typed JSON
    writes no Type on a Word, since its field is never an interface. A
    heredoc body is left to the awk lexer, as the awk rung reads it."""
    if isinstance(node, dict):
        if "Parts" in node and node.get("Type", "Word") == "Word":
            out.append(node)
            return
        for key, v in node.items():
            if key != "Hdoc":
                _words(v, out)
    elif isinstance(node, list):
        for v in node:
            _words(v, out)


def _heredocs(b):
    """(stripped, [(body, quoted)]) -- the awk's sw_heredocs walk. Every opener
    on a line takes its body in turn from the lines below; the rest of the
    opener line stays. quoted says the delimiter was quoted, so the shell
    expands nothing in it; an unquoted one's body keeps its command
    substitutions (heredoc_subs). A body whose closing line never comes stays
    in the text as commands. body is "" when the opener ends the text. The
    search resumes after each heredoc, never inside what it kept, so a `<<X`
    in a kept substitution cannot pair with a later X line."""
    done, docs = "", []
    while True:
        m = _OPENER.search(b)
        if not m:
            return done + b, docs
        head, b = b[:m.start()], b[m.start():]
        nl = b.find("\n")
        seg, tail = (b, "") if nl < 0 else (b[:nl], b[nl + 1:])
        delims = []

        def opener(o):
            raw = re.sub(r"^<<-?[ \t]*", "", o.group())
            d = re.sub(r"""["'\\]""", "", raw)
            delims.append((d, d != raw))
            return " HEREDOC "
        out, m = "", _OPENER.search(seg)
        while m:                            # the awk's per-line loop: each search
            out += seg[:m.start()] + opener(m)  # starts afresh after the last opener
            seg = seg[m.end():]
            m = _OPENER.search(seg)
        seg = out + seg
        subs, closed = "", nl >= 0
        for d, quoted in delims:
            body = ""
            if closed:
                e = re.search("(?:^|\n)[ \t]*" + re.escape(d) + "[ \t]*(?:\n|\\Z)", tail)
                if e:
                    body, tail = tail[:e.start()], tail[e.end():]
                    subs += "" if quoted else heredoc_subs(body)
                else:                       # never closes: keep it, as commands
                    body, closed = tail, False
            docs.append((body, quoted))
        done += head + seg + subs
        b = "" if nl < 0 else "\n" + tail


def strip_heredocs(b):
    """Drop every heredoc body but an unquoted one's command substitutions; the
    marker becomes the word HEREDOC."""
    return _heredocs(b)[0]


def heredoc_bodies(b):
    return [body for body, _ in heredocs(b)]


def heredocs(b):
    """[(body, live)] per heredoc; live when the delimiter was unquoted and the
    body holds a $ or a backtick the shell would expand."""
    return [(body, not quoted and ("$" in body or "`" in body))
            for body, quoted in _heredocs(b)[1]]


class Scan:
    def __init__(self, text):
        """Read by the first rung on hand. The command itself is checked once,
        by check(); a text that only might be shell -- a nested string, the
        text with heredocs stripped -- falls to the awk rung when shfmt
        refuses it or its tree cannot be mapped."""
        try:
            self.rung, tree = parse(text)
        except Unparseable:
            self.rung, tree = "awk", None
        self._reset()
        if tree is not None:
            try:
                src = text.encode("utf-8", "surrogatepass")
                self._region(src, tree, 0, len(src))
                self._emit()
            except Exception:  # noqa: BLE001 -- a mapping bug is a crashed rung
                self.rung, tree = "awk", None
                self._reset()
        if tree is None:
            self._lex(text)
            self._emit()
        del self._cur, self._have, self._quoted, self._skip, self._livecur
        self.shellseg = any(c is not None and self.w[c] in SHELL
                            for a, b in self.segments() for c in [seg_cmd(self, a, b)])

    def _reset(self):
        self.w, self.k, self.q, self.live = [], [], [], []
        self.pipes = set()                 # the separators that are a | or |&
        self._cur, self._have, self._quoted, self._skip, self._livecur = "", False, False, False, False

    def _region(self, src, node, a, b):
        """Bytes a..b of src, whose Words are node's: each Word through its
        parts, the text between them through the awk lexer."""
        ws = []
        _words(node, ws)
        at = a
        for w in sorted(ws, key=_off):
            s, e = _off(w), _off(w, "End")
            if s < at or e > b:
                raise ValueError(f"word at {s}..{e} outside {at}..{b}")
            self._lex(src[at:s].decode("utf-8", "surrogatepass"))
            self._word(src, w)
            at = e
        self._lex(src[at:b].decode("utf-8", "surrogatepass"))

    def _word(self, src, w):
        dec = lambda a, b: src[a:b].decode("utf-8", "surrogatepass")
        at = _off(w)
        for p in w["Parts"]:
            s, e, t = _off(p), _off(p, "End"), p.get("Type")
            self._lex(dec(at, s))
            if t == "Lit":
                self._lex(dec(s, e))
            elif t in ("SglQuoted", "DblQuoted"):
                if p.get("Dollar"):                # $'...' and $"..."
                    self._cur += "$"; self._livecur = True; s += 1
                self._quoted = self._have = True
                if t == "SglQuoted":
                    self._cur += dec(s + 1, e - 1)
                else:
                    self._dq(dec(s + 1, e - 1))
            else:                                  # $(...), ${...}, $((...)) and the rest
                self._region(src, p, s, e)
            at = e
        self._lex(dec(at, _off(w, "End")))

    def _dq(self, body):
        r"""A double-quoted body: \" \\ \$ \` escape; the rest literal."""
        i = 0
        while i < len(body):
            d = body[i]
            if d == "\\" and body[i + 1:i + 2] in ('"', "\\", "$", "`"):
                i += 1; d = body[i]
            elif d in ("$", "`"):
                self._livecur = True
            self._cur += d
            i += 1

    def __len__(self):
        return len(self.w)

    def tokens(self):
        """The fixture encoding: "w:<word>", "q:<raw>" or ";"."""
        return [";" if k == ";" else k + ":" + (q if k == "q" else w)
                for w, k, q in zip(self.w, self.k, self.q)]

    def segments(self):
        """(a, b) inclusive index ranges between separators, empty ones included,
        as the awk's `for (i = 1; i <= n + 1; i++)` walks them."""
        a = 0
        for i in range(len(self.w) + 1):
            if i < len(self.w) and self.k[i] != ";":
                continue
            yield a, i - 1
            a = i + 1

    def _emit(self):
        if not self._have:
            return
        if self._skip:
            self._skip = False
        else:
            if self._quoted and _WS.search(self._cur):
                self.w.append("$Q"); self.k.append("q"); self.q.append(self._cur)
            else:
                self.w.append(self._cur); self.k.append("w"); self.q.append("")
            self.live.append(self._livecur)
        self._cur, self._have, self._quoted, self._livecur = "", False, False, False

    def _sep(self):
        self._skip = False
        if not self.w or self.k[-1] == ";":
            return
        self.w.append(";"); self.k.append(";"); self.q.append(""); self.live.append(False)

    def _lex(self, b):
        """The awk lexer over b, carrying the word in progress across calls."""
        L = len(b)
        at = lambda j: b[j] if j < L else ""
        i = 0
        while i < L:
            c = b[i]
            if c == "\\":                          # \x is x; \<newline> is nothing
                i += 1
                d = at(i)
                if d not in ("\n", ""):
                    self._cur += d; self._have = True
                i += 1
                continue
            if c == "'":                           # literal to the next '
                self._quoted = self._have = True
                e = b.find("'", i + 1)
                if e < 0:
                    self._cur += b[i + 1:]
                    break
                self._cur += b[i + 1:e]
                i = e + 1
                continue
            if c == '"':                           # to the next unescaped "
                self._quoted = self._have = True
                e = i + 1
                while e < L and b[e] != '"':
                    e += 2 if b[e] == "\\" and at(e + 1) in ('"', "\\", "$", "`") else 1
                self._dq(b[i + 1:e])
                i = e + 1
                continue
            if c == "#" and not self._have:        # comment to end of line
                e = b.find("\n", i)
                if e < 0:
                    break
                i = e                              # the newline is the next token
                continue
            if c in (" ", "\t"):
                self._emit(); i += 1
                continue
            if c in ("<", ">") or (c == "&" and at(i + 1) == ">"):
                # A redirection: drop a bare fd number in front of it (2>&1), the
                # operator, and -- unless it is a dup like >&1 or >&- -- its operand.
                if self._have and not self._quoted and self._cur.isdigit() and self._cur.isascii():
                    self._cur, self._have = "", False
                else:
                    self._emit()
                while at(i + 1) in ("<", ">", "|"):
                    i += 1
                if at(i + 1) == "&":
                    i += 1
                    if at(i + 1) and at(i + 1) in "0123456789-":
                        while at(i + 1) and at(i + 1) in "0123456789-":
                            i += 1
                        i += 1
                        continue
                self._skip = True
                i += 1
                continue
            if c in (";", "|", "&", "\n", "(", ")", "`"):
                self._emit(); self._sep()
                o = i
                while at(i + 1) in (";", "|", "&"):
                    i += 1
                if b[o:i + 1] in ("|", "|&") and self.w:
                    self.pipes.add(len(self.w) - 1)
                i += 1
                continue
            if c in ("{", "}") and not self._have:
                self._sep(); i += 1
                continue
            if c == "$":
                self._livecur = True
            self._cur += c; self._have = True
            i += 1


def seg_cmd(s, a, b):
    """Index of the command-position word of segment a..b -- the first word
    after VAR=x assignments -- or None."""
    for i in range(a, b + 1):
        if s.k[i] != "w":
            return None
        if not _ASSIGN.match(s.w[i]):
            return i
    return None


def texts_of(text, prose=PROSE):
    """[(text, nested)]: the text itself plus, recursively, every quoted string
    in it that holds whitespace and may run. A segment's quoted strings are
    skipped only when it is led by a prose consumer, holds no executor, and no
    segment of its text is a shell. `prose` widens the consumer set for a
    guard whose command names also appear as arguments (pkill -f). Capped so a pathological command cannot spin."""
    out = [(text, False)]
    x = 0
    while x < len(out) and len(out) < NESTED_CAP:
        s = Scan(out[x][0])
        for a, b in s.segments():
            c = seg_cmd(s, a, b)
            ex = s.shellseg or any(s.k[j] == "w" and s.w[j] in EXEC for j in range(a, b + 1))
            if ex or c is None or s.w[c] not in prose:
                for j in range(a, b + 1):
                    if len(out) >= NESTED_CAP:
                        break
                    if s.k[j] == "q":
                        out.append((s.q[j], True))
        x += 1
    return out


def cmd_index(s, a, b, cmd, nested, parents=None, prose=PROSE):
    """Index in a..b of the word that is the command `cmd` (a compiled regex)
    describes, or None. Top level: any word counts unless the word before it
    matches `parents`, or the segment is led by a prose consumer and no segment
    is a shell. Nested: only the command position, past assignments, wrappers
    with their options, and shell keywords."""
    if not nested:
        c = seg_cmd(s, a, b)
        for i in range(a, b + 1):
            if (s.k[i] == "w" and cmd.search(s.w[i]) and
                    not (i > a and s.k[i - 1] == "w" and parents is not None and parents.search(s.w[i - 1]))):
                return i
            if i == c and s.w[c] in prose and not s.shellseg:
                return None
        return None
    wrap = False
    for i in range(a, b + 1):
        if s.k[i] != "w":
            return None
        if cmd.search(s.w[i]):
            return i
        if _ASSIGN.match(s.w[i]):
            continue
        if s.w[i] in WRAP:
            wrap = True
            continue
        if wrap and (s.w[i].startswith("-") or re.fullmatch(r"[0-9]+[smhd]?", s.w[i])):
            continue
        return None
    return None

