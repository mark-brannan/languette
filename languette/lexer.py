"""The Scan: a text's words, as the ladder's top rung or the awk lexer reads them.

Indices are 0-based. A Scan holds parallel lists: w (word text), k ("w", "q"
or ";"), q (raw text of a quoted word holding whitespace, else ""), live (the
word carried a $ or backtick the shell would act on), and shellseg (some
segment is led by a shell, so `echo ... | sh` is executed text).
"""

import re

from . import ladder                           # ladder.parse, so a stand-in for it reaches this call too
from .quoting import ansi_c, _ASSIGN, _sub_end
from .lexicon import SHELL, _FIND_EXECS, _FIND_WRAPPERS
from .ladder import RunFailed, TooBig, Unparseable


_WS = re.compile(r"[ \t\n]")


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


class Scan:
    def __init__(self, text):
        """Read by the first rung on hand. The command itself is checked once,
        by the Document's reading(); a text that only might be shell -- a nested string, the
        text with heredocs stripped -- falls to the awk rung when a rung
        refuses it or its tree cannot be mapped. A failed run (RunFailed)
        raises: the clock never picks the reader. Only shfmt's tree maps."""
        try:
            self.rung, tree = ladder.parse(text, words=True)
        except (RunFailed, TooBig):
            raise
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
        del self._cur, self._have, self._quoted, self._esc, self._skip, self._livecur
        self.shellseg = any(c is not None and self.w[c] in SHELL
                            for a, b in self.segments() for c in [seg_cmd(self, a, b)])

    def _reset(self):
        self.w, self.k, self.q, self.live = [], [], [], []
        self.quoted = []                   # per word: any part of it quoted or backslash-escaped
        self.subs = []                     # bodies of $(...) and `...` inside double quotes
        self.op = []                       # per word: a separator's operator text, else ""
        self.pipes = set()                 # the separators that are a | or |&
        self._cur, self._have, self._quoted, self._skip, self._livecur = "", False, False, False, False
        self._esc = False

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
                dollar = p.get("Dollar")
                if dollar and t == "SglQuoted":    # $'...': ANSI-C quoting, decoded
                    self._quoted = self._have = True
                    self._cur += ansi_c(dec(s + 2, e - 1))
                    at = e
                    continue
                if dollar:                         # $"..."
                    self._cur += "$"; self._livecur = True; s += 1
                self._quoted = self._have = True
                if t == "SglQuoted":
                    self._cur += dec(s + 1, e - 1)
                else:
                    body = dec(s + 1, e - 1)
                    self._dq(body, body)
            else:                                  # $(...), ${...}, $((...)) and the rest
                self._region(src, p, s, e)
            at = e
        self._lex(dec(at, _off(w, "End")))

    def _dq(self, body, rest):
        r"""A double-quoted body: \" \\ \$ \` escape; the rest literal. rest is
        the text from the body's start to wherever a substitution in it may
        run (_dq_sub): the body itself when a parser bounded it, the rest of
        the text when the awk lexer did."""
        i = 0
        while i < len(body):
            d = body[i]
            if d == "\\" and body[i + 1:i + 2] in ('"', "\\", "$", "`"):
                i += 1; d = body[i]
            elif d in ("$", "`"):
                self._livecur = True
                self._dq_sub(rest, i)
            self._cur += d
            i += 1

    def _dq_sub(self, b, i):
        """b[i] is a live $ or backtick inside double quotes; when it opens a
        command substitution, keep its body in subs for texts_of. The awk's
        sw_dq_sub: a $(...) ends where _sub_end says, and one it cannot be
        sure of keeps the rest of b; a backtick runs to the next unescaped
        one, or to the end, and its body loses the backslash before $ ` \\ or ",
        as the shell's does before it runs it."""
        if b.startswith("$(", i):
            j = _sub_end(b, i + 2)
            self.subs.append(b[i + 2:j - 1 if b[j - 1:j] == ")" else j])
        elif b[i] == "`":
            j, t = i + 1, ""
            while j < len(b) and b[j] != "`":
                if b[j] == "\\":
                    j += 1
                    if b[j:j + 1] not in ("$", "`", "\\", '"'):
                        t += "\\"
                t += b[j:j + 1]
                j += 1
            self.subs.append(t)

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
            self.live.append(self._livecur); self.op.append(""); self.quoted.append(self._quoted or self._esc)
        self._cur, self._have, self._quoted, self._livecur, self._esc = "", False, False, False, False

    def _sep(self, op=""):
        """A separator; `op` is the operator text that made it (`;`, `&&`, `|`, `)`, ...),
        and consecutive operators pile up on one separator, so `op` reads `;}` for `; }`."""
        self._skip = False
        if not self.w:
            return
        if self.k[-1] == ";":
            self.op[-1] += op
            return
        self.w.append(";"); self.k.append(";"); self.q.append(""); self.live.append(False); self.op.append(op)
        self.quoted.append(False)

    def _in_find_exec(self):
        """True when this segment is a find (the command word, past VAR=x, flags
        and a wrapper like sudo or xargs) that already holds -exec, -execdir,
        -ok or -okdir, whose {} ends the command it runs. A quoted word is
        skipped over; only the segment boundary stops the walk. Keyed on the
        command word, so `gh pr edit --title -ok {}` is not a find."""
        n = len(self.w)
        i = n
        while i > 0 and self.k[i - 1] != ";":
            i -= 1
        while i < n and self.k[i] == "w" and (
                _ASSIGN.match(self.w[i]) or self.w[i].startswith("-")
                or self.w[i].rsplit("/", 1)[-1] in _FIND_WRAPPERS):
            i += 1
        if i >= n or self.k[i] != "w" or self.w[i].rsplit("/", 1)[-1] != "find":
            return False
        return any(self.k[x] == "w" and self.w[x] in _FIND_EXECS for x in range(i + 1, n))

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
                    self._cur += d; self._have = self._esc = True
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
            if c == "$" and at(i + 1) == "'":      # $'...': ANSI-C quoting, to the next unescaped '
                self._quoted = self._have = True
                e = i + 2
                while e < L and b[e] != "'":
                    e += 2 if b[e] == "\\" else 1
                self._cur += ansi_c(b[i + 2:e])
                i = e + 1
                continue
            if c == '"':                           # to the next unescaped "
                self._quoted = self._have = True
                e = i + 1
                while e < L and b[e] != '"':
                    e += 2 if b[e] == "\\" and at(e + 1) in ('"', "\\", "$", "`") else 1
                self._dq(b[i + 1:e], b[i + 1:])
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
                self._emit()
                o = i
                while at(i + 1) in (";", "|", "&"):
                    i += 1
                self._sep(b[o:i + 1])
                if b[o:i + 1] in ("|", "|&") and self.w:
                    self.pipes.add(len(self.w) - 1)
                i += 1
                continue
            if c in ("{", "}") and not self._have:
                if c == "{" and at(i + 1) == "}" and at(i + 2) in ("", " ", "\t", "\n", ";", "|", "&", ")", "<", ">") \
                        and not self._in_find_exec():
                    self._cur += "{}"; self._have = True   # a bare {} is a word (xargs -I{}); find's stays a separator
                    i += 2
                    continue
                self._sep(c); i += 1
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


# A word the shell would still expand, glob or brace-expand, so its text is not yet its value.
UNREADABLE = re.compile(r"[$`*?\[{]")


def word_live(s, i):
    """Word-live: True when word i of scan s is not yet the value the command gets: it carried
    a $ or backtick the shell acts on, or holds a glob or brace the shell may expand. Quoting
    is not read, so a quoted `*` counts too: unsure reads as live."""
    return bool(s.live[i]) or UNREADABLE.search(s.w[i]) is not None


def word(s, i):
    """The text of word i: q for a quoted word holding whitespace (the w list
    has $Q there), w for any other."""
    return s.q[i] if s.k[i] == "q" else s.w[i]
