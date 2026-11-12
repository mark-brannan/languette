"""Where a posted body comes from: written in the command, a $VAR, a file,
stdin or a heredoc. One reading for every guard that judges a post's text, the
strictest the guards had: a body read here is the text the command sends, and
anything else is a source the guard cannot read, with why.

A source is a tuple: ("text", value) | ("doc", k), heredoc k's body |
("file", path, live, tilde), resolved by `where` | ("stdin", why), stdin no
heredoc feeds | ("opaque", why), built at run time.
"""

import re

from .messages import say
from .quoting import VAR_REF
from .texts import shell_heredocs, writes

_MARK = " HEREDOC "
_DOC = re.compile(r"HEREDOC(\d+)")
_FROM_DOC = re.compile(r"""\$\(\s*cat\s+(?:-\s+)?HEREDOC(\d+)\s*\)""")
_SEP = re.compile(r"(\|\||&&|[;&|])")
# A command that copies its stdin to a file unchanged: the file holds the heredoc's text.
_COPIES = re.compile(r"(?:\S*/)?(?:cat|tee)\Z")


def _short(v):
    v = v.replace("\n", " ")
    return v if len(v) <= 80 else v[:77] + "..."


class Bodies:
    """The command's heredocs, numbered where its text uses them, and the paths it
    writes: what a body source is read against. `text` is the command with heredoc
    bodies stripped and each marker numbered (HEREDOC0, HEREDOC1, ...); `docs` is
    [(body, live)] per heredoc, None when the markers would not pair with the bodies."""

    def __init__(self, doc, command):
        self.doc = doc
        self.buf = command + "\n"
        docs = doc.heredocs(self.buf)
        # A typed HEREDOC must not pass for scan's mark (the bodies are read from the command as written).
        parts = doc.stripped(self.buf.replace("HEREDOC", "HEREDOC_")).split(_MARK)
        if len(parts) - 1 == len(docs):
            self.text = "".join(p + (f" HEREDOC{k} " if k < len(parts) - 1 else "") for k, p in enumerate(parts))
            self.docs = docs
        else:
            self.text, self.docs = _MARK.join(parts), None
        # path -> times written, path -> the heredoc that alone fills it, paths appended to
        self.written, self.fed, self.appended = {}, {}, set()
        for line in self.text.split("\n"):
            for p, app in writes(line, False, True):
                self.written[p] = self.written.get(p, 0) + 1
                if app:
                    self.appended.add(p)
            for p, k in _copied(line):
                self.fed.setdefault(p, k)

    def texts(self):
        """[(text, nested)] the command runs, as Document.texts reads them, its own
        text with the heredocs numbered."""
        out = list(self.doc.texts(text=self.text))
        for body in shell_heredocs(self.buf, self.doc.scan):
            out += [(t, True) for t, _ in self.doc.texts(text=body)]
        return out

    def heredoc(self, k):
        if self.docs is None or k >= len(self.docs):
            return ("opaque", say("body_unpaired"))
        if self.docs[k][1]:
            return ("opaque", say("body_heredoc_live"))
        return ("doc", k)

    def value(self, v, live):
        """A posted value: its text, the heredoc that is it (`$(cat <<EOF)`, or a $VAR
        this command assigns once from one before using it), or opaque."""
        if not live:
            return ("text", v)
        m = _FROM_DOC.fullmatch(v.strip())
        if m:
            return self.heredoc(int(m.group(1)))
        m = VAR_REF.fullmatch(v)
        k = self._fed_var(m.group(1) or m.group(2)) if m else None
        if k is not None:
            return self.heredoc(k)
        return ("opaque", say("body_run_time", v=_short(v)))

    def _fed_var(self, name):
        """The heredoc a $NAME holds when this command assigns it once, from `$(cat <<EOF)`,
        before its first use, and never assigns it again (=, +=, read, printf -v,
        mapfile, for, unset), and runs nothing that could (eval, source, let, a nameref); else None."""
        t, n = self.text, re.escape(name)
        # A shell assignment, not a gh field (-f NAME=...) of the same name.
        sets = [a for a in re.finditer(r"(?:^|[\s;&|(])" + n + r"(?:\[[^\]]*\])?\+?=", t)
                if not re.search(r"(?:-[fF]|--field|--raw-field)\s*\Z", t[:a.start() + 1])]
        again = re.search(r"(?:^|[\s;&|(`])(?:read|printf|mapfile|readarray|unset|getopts|for|select)\b"
                          r"[^;&|\n]*?(?<![$\w{])" + n + r"\b", t)
        # eval, source, . and let assign from text these regexes never see; a nameref (declare -n) does too.
        blind = re.search(r"(?:^|[\s;&|(`])(?:(?:eval|source|let)\b|\.(?=\s)|(?:declare|typeset|local)\s+-\w*n\b)", t)
        use = re.search(r"\$\{?" + n + r"\b", t)
        if len(sets) != 1 or again or blind or not use or sets[0].end() > use.start() or "+=" in sets[0].group():
            return None
        fed = re.match(r"""["']?""" + _FROM_DOC.pattern, t[sets[0].end():])
        return int(fed.group(1)) if fed else None

    def stdin(self, s, lo, hi):
        """The body gh reads from stdin: the one heredoc on words lo..hi of scan s, or
        the heredoc a `cat <<EOF |` before them pipes in unchanged."""
        ks = [int(m.group(1)) for w in s.w[lo:hi + 1] if (m := _DOC.fullmatch(w))]
        if not ks and lo - 1 in s.pipes:
            a = next((x for x, y in s.segments() if y == lo - 2), None)
            words = [s.w[i] if s.k[i] == "w" else None for i in range(a, lo - 1)] if a is not None else []
            if words and _COPIES.match(words[0] or "") and words[0].endswith("cat"):
                ks = [int(m.group(1)) for w in words[1:] if w and (m := _DOC.fullmatch(w))]
                if len(ks) != 1 or len(words) - 1 != len(ks) + words[1:].count("-"):
                    ks = []
        if len(ks) == 1:
            return self.heredoc(ks[0])
        return ("stdin", say("body_stdin"))

    def file(self, p, live, tilde, s, lo, hi):
        """A body read from the file p, `-` being stdin."""
        return self.stdin(s, lo, hi) if p == "-" else ("file", p, live, tilde)

    def where(self, src, resolve):
        """Where a ("file", ...) source's text is: ("doc", k) when this command fills the
        file from heredoc k and writes it no other way, ("read", path) when the command
        leaves it as it is on disk, else ("unread", why) or ("opaque", why). `resolve`
        turns a path word the command writes into an absolute path, or None."""
        _, p, live, tilde = src
        f = resolve(p, live, tilde)
        if f is None:
            return ("unread", say("body_unresolved"))
        hit = [q for q in self.written if resolve(q, True, True) == f]
        if not hit:
            return ("read", f)
        n = sum(self.written[q] for q in hit)
        if n > 1:
            return ("unread", say("body_written_again", n=n))
        if hit[0] in self.appended:
            return ("unread", say("body_appended"))
        if hit[0] not in self.fed:
            return ("unread", say("body_not_heredoc"))
        return self.heredoc(self.fed[hit[0]])


def _copied(line):
    """(path, k) per file a line fills with heredoc k's text unchanged: `cat` or `tee`
    fed heredoc k writing it, or a `tee` that `cat <<EOF |` pipes into."""
    out, piped, op = [], None, ""
    for part in _SEP.split(line):
        if _SEP.fullmatch(part):
            op = part
            continue
        words = [w for w in re.split(r"\s+", part) if w]
        while words and re.match(r"[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        ks = [int(m.group(1)) for w in words if (m := _DOC.fullmatch(w))]
        k = ks[0] if len(ks) == 1 else piped if op == "|" and not ks else None
        copies = bool(words) and _COPIES.match(words[0].strip("\"'")) is not None
        piped = None
        if k is not None and copies:
            args = [w for w in words[1:] if not _DOC.fullmatch(w) and w not in ("-", "-a", "--append")]
            dests = writes(part, False)
            # Nothing but the heredoc goes in: no file operand beside the ones written.
            rest = [w for w in args if not re.fullmatch(r"\d*>>?", w) and w.strip("\"'") not in dests
                    and not re.fullmatch(r"\d*>>?.+", w)]
            if not rest:
                out += [(p, k) for p in dests]
                piped = k
    return out
