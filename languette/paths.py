"""Path words, as the guards that judge a target path share them: resolve one
word of a command to a single absolute path, or say why it cannot be one; the
agent's own areas. Standard library only."""

import os
import re

from languette import scan as sw
from languette.verdict import Need


class Unresolved(Exception):
    """A word that cannot be resolved to one path; str() says what the guard saw."""


def physical(p):
    """The longest existing prefix resolved through symlinks, the rest
    appended as written. "" for /. A generator: `yield from` it."""
    rest = ""
    while p != "/" and not (yield Need("path", "lexists", p)):
        head, _, base = p.rpartition("/")
        rest = "/" + base + rest
        p = head or "/"
    r = yield Need("path", "realpath", p)
    return ("" if r == "/" else r) + rest


def normalize(p):
    """Collapse "." segments and duplicate slashes. `..` is never passed in."""
    out = "".join("/" + s for s in p.split("/") if s not in ("", "."))
    return out or "/"


def lexical(p):
    """normalize, with `..` applied as text (the filesystem is not consulted)."""
    parts = []
    for s in p.split("/"):
        if s in ("", "."):
            continue
        if s == "..":
            if parts:
                parts.pop()
            continue
        parts.append(s)
    return "/" + "/".join(parts)


def resolve(word, quoted, cwd, home, moved):
    """One word of a command, as the absolute path it names, or Unresolved."""
    t = word
    if quoted:
        raise Unresolved("a quoted string with whitespace in it is not one path this hook can resolve")
    if re.search(r"[*?\[{}]", t):
        raise Unresolved("a glob or brace expansion could name anything")
    if re.search(r"[$`]", t):
        raise Unresolved("a variable or command substitution could expand to anything")
    if re.search(r"[\t\n\r]", t):
        raise Unresolved("it contains a tab or newline")
    if t == ".." or re.search(r"(?:^|/)\.\.(?:/|\Z)", t):
        raise Unresolved("a `..` segment steps out of the directory the name suggests")
    if "~" in t:
        if t == "~":
            t = home
        elif t.startswith("~/"):
            t = home + t[1:]
        else:
            raise Unresolved("only a leading `~/` is understood")
    if not t.startswith("/"):
        if moved:
            raise Unresolved("a `cd` earlier in this command moves the working directory and the hook "
                             "cannot follow it; use an absolute path")
        t = cwd + "/" + t
    return normalize(t)


def own_roots(home, extra=()):
    """Where the agent works and nothing of the user's lives, as written and
    as the filesystem has them (/tmp is /private/tmp on macOS). A generator."""
    base = ["/tmp", home + "/.local/state/claude-tmpdir", home + "/.claude/worktrees"]
    phys = []
    for r in base:
        phys.append((yield from physical(r)))
    return base + phys + list(extra)


def under(p, roots):
    return any(p == r or p.startswith(r + "/") for r in roots)


_CD = re.compile(r"^(?:cd|pushd|popd)\Z")
_CHDIR_WRAP = re.compile(r"(?:^|/)(?:sudo|doas|env)\Z")
# env -C, sudo -D and sudo -R (a chroot: `.` is somewhere else there too), in every spelling getopt
# takes: detached, attached (-C/etc), clustered (-nD /etc), and a long option or any prefix of it.
_CHDIR_OPT = re.compile(r"-[A-Za-z]*[CDR].*|--c(?:h(?:d(?:ir?)?|r(?:o(?:ot?)?)?)?)?(?:=.*)?")
# Options of env, sudo and doas that take the next word as their value.
_VALUE_LETTERS = "uSghprtTU"
_VALUE_LONG = ("unset", "split-string", "close-from", "group", "host", "prompt", "role", "type",
               "command-timeout", "user", "other-user")


def chdir_wrapper(s, a, b):
    """A wrapper that runs its command in another directory: `env -C dir`, `sudo -D dir`, `sudo -R dir`.
    Only the wrapper's own options are read, up to the command it runs, so that command's own -R is
    not taken for one. A wrapper option this does not know errs toward True, which only denies a
    relative path."""
    for i in range(a, b + 1):
        if s.k[i] != "w" or not _CHDIR_WRAP.search(s.w[i]):
            continue
        value = False
        for j in range(i + 1, b + 1):
            x = s.w[j]
            if s.k[j] != "w":
                break
            if _CHDIR_OPT.fullmatch(x):
                return True
            if x.startswith("--") and len(x) > 2:
                value = "=" not in x and any(o.startswith(x[2:]) for o in _VALUE_LONG)
            elif x.startswith("-") and len(x) > 1:
                value = x[-1] in _VALUE_LETTERS
            elif value or sw._ASSIGN.match(x):
                value = False
            else:
                break
    return False


def moves_directory(scans):
    """True when some segment of some scanned text is a cd, pushd or popd, or a
    wrapper with a chdir option: every relative path in the command is then
    unresolvable."""
    return any(a <= b and (sw.cmd_index(s, a, b, _CD, True) is not None or chdir_wrapper(s, a, b))
               for s, _ in scans for a, b in s.segments())
