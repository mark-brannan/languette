"""Path words, as the guards that judge a target path share them: resolve one
word of a command to a single absolute path, or say why it cannot be one; the
agent's own areas. What the disk says about a path is a Need("physical", p),
which a guard plans and the runner answers. Standard library only."""

import json
import os
import re

from languette import scan as sw
from languette.verdict import Need, Refuse, deny


class Unresolved(Exception):
    """A word that cannot be resolved to one path; str() says what the guard saw."""


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


def own_bases(home):
    """Where the agent works and nothing of the user's lives, as written."""
    return ["/tmp", home + "/.local/state/claude-tmpdir", home + "/.claude/worktrees"]


def own_roots(home, physical, extra=()):
    """own_bases, as written and as the filesystem has them (/tmp is
    /private/tmp on macOS); `physical` maps a path to its physical answer."""
    base = own_bases(home)
    return base + [physical(r) for r in base] + list(extra)


def physical_of(answers):
    """Path -> its planned Need("physical") answer. One the world could not
    have is raised, as the runner once threw it into the guard."""
    def physical(p):
        got = answers[Need("physical", p)]
        if isinstance(got, Exception):
            raise got
        return got
    return physical


def under(p, roots):
    return any(p == r or p.startswith(r + "/") for r in roots)


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
    return any(a <= b and (sw.cmd_index(s, a, b, sw.CD, True) is not None or chdir_wrapper(s, a, b))
               for s, _ in scans for a, b in s.segments())


def find_starts(s, g, b):
    """The start paths of the `find` at word g: every word before its first option or test."""
    i = g + 1
    while i <= b and not s.w[i].startswith(("-", "!")):
        i += 1
    return range(g + 1, i)


def judge_segments(judge, scans):
    """judge.segment on every non-empty segment of every scanned text."""
    for s, nested in scans:
        for a, b in s.segments():
            if a <= b:
                judge.segment(s, a, b, nested)


def parse_targets(doc, name, judge, allow_var):
    """The parse of a guard that judges target paths: `judge(cwd, home)` walks the
    command and gathers its targets; `allow_var` names the env var of extra
    allowed paths. "found" is a finding parse alone comes to."""
    payload, env = doc.payload, doc.env
    out = {"found": None, "home": None, "allow": None, "targets": [], "refused": None}
    if doc.text is None:
        return out
    cwd = payload["cwd"]
    home = env.get("HOME", "")
    if not home.startswith("/"):
        out["found"] = deny(f"{name}: $HOME is not an absolute path, cannot resolve targets")
        return out
    walker = judge(cwd, home)
    try:
        walker.run(doc)
    except Refuse as e:
        out["refused"] = str(e)
    out.update(home=home, allow=env.get(allow_var) or None, targets=walker.targets)
    return out


def plan_targets(parsed, parse_allow):
    """The physical path of $HOME and each allow entry, when the allow var is set;
    of the agent's own areas and every target, when there are targets to judge.
    `parse_allow(value, home, home_p, physical)` reads the allow var."""
    if parsed["found"] or parsed["home"] is None:
        return []
    home, want = parsed["home"], []
    if parsed["allow"]:
        want.append(home)
        parse_allow(parsed["allow"], home, home, lambda p: want.append(p) or p)
    if parsed["refused"] is None and parsed["targets"]:
        want += own_bases(home) + [t for t, _, _ in parsed["targets"]]
    return [Need("physical", p) for p in dict.fromkeys(want)]


def project_config(payload, env, name):
    """The project's `name` file: the nearest at or above cwd, stopping at the repo
    root, because the agent may have cd'd into another repo; then
    $CLAUDE_PROJECT_DIR's. Returns (path or None, whether cwd was a usable directory)."""
    cwd = payload.get("cwd")
    usable = isinstance(cwd, str) and cwd.startswith("/") and (yield Need("path", "isdir", cwd))
    if usable:
        d = yield Need("path", "realpath", cwd)
        while True:
            if (yield Need("path", "lexists", os.path.join(d, name))):
                return os.path.join(d, name), True
            if (yield Need("path", "lexists", os.path.join(d, ".git"))) or os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
    proj = env.get("CLAUDE_PROJECT_DIR")
    if proj and (yield Need("path", "lexists", os.path.join(proj, name))):
        return os.path.join(proj, name), bool(usable)
    return None, bool(usable)


def read_json(path):
    """The file at path, parsed as JSON, or Refuse naming why it cannot be."""
    try:
        return json.loads((yield Need("read", path)))
    except ValueError as e:
        raise Refuse(f"not JSON ({e})")
    except OSError as e:
        raise Refuse(f"unreadable ({e.strerror})")
