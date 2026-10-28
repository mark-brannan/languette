"""The terms files of guard-private-terms, parsed: the user's
redacted_terms_file and blocked_terms_file, one tab-separated format. The guard
and `languette doctor` both load through this module, so a line one would
refuse the other names. Only a file's entries count: the guard loads no other
set. The default entries, rules/redacted-terms.tsv, are what the doctor writes
into a new redacted terms file and repairs in an old one.

A line is the find, an optional put, an optional comment. The first line is
skipped when it is the header (`find put comment`, or `find message comment`
for the blocked file); `#` starts a comment line, a blank line is skipped, a
fourth column is not in shape. A find is case-insensitive plain text, or a
regular expression under `re:` that languette.reshape accepts. `$NAME` in a
find is that variable's value in the env given, a literal inside a `re:`; a
line naming a variable that is unset or empty is kept but matches nothing.

A default entry is a line the doctor copied, its comment column tagged
`default:<name>@<version>`: the name groups the lines of one default, the
version is a hash of the group's finds and puts, so an edit to any of them
shows. Commenting a default's line out turns it off and keeps it off.

The parsing is pure. The loading is a generator that yields the Needs for the
read and the hostname, which the guard and the doctor both drive. Standard
library only.
"""

import hashlib
import os
import re
from collections import namedtuple

from languette import reshape
from languette.verdict import Need

# kind -> (the option, the default file, the second column's name)
KINDS = {"redacted": ("redacted_terms_file", "redacted-terms.tsv", "put"),
         "blocked": ("blocked_terms_file", "blocked-terms.tsv", "message")}
DEFAULT_PUT = "<redacted>"
DEFAULTS = os.path.join(os.path.dirname(__file__), "rules", "redacted-terms.tsv")
MAX_READ = 1 << 20                                  # bytes of a terms file the guard reads
_VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
# The tag on a default entry's comment column; the version is absent in the rules file.
TAG = re.compile(r"^default:(?P<name>[\w-]+)(?:@(?P<version>[0-9a-f]+))?(?=\s|$)")
# A default's line, active or commented out, split into its columns.
_LINE = re.compile(r"^(?P<off>#\s*)?(?P<find>[^\t]*)\t(?P<put>[^\t]*)\t(?P<comment>default:[^\t]*)$")

# find: as written; put: its second column or None; rx: compiled, None for a skipped line;
# name: what a hit is called, a plain find with its $NAMEs filled.
Term = namedtuple("Term", "find put rx is_re name")
# One default entry's line: the find, the put, what its comment says after the tag.
Default = namedtuple("Default", "find put about")


class BadTerms(Exception):
    """A line the guard would refuse: its number (1-based) and why."""

    def __init__(self, line, why):
        super().__init__(f"line {line}: {why}")
        self.line, self.why = line, why


def option_name(kind):
    return KINDS[kind][0]


def option_env(option):
    """The environment variable Claude Code gives a plugin option."""
    return "CLAUDE_PLUGIN_OPTION_" + option.upper()


def header(kind):
    return f"find\t{KINDS[kind][2]}\tcomment"


def where(kind, env):
    """(path, set): where the kind's file is read from and whether the user's option named it.
    A leading `~` or `$HOME` in the option is expanded; with the option unset or empty it is
    $XDG_CONFIG_HOME/languette/<file>, ~/.config by default. "" when there is no home to look in."""
    option, name, _ = KINDS[kind]
    home = env.get("HOME") or ""
    value = env.get(option_env(option)) or ""
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


def entries(text, kind, env):
    """(line number, the line, its Term or the BadTerms the guard would refuse it for) for
    every entry line, in file order: the header, comment and blank lines are skipped."""
    for n, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if n == 1 and line == header(kind):
            continue
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) > 3:
            yield n, line, BadTerms(n, "four columns")
            continue
        find = cols[0].strip()
        put = cols[1] if len(cols) > 1 and cols[1] != "" else None
        is_re = find.startswith("re:")
        pattern, unset = _value(find[3:] if is_re else find, is_re, env)
        why = reshape.refusal(pattern) if is_re else "matches the empty string" if not pattern else None
        if why:
            yield n, line, BadTerms(n, why)
            continue
        rx = re.compile(pattern if is_re else re.escape(pattern), re.I)
        yield n, line, Term(find, put, None if unset else rx, is_re, pattern)


def parse(text, kind, env):
    """The Terms in file order. BadTerms on the first line the guard would refuse."""
    out = []
    for _, _, item in entries(text, kind, env):
        if isinstance(item, BadTerms):
            raise item
        out.append(item)
    return out


def environment(env):
    """`env` with $HOSTNAME as the terms read it: the env's own, else the OS's."""
    return {**env, "HOSTNAME": env.get("HOSTNAME") or (yield Need("hostname"))}


def read(kind, env):
    """(the kind's file's text, its path, whether an option named it, the exception that stops
    the guard judging by it or None). The text is None when there is no file to read: an unset
    option with nothing at the default path, which is no error."""
    path, named = where(kind, env)
    if not path:
        return None, "", named, None
    try:
        return (yield Need("read", path, MAX_READ)), path, named, None
    except Exception as e:  # noqa: BLE001 -- the world's own: missing, a directory, unreadable
        if not named and isinstance(e, (FileNotFoundError, NotADirectoryError)):
            return None, path, named, None
        return None, path, named, e


