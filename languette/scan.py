"""Shell-text scanner: a port of hooks/lib-shell-words.awk, whose header is
the spec. Nothing here decides anything; it turns the Bash tool's command
string into words a guard judges, and every ambiguity resolves toward MORE
words reaching the guard, never fewer.

Indices are 0-based. A Scan holds parallel lists: w (word text), k ("w", "q"
or ";"), q (raw text of a quoted word holding whitespace, else ""), live (the
word carried a $ or backtick the shell would act on), and shellseg (some
segment is led by a shell, so `echo ... | sh` is executed text).
"""

import re

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
    and a `#` that starts a word comments to the end of its line."""
    L, i = len(t), 0
    while i < L:
        c = t[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            e = t.find("'", i + 1)
            if e < 0:
                return "'"
            i = e + 1
            continue
        if c == '"':
            i += 1
            while i < L and t[i] != '"':
                i += 2 if t[i] == "\\" else 1
            if i >= L:
                return '"'
            i += 1
            continue
        if c == "#" and (i == 0 or t[i - 1] in " \t\n;|&()`<>"):
            e = t.find("\n", i)
            if e < 0:
                return ""
            i = e
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
        seg = _OPENER.sub(opener, seg)
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
        self.w, self.k, self.q, self.live = [], [], [], []
        self._cur, self._have, self._quoted, self._skip, self._livecur = "", False, False, False, False
        self._run(text)
        del self._cur, self._have, self._quoted, self._skip, self._livecur
        self.shellseg = any(c is not None and self.w[c] in SHELL
                            for a, b in self.segments() for c in [seg_cmd(self, a, b)])

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

    def _run(self, b):
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
            if c == '"':                           # \" \\ \$ \` escape; the rest literal
                self._quoted = self._have = True
                i += 1
                while i < L:
                    d = b[i]
                    if d == '"':
                        break
                    if d == "\\" and at(i + 1) in ('"', "\\", "$", "`"):
                        i += 1; d = b[i]
                    elif d in ("$", "`"):
                        self._livecur = True
                    self._cur += d
                    i += 1
                i += 1
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
                while at(i + 1) in (";", "|", "&"):
                    i += 1
                i += 1
                continue
            if c in ("{", "}") and not self._have:
                self._sep(); i += 1
                continue
            if c == "$":
                self._livecur = True
            self._cur += c; self._have = True
            i += 1
        self._emit()


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

