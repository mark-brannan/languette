"""Cd tracking: the directories each segment of a scan may run in, following
cd and pushd, and failing to unknown where the shell's reading could differ.
"""

import os
import re

from .lexicon import CD
from .lexer import seg_cmd, word_live


def cd_present(s):
    """True when some plain word of scan s is cd, pushd or popd, wherever it
    stands: a guard that does not follow the working directory gives up on
    the word alone."""
    return any(k == "w" and CD.match(w) for k, w in zip(s.k, s.w))


def _abspath(p):
    """p normalized with `.` and `//` folded; `..` is applied as text, so callers pass only a
    `..` that cannot cross a symlink (see _dotdot_ok): the filesystem is not consulted."""
    return os.path.normpath("/" + p.lstrip("/"))


def _dotdot_ok(t, fresh):
    """True when cd target t holds no `..` whose lexical reading could differ from the
    shell's. Only a leading run of `..` from a start that is a realpath (`fresh`) is read;
    a `..` after a named step, in an absolute target or after an earlier cd may cross a
    symlink, so the directory is unknown and the guard fails closed."""
    parts = t.split("/")
    n = 0
    while n < len(parts) and parts[n] in ("..", ".", ""):
        n += 1
    if ".." in parts[n:]:
        return False
    return ".." not in parts[:n] or (fresh and not t.startswith("/"))


# The operators a separator's text is made of, as Scan piles them up. A guard that also
# reads { } and the backtick as openers adds them (pushes does).
SEP_OPS = re.compile(r"\|\||&&|\|&|\||&|;|\n|\(|\)")


def _cd_to(s, c, b, here, home, cdpath, fresh=False):
    """Where the cd/pushd at c (its segment ending at b) lands from `here`, or None
    when that cannot be read: `-`, popd, a live word, a CDPATH search, an unknown start, a `..`
    that may cross a symlink (`fresh`: `here` is the start realpath, no cd has moved it), or
    a pushd that is not exactly one plain directory (no operand swaps the stack, `+N` rotates
    it, `-n` leaves the directory alone)."""
    if s.w[c] == "popd":
        return None
    i = c + 1
    while i <= b and re.fullmatch(r"-[LPe@]+", s.w[i]):
        i += 1
    if i <= b and s.w[i] == "--":
        i += 1
    if s.w[c] == "pushd" and (i > b or re.fullmatch(r"[+-]\d+|-n", s.w[i]) or i < b):
        return None
    if i > b:
        t = "~"
    elif word_live(s, i) or s.w[i] == "-" or s.k[i] != "w":
        return None
    else:
        t = s.w[i]
    if t == "~" or t.startswith("~/"):
        if not (home and home.startswith("/")) or (i <= b and s.quoted[i]):
            return None
        t = home + t[1:]
    elif t.startswith("~"):
        return None
    if not _dotdot_ok(t, fresh and here is not None):
        return None
    if t.startswith("/"):
        return _abspath(t)
    if here is None or (cdpath and not re.match(r"\.\.?(?:/|\Z)", t)):
        return None
    return _abspath(here + "/" + t)


def cwds(s, start, home=None, cdpath=False):
    """Cd tracking: {a: the directories segment a..b of scan s may run in}, a frozenset in
    which None stands for one that cannot be known, following each top-level cd and pushd
    from `start` (an absolute path, or None). A cd joined by `&&` moves what follows it;
    after any other separator the old directory stays possible too, since the cd may have
    failed. A cd in a pipeline or backgrounded moves nothing, a ( ) subshell's cd ends at
    its ), and a cd the scan cannot read (cd_to, or one not in command position) leaves
    the directory unknown. `cdpath`: CDPATH is set, so a relative cd may land anywhere."""
    first = frozenset([start])
    here, alt, stack, out = first, frozenset(), [], {}
    for a, b in s.segments():
        before = s.op[a - 1] if a > 0 else ""
        after = s.op[b + 1] if b + 1 < len(s.w) else ""
        out[a] = here
        if a <= b:
            c = seg_cmd(s, a, b)
            alone = not re.search(r"(?<!\|)\|(?!\|)", before + " " + after) and not re.search(r"(?<!&)&(?!&)", after)
            if c is not None and CD.match(s.w[c]):
                if alone:
                    alt, here = alt | here, frozenset(_cd_to(s, c, b, h, home, cdpath, here == first) for h in here)
            elif any(s.k[i] == "w" and CD.match(s.w[i]) for i in range(a, b + 1)):
                alt, here = alt | here, here | {None}
        for t in SEP_OPS.findall(after):
            if t == "(":
                stack.append((here, alt))
            elif t == ")":
                here, alt = stack.pop() if stack else (first, frozenset())
            elif t != "&&":
                here, alt = here | alt, frozenset()
    return out