def load(kind, env, penv):
    """(the kind's terms, its path, whether an option named it, the exception that stops the guard
    judging by it or None): read, then parse under penv."""
    text, path, named, err = yield from read(kind, env)
    if text is None:
        return None, path, named, err
    try:
        return parse(text, kind, penv), path, named, None
    except BadTerms as e:
        return None, path, named, e


def pairs(found):
    """The redacted pairs that apply, in file order: a line naming an unset variable matches nothing."""
    return [t for t in found if t.rx]


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
    if isinstance(e, IsADirectoryError):
        return "is a directory"
    if isinstance(e, PermissionError):
        return "is not readable"
    if isinstance(e, UnicodeDecodeError):
        return "is not UTF-8 text"
    if isinstance(e, ValueError):
        return str(e)                       # "is not a regular file", "is over N bytes"
    return f"cannot be read ({getattr(e, 'strerror', None) or e})"


def named(found):
    """hits() as the deny and the doctor say them: `term (message)`, comma-separated."""
    return ", ".join(name + (f" ({message})" if message else "") for name, message in found)


# --- the default entries ----------------------------------------------------

def defaults(text):
    """name -> [Default] in the rules file's order, from its text: every entry line whose
    comment column carries a tag."""
    out = {}
    for line in text.split("\n"):
        m = _LINE.match(line.rstrip("\r"))
        tag = m and TAG.match(m["comment"])
        if tag and not m["off"]:
            about = m["comment"][tag.end():].strip()
            out.setdefault(tag["name"], []).append(Default(m["find"], m["put"], about))
    return out


def version(lines):
    """A default's version: a hash of its lines' finds and puts, so an edit to any of them shows."""
    h = hashlib.sha1("\n".join(f"{d.find}\t{d.put}" for d in lines).encode("utf-8"))
    return h.hexdigest()[:7]


def written(name, lines):
    """A default's lines as the doctor writes them, each tagged with the name and the version."""
    v = version(lines)
    return [f"{d.find}\t{d.put}\tdefault:{name}@{v}" + (f" {d.about}" if d.about else "") for d in lines]


def initial(groups):
    """A new redacted terms file: the header and every default."""
    lines = [header("redacted"), "# Terms replaced in a post bound for a public repo: find, put, comment.",
             "# A default: line is one languette doctor wrote and can repair; comment it out to turn it off."]
    for name, group in groups.items():
        lines += written(name, group)
    return "\n".join(lines) + "\n"


def _tagged(text):
    """[(index, name, version, off, Default)] for every tagged line of a user's file."""
    out = []
    for i, line in enumerate(text.split("\n")):
        m = _LINE.match(line.rstrip("\r"))
        tag = m and TAG.match(m["comment"])
        if tag:
            out.append((i, tag["name"], tag["version"], bool(m["off"]),
                        Default(m["find"], m["put"], m["comment"][tag.end():].strip())))
    return out


def restore(text, groups):
    """(the user's redacted terms file repaired, [what was done or left]): a missing default is
    inserted in the defaults' order, one unedited since its version is replaced by the current
    lines, one edited by hand is reported and left, one commented out anywhere is left, one no
    longer a default is commented out, and every other line is left as it is."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    tagged = _tagged(text)
    by_name = {}
    for i, name, v, off, d in tagged:
        by_name.setdefault(name, []).append((i, v, off, d))
    edits = {}                             # line index -> replacement lines, [] to drop
    inserts = {}                           # line index -> lines to put before it; len(lines) for the end
    notes = []
    for name, group in groups.items():
        current = version(group)
        mine = by_name.get(name)
        if mine is None:
            continue
        if any(off for _, _, off, _ in mine):
            continue
        tags = {v for _, v, _, _ in mine}
        found = version([d for _, _, _, d in mine])
        if found == current:
            continue
        if tags == {found}:
            first, *rest = (i for i, _, _, _ in mine)
            edits[first] = written(name, group)
            for i in rest:
                edits[i] = []
            notes.append(f"{name}: updated to the current version")
        else:
            notes.append(f"{name}: edited by hand, so left as it is")
    present = [n for n in groups if n in by_name]
    for k, name in enumerate(groups):
        if name in by_name:
            continue
        later = next((n for n in list(groups)[k + 1:] if n in by_name), None)
        if later is not None:
            at = min(i for i, _, _, _ in by_name[later])
        elif present:
            earlier = [n for n in list(groups)[:k] if n in by_name]
            at = max(i for i, _, _, _ in by_name[earlier[-1]]) + 1
        else:
            at = 1 if lines and lines[0] == header("redacted") else 0
        inserts.setdefault(at, []).extend(written(name, groups[name]))
        notes.append(f"{name}: added")
    for name, mine in by_name.items():
        if name in groups:
            continue
        for i, _, off, _ in mine:
            if not off:
                edits[i] = ["# " + lines[i]]
        notes.append(f"{name}: no longer a default, so commented out")
    out = []
    for i, line in enumerate(lines):
        out += inserts.get(i, [])
        out += edits[i] if i in edits else [line]
    out += inserts.get(len(lines), [])
    return "\n".join(out) + "\n", notes
