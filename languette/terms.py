"""The terms files of guard-private-terms, parsed: the shipped
rules/redacted-terms.tsv, the user's redacted_terms_file and the
blocked_terms_file, one tab-separated format. The guard and `languette doctor`
both load through this module, so a line one would refuse the other names.

A line is the find, an optional put, an optional comment. The first line is
skipped when it is the header (`find put comment`, or `find message comment`
for the blocked file); `#` starts a comment line, a blank line is skipped, a
fourth column is not in shape. A find is case-insensitive plain text, or a
regular expression under `re:` that languette.reshape accepts. `$NAME` in a
find is that variable's value in the env given, a literal inside a `re:`; a
line naming a variable that is unset or empty is kept but matches nothing. In
the redacted file a line `!<put>` drops every shipped pair with that put.

Pure: the caller reads the text and supplies the hostname. Standard library only.
"""

import os
import re
from collections import namedtuple

from languette import reshape

# kind -> (the option, the default file, the second column's name)
KINDS = {"redacted": ("redacted_terms_file", "redacted-terms.tsv", "put"),
         "blocked": ("blocked_terms_file", "blocked-terms.tsv", "message")}
DEFAULT_PUT = "<redacted>"
SHIPPED = os.path.join(os.path.dirname(__file__), "rules", "redacted-terms.tsv")
MAX_READ = 1 << 20                                  # bytes of a terms file the guard reads
_VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

# find: as written; put: its second column or None; rx: compiled, None for a drop or a skipped line;
# name: what a hit is called, a plain find with its $NAMEs filled.
Term = namedtuple("Term", "find put rx is_re drop name")


class BadTerms(Exception):
    """A line the guard would refuse: its number (1-based) and why."""

    def __init__(self, line, why):
        super().__init__(f"line {line}: {why}")
        self.line, self.why = line, why


def option_name(kind):
    return KINDS[kind][0]


def where(kind, env):
    """(path, set): where the kind's file is read from and whether the user's option named it.
    A leading `~` or `$HOME` in the option is expanded; with the option unset or empty it is
    $XDG_CONFIG_HOME/languette/<file>, ~/.config by default. "" when there is no home to look in."""
    option, name, _ = KINDS[kind]
    home = env.get("HOME") or ""
    value = env.get("CLAUDE_PLUGIN_OPTION_" + option.upper()) or ""
    if value:
        m = re.match(r"(?:~|\$HOME|\$\{HOME\})(?=/|\Z)", value)
        return (home + value[m.end():] if m else value), True
    base = env.get("XDG_CONFIG_HOME") or (home + "/.config" if home else "")
    return (os.path.join(base, "languette", name) if base else ""), False


def _value(find, is_re, env):
    """(find with each $NAME filled, whether a variable was unset or empty). Where one is,
    a stand-in is filled so the line's shape is still judged."""
    unset = False

    def fill(m):
        nonlocal unset
        v = env.get(m.group(1)) or ""
        unset = unset or v == ""
        v = v or "x"
        return re.escape(v) if is_re else v
    return _VAR.sub(fill, find), unset


def parse(text, kind, env):
    """The Terms in file order. BadTerms on the first line the guard would refuse."""
    second = KINDS[kind][2]
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if n == 1 and line == f"find\t{second}\tcomment":
            continue
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) > 3:
            raise BadTerms(n, "four columns")
        find = cols[0].strip()
        put = cols[1] if len(cols) > 1 and cols[1] != "" else None
        if kind == "redacted" and find.startswith("!"):
            out.append(Term(find, find[1:], None, False, True, find))
            continue
        is_re = find.startswith("re:")
        pattern, unset = _value(find[3:] if is_re else find, is_re, env)
        if is_re:
            why = reshape.refusal(pattern)
            if why:
                raise BadTerms(n, why)
        elif not pattern:
            raise BadTerms(n, "matches the empty string")
        rx = re.compile(pattern if is_re else re.escape(pattern), re.I)
        out.append(Term(find, put, None if unset else rx, is_re, False, pattern))
    return out


def pairs(shipped, mine):
    """The redacted pairs in the order they apply: the shipped ones, minus any whose put a
    `!<put>` line of yours drops, then yours."""
    dropped = {t.put for t in mine if t.drop}
    return [t for t in shipped if t.rx and t.put not in dropped] + [t for t in mine if t.rx and not t.drop]


def redact(text, applied, esc=None):
    """text with each pair's find replaced by its put, in order. `esc`, when given, is
    applied to every put placed, for a word the shell would otherwise read."""
    for t in applied:
        put = DEFAULT_PUT if t.put is None else t.put
        put = esc(put) if esc else put
        text = t.rx.sub(lambda _, p=put: p, text)
    return text


def hits(text, terms):
    """[(name, message or None)] for each blocked term the text holds, in file order: the
    term as written, or for a `re:` find the text it matched."""
    out = []
    for t in terms:
        m = t.rx and t.rx.search(text)
        if m:
            hit = (m.group(0) if t.is_re else t.name, t.put)
            if hit not in out:
                out.append(hit)
    return out


def why_not(e):
    """Why a terms file could not be had, from the exception a read raised."""
    if isinstance(e, (FileNotFoundError, NotADirectoryError)):
        return "does not exist"
    if isinstance(e, UnicodeDecodeError):
        return "is not UTF-8 text"
    if isinstance(e, ValueError):
        return str(e)                       # "is not a regular file", "is over N bytes"
    return f"cannot be read ({getattr(e, 'strerror', None) or e})"


def named(found):
    """hits() as the deny and the doctor say them: `term (message)`, comma-separated."""
    return ", ".join(name + (f" ({message})" if message else "") for name, message in found)
