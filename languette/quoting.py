"""Quoting and heredocs, as the shell reads them: ANSI-C quotes, where a quote
or a substitution ends, the logical line an opener sits on, and heredoc
bodies (stripped from the text, or read out of it).
"""

import bisect
import re


_DPART = r"""'[^'\n]*'|"[^"\n]*"|\\."""
_OPENER = re.compile(r"(?<!<)<<-?[ \t]*(?:[A-Za-z_]|" + _DPART + r")(?:[A-Za-z0-9_]|" + _DPART + r")*")
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# A word's run-time part that names one variable: $NAME or ${NAME}, the name in group 1 or 2.
VAR_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
# A word the shell would still expand, glob or brace-expand, so its text is not yet its value.
UNREADABLE = re.compile(r"[$`*?\[{]")
_CASE = re.compile(r"(?<![A-Za-z0-9_])case(?![A-Za-z0-9_])")


_ANSI_C = re.compile(r"\\(?:([abeEfnrtv\\'\"?])|([0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})"
                     r"|U([0-9A-Fa-f]{1,8})|c(.))", re.S)
_ANSI_C_CHARS = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r",
                 "t": "\t", "v": "\v"}


def ansi_c(body):
    r"""The text of $'body': the escapes bash decodes (\n, \', octal, \xHH, \u,
    \cX ...); an unknown one stays as written. Bash stops at a NUL."""
    def one(m):
        simple, octal, hexa, u4, u8, ctl = m.groups()
        if simple:
            return _ANSI_C_CHARS.get(simple, simple)
        if ctl:
            return chr(ord(ctl) & 0x1f)
        n = int(octal, 8) & 0xff if octal else int(hexa or u4 or u8, 16)
        try:
            # A lone surrogate is not text: bash emits bytes no encoder takes.
            return chr(n) if not 0xd800 <= n <= 0xdfff else m.group(0)
        except (ValueError, OverflowError):
            return m.group(0)
    return _ANSI_C.sub(one, body).split("\0", 1)[0]


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
    or ""), read by its own rules: a backslash escapes outside single quotes
    (and inside `$'...'`), and a `#` comments to the end of its line only before a word has begun,
    so `a\\ #'` opens a quote and `a #'` does not."""
    return _qopen(t)[0]


def _qopen(t):
    """(quote, index) of the quote _qclose finds open, or ("", -1)."""
    L, i, have, dollar = len(t), 0, False, False
    while i < L:
        c, after_dollar, dollar = t[i], dollar, False
        if c == "\\":
            if i + 1 < L and t[i + 1] != "\n":
                have = True
            i += 2
            continue
        if c == "'" and after_dollar:
            have, o, i = True, i, i + 1            # $'...': a backslash escapes, \' included
            while i < L and t[i] != "'":
                i += 2 if t[i] == "\\" else 1
            if i >= L:
                return "'", o
            i += 1
            continue
        if c == "'":
            have, e = True, t.find("'", i + 1)
            if e < 0:
                return "'", i
            i = e + 1
            continue
        if c == '"':
            have, o, i = True, i, i + 1
            while i < L and t[i] != '"':
                i += 2 if t[i] == "\\" else 1
            if i >= L:
                return '"', o
            i += 1
            continue
        if c == "#" and not have:
            e = t.find("\n", i)
            if e < 0:
                return "", -1
            i = e
            continue
        if c in " \t\n;|&()`<>":
            have = False
        elif c not in "{}" or have:
            have = True
        dollar = c == "$" and not after_dollar  # one unescaped $: `\$` went by above, `$$` is a PID
        i += 1
    return "", -1


def _line_end(t, i=0):
    """Index of the newline that ends the logical line of t starting at i, or -1, read by
    the lexer's own rules (_qopen): a newline inside a quote, after a
    backslash, in `$'...'`, or in a `$(...)` or `...` substitution goes on,
    and `#` comments to the end of its line only before a word has begun. A
    heredoc body begins on the line after it. A quote or substitution left
    open to the end of t gives -1, so nothing after it is taken for a body and
    every word stays in the text."""
    L, have, dollar, subs = len(t), False, False, []
    while i < L:
        c, after_dollar, dollar = t[i], dollar, False
        if c == "\\":
            have = have or (i + 1 < L and t[i + 1] != "\n")
            i += 2
            continue
        if c == "\n":
            if not subs:
                return i
            have = False
            i += 1
            continue
        if c in "'\"":
            have = True
            if c == "'" and not after_dollar:
                e = t.find("'", i + 1)
                i = L if e < 0 else e
            else:                                  # "...", and $'...' with its escapes
                i += 1
                while i < L and t[i] != c:
                    i += 2 if t[i] == "\\" else 1
            if i >= L:
                return -1
            i += 1
            continue
        if c == "#" and not have:
            i = t.find("\n", i)
            if i < 0 or not subs:
                return i
            continue
        if subs and not have and re.match(r"case[ \t\n]", t[i:i + 5]):
            return -1                              # a pattern's ) would close $( early: fail closed
        if c == "(" and (after_dollar or subs[-1:] == [")"]):
            subs.append(")")                       # $( opens, ( nests inside one
        elif c == ")" and subs[-1:] == [")"] or c == "`" and subs[-1:] == ["`"]:
            subs.pop()
        elif c == "`":
            subs.append("`")
        if c in " \t;|&()`<>":
            have = False
        elif c not in "{}" or have:
            have = True
        dollar = c == "$" and not after_dollar
        i += 1
    return -1


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


def _closers(b):
    """Every line of b by its text less the spaces and tabs around it: {text: [line start]}."""
    out, at = {}, 0
    for line in b.split("\n"):
        out.setdefault(line.strip(" \t"), []).append(at)
        at += len(line) + 1
    return out


def _closing(b, closers, d, q):
    """(start, end) of the first line at or past q that is delimiter d with spaces and tabs
    around it, end just past its newline; None when no such line comes."""
    starts = closers.get(d.strip(" \t"), ())
    for at in starts[bisect.bisect_left(starts, q):]:
        e = b.find("\n", at)
        e = len(b) if e < 0 else e
        if re.fullmatch(r"[ \t]*" + re.escape(d) + r"[ \t]*", b[at:e]):
            return at, min(e + 1, len(b))
    return None


def _heredocs(b):
    """(stripped, [(body, quoted)]) -- the awk's sw_heredocs walk. Every opener
    on a line takes its body in turn from the lines below; the rest of the
    opener line stays. The opener's line runs to the first newline outside a
    quote or substitution and after no backslash (_line_end); one that never
    closes leaves the rest of the text as commands. quoted says the delimiter
    was quoted, so the shell expands nothing in it; an unquoted one's body
    keeps its command
    substitutions (heredoc_subs). A body whose closing line never comes stays
    in the text as commands. body is "" when the opener ends the text. The
    search resumes after each heredoc, never inside what it kept, so a `<<X`
    in a kept substitution cannot pair with a later X line. The walk reads b
    once: each closing line is looked up, not searched for."""
    done, docs, at, closers = [], [], 0, None
    while True:
        m = _OPENER.search(b, at)
        if not m:
            done.append(b[at:])
            return "".join(done), docs
        head = b[at:m.start()]
        nl = _line_end(b, m.start())  # the opener's logical line, not its first physical one
        seg, q = (b[m.start():], len(b)) if nl < 0 else (b[m.start():nl], nl + 1)
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
                closers = _closers(b) if closers is None else closers
                e = _closing(b, closers, d, q)
                if e:
                    body, q = b[q:max(q, e[0] - 1)], e[1]
                    subs += "" if quoted else heredoc_subs(body)
                else:                       # never closes: keep it, as commands
                    body, closed = b[q:], False
            docs.append((body, quoted))
        done.append(head + seg + subs)
        if nl < 0:
            return "".join(done), docs
        if q >= len(b):
            done.append("\n")
            return "".join(done), docs
        at = q - 1                          # the newline before the rest, as the line break it is


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
