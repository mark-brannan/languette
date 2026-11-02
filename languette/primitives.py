"""The named tests a rule set's `{"test": name}` entry may use (docs/design/guard-rules.md,
"Primitives"): each a pure function of the Document that gives the fields of its
rule's message when the call is one it describes, else None. A test one guard needs
lives here, named, until a second guard asks for it; the registry is closed, and
only a shipped rule set may name one.
"""

import os
import re

from languette import scan as sw
from languette.messages import say

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_FORK = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&")


def _power(s, a, b):
    g = sw.cmd_index(s, a, b, _POWER, True)
    if g is None:                              # `sh -c reboot`: a one-word script is not a nested text
        g = next((i for i in range(a + 1, b + 1) if s.k[i] == "w" and _POWER.search(s.w[i])
                  and re.fullmatch(r"-[A-Za-z]*c", s.w[i - 1])), None)
    return None if g is None else os.path.basename(s.w[g])


def power_word(doc):
    """shutdown, reboot, halt or poweroff at command position, or as the one-word script of `sh -c`."""
    for t, _ in doc.texts():
        s = doc.scan(t)
        for a, b in s.segments():
            what = a <= b and _power(s, a, b)
            if what:
                return {"what": what}
    return None


def fork_bomb(doc):
    """The fork-bomb shape. It is raw text, so a commit message that quotes it must not trip it:
    only a text with a segment that is not led by a prose consumer is read."""
    for t, _ in doc.texts():
        s = doc.scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        if any(sw.seg_cmd(s, a, b) is None or s.w[sw.seg_cmd(s, a, b)] not in sw.PROSE or s.shellseg
               for a, b in segs) and _FORK.search(t):
            return {}
    return None


_DL = re.compile(r"(?:^|/)(?:curl|wget|fetch)\Z")
_INTERP = re.compile(r"(?:^|/)(?:sh|bash|dash|zsh|ksh|ash|fish|python[0-9.]*|perl[0-9.]*|node|ruby)\Z")
_SHELLS = re.compile(r"(?:sh|bash|dash|zsh|ksh|ash|fish)\Z")
_FED = ("(", "`")

# family -> (letters that mean "the program is given", options that take a value)
_NODE_SCRIPT = ("-e", "--eval", "-p", "--print", "-pe", "-ep", "-c", "--check")
_VALUE_OPTS = {"sh": ("-o", "-O", "+o", "+O", "--rcfile", "--init-file"), "python": ("-W", "-X"),
               "perl": ("-I",), "ruby": ("-I", "-r"), "node": ("-r", "--require", "--import", "--loader")}

def _family(path):
    name = os.path.basename(path)
    return ("sh" if _SHELLS.fullmatch(name) else "python" if name.startswith("python") else
            "perl" if name.startswith("perl") else name)


def _program(s, g, b):
    """How the interpreter at g gets its program: (script_given, operands),
    where script_given means a -c, -e or -m the interpreter runs instead of
    stdin, and operands are the words that are neither options nor their values."""
    fam, given, ops = _family(s.w[g]), False, []
    i = g + 1
    while i <= b:
        x, at, i = s.w[i], i, i + 1
        if s.k[at] != "w":
            ops.append(x)
        elif x == "--":
            ops += s.w[i:b + 1]
            break
        elif x in _VALUE_OPTS.get(fam, ()):
            i += 1
        elif x == "-" or (len(x) > 1 and x[0] in "-+"):
            if fam == "node":
                given = given or x in _NODE_SCRIPT
            elif re.fullmatch(r"-[A-Za-z]+", x) and not (fam == "perl" and x[1] in "MmIiFd"):
                given = given or any(ch in x for ch in {"sh": "c", "python": "cm", "perl": "eE", "ruby": "e"}[fam])
        else:
            ops.append(x)
    return given, ops


def _reads_stdin(s, g, b):
    """The interpreter at g takes its program from stdin: no -c/-e/-m, and no
    script operand (a lone `-` is stdin)."""
    given, ops = _program(s, g, b)
    if _family(s.w[g]) == "sh":
        stdin_flag = any(re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", w) for w in s.w[g + 1:b + 1])
        return not given and (stdin_flag or not ops)
    return not given and (not ops or ops[0] == "-")


def _has_dl(s, a, b, nested):
    return sw.cmd_index(s, a, b, _DL, nested) is not None


def _text_downloads(doc, raw):
    """A quoted word's text runs a download inside a substitution."""
    if "$(" not in raw and "`" not in raw:
        return False
    s = doc.scan(raw)
    return any(a <= b and _has_dl(s, a, b, False) for a, b in s.segments())


def _pipe_why(doc, s, nested):
    """The reason this scanned text is a pipe-to-shell, or None."""
    segs = {a: b for a, b in s.segments() if a <= b}
    carried = False
    for a, b in sorted(segs.items()):
        sep = s.op[a - 1] if a > 0 else ""
        if "|" not in sep.replace("||", "").replace("&&", ""):
            carried = False
        c = sw.seg_cmd(s, a, b)
        g = sw.cmd_index(s, a, b, _INTERP, nested)
        fed = (b + 1 < len(s.w) and s.op[b + 1].startswith(_FED)
               and (b + 2 in segs and _has_dl(s, b + 2, segs[b + 2], nested)))
        if g is not None:
            name = os.path.basename(s.w[g])
            if carried and _reads_stdin(s, g, b):
                return say("pipe_into", name=name)
            given, ops = _program(s, g, b)
            if fed and (given or not ops):
                return say("pipe_substituted", name=name)
            if given and any(s.k[i] == "q" and _text_downloads(doc, s.q[i]) for i in range(g + 1, b + 1)):
                return say("pipe_substituted_c", name=name)
        if c is not None and s.w[c] == "eval":
            if fed or any(s.k[i] == "q" and _text_downloads(doc, s.q[i]) for i in range(c + 1, b + 1)):
                return say("pipe_eval")
        if c is not None and s.w[c] in ("source", ".") and fed and len(s.w[c + 1:b + 1]) == 0:
            return say("pipe_source", name=s.w[c])
        if _has_dl(s, a, b, nested):
            carried = True
    return None


def pipe_to_shell(doc):
    """A download that is run as it arrives: piped into an interpreter that reads stdin, handed
    over as a file (`sh <(curl u)`) or as text (`eval "$(curl u)"`)."""
    for text, nested in doc.texts():
        why = _pipe_why(doc, doc.scan(text), nested)
        if why:
            return {"why": why, "way_out": say("pipe_to_shell_way_out")}
    return None


TESTS = {"power-word": power_word, "fork-bomb": fork_bomb, "pipe-to-shell": pipe_to_shell}
