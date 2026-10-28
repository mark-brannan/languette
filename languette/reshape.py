"""Whether a `re:` find is one languette will run (docs/design/doctor.md, the
terms files). It is judged by the pattern's parse alone, never by running it on
text: a post must not hang on a pattern, and a timing varies with the machine.

refusal(pattern) is None for a pattern that is accepted, else why not:

    does not compile
    matches the empty string
    a backreference
    a quantifier inside a quantified group      (a+)+  (\\d+)*x  (a|b?a)*
    two unbounded repeats in a row over the same characters      .*.*;  \\w+\\d+x
    overlapping alternatives inside a repeat      (?:a|aa)+x

The three that backtrack without bound are found by overlap: a repeat is
ambiguous when what its body can start with is what a repeat inside it, the
repeat after it, or another alternative can also consume. A delimiter in
between keeps a pattern accepted: (\\.[\\w-]+)* is. Characters are compared over
Latin-1 and a few others, case-folded. Standard library only.
"""

import re

try:
    from re import _constants as C
    from re import _parser as P
except ImportError:                                    # Python before 3.11
    import sre_constants as C
    import sre_parse as P

_ALPHA = frozenset(chr(i) for i in range(0x250)) | {"中", "٣"}
_CATEGORY = {"DIGIT": r"\d", "NOT_DIGIT": r"\D", "SPACE": r"\s", "NOT_SPACE": r"\S", "WORD": r"\w", "NOT_WORD": r"\W"}


def _folded(chars):
    return chars | {c.lower() for c in chars} | {c.upper() for c in chars if len(c.upper()) == 1}


def _in(items):
    out, negate = set(), False
    for op, av in items:
        if op is C.NEGATE:
            negate = True
        elif op is C.LITERAL:
            out.add(chr(av))
        elif op is C.RANGE:
            out |= {chr(c) for c in range(av[0], av[1] + 1) if c < 0x250}
        elif op is C.CATEGORY:
            kind = re.compile(_CATEGORY[re.sub(r"^CATEGORY_(?:UNI_|LOC_)?", "", av.name)])
            out |= {c for c in _ALPHA if kind.match(c)}
    out = _folded(out) & _ALPHA
    return _ALPHA - out if negate else out


def _one(op, av):
    """The characters one item consumes, or None when it is not a single-character item."""
    if op is C.LITERAL:
        return _folded({chr(av)}) & _ALPHA
    if op is C.NOT_LITERAL:
        return _ALPHA - (_folded({chr(av)}) & _ALPHA)
    if op is C.ANY:
        return _ALPHA
    if op is C.IN:
        return _in(av)
    return None


def _children(op, av):
    """The item lists nested in an item."""
    if op is C.SUBPATTERN:
        return [av[3]]
    if op is C.BRANCH:
        return av[1]
    if op in (C.MAX_REPEAT, C.MIN_REPEAT, C.POSSESSIVE_REPEAT):
        return [av[2]]
    if op is C.ATOMIC_GROUP:
        return [av]
    if op in (C.ASSERT, C.ASSERT_NOT):
        return [av[1]]
    if op is C.GROUPREF_EXISTS:
        return [av[1], av[2] or []]
    return []


def _repeat(item):
    """(lo, hi, body) of a repeat that backtracks, else None; a possessive one does not."""
    op, av = item
    return av if op in (C.MAX_REPEAT, C.MIN_REPEAT) else None


def _unbounded(item):
    r = _repeat(item)
    return r is not None and r[1] == C.MAXREPEAT


def _first(seq):
    """(the characters a match of seq can start with, whether it can match nothing)."""
    out = set()
    for op, av in seq:
        one = _one(op, av)
        if one is not None:
            return out | one, False
        if op in (C.AT, C.ASSERT, C.ASSERT_NOT, C.GROUPREF, C.GROUPREF_EXISTS):
            continue
        parts = [_first(c) for c in _children(op, av)]
        for chars, _ in parts:
            out |= chars
        nullable = any(n for _, n in parts) or (op is C.BRANCH and not av[1]) \
            or (op in (C.MAX_REPEAT, C.MIN_REPEAT, C.POSSESSIVE_REPEAT) and av[0] == 0)
        if not nullable:
            return out, False
    return out, True


def _all(seq):
    out = set()
    for op, av in seq:
        one = _one(op, av)
        if one is not None:
            out |= one
        else:
            for c in _children(op, av):
                out |= _all(c)
    return out


def _both(a, b):
    return bool(a & b)


def _walk(seq):
    """Every item list in seq, seq first."""
    yield seq
    for op, av in seq:
        for c in _children(op, av):
            yield from _walk(c)


def _items(seq):
    for s in _walk(seq):
        yield from s


def _shape(tree):
    """Why the parsed pattern is one that backtracks without bound, or None."""
    items = list(_items(tree))
    if any(op in (C.GROUPREF, C.GROUPREF_EXISTS) for op, _ in items):
        return "a backreference"
    for item in items:
        if not _unbounded(item):
            continue
        body = item[1][2]
        start, _ = _first(body)
        for inner in _items(body):
            r = _repeat(inner)
            if r is not None and r[0] != r[1] and _both(_all(r[2]), start):
                return "a quantifier inside a quantified group"
    for seq in _walk(tree):
        for a, b in zip(seq, seq[1:]):
            if _unbounded(a) and _unbounded(b) and _both(_all(a[1][2]), _first(b[1][2])[0]):
                return "two unbounded repeats in a row over the same characters"
    for item in items:
        if not _unbounded(item):
            continue
        body = item[1][2]
        start, _ = _first(body)
        for op, av in _items(body):
            if op is not C.BRANCH:
                continue
            sets = [_first(alt)[0] for alt in av[1]]
            empty = any(not alt for alt in av[1])
            if any(_both(a, b) for i, a in enumerate(sets) for b in sets[i + 1:]) \
                    or (empty and any(_both(s, start) for s in sets)):
                return "overlapping alternatives inside a repeat"
    return None


def refusal(pattern):
    """None when `pattern` (matched case-insensitively) is accepted, else why not."""
    try:
        re.compile(pattern, re.I)
        tree = P.parse(pattern, re.I)
    except (re.error, RecursionError, OverflowError, ValueError):
        return "does not compile"
    if tree.getwidth()[0] == 0:
        return "matches the empty string"
    return _shape(tree)
