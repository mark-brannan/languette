"""guard-recursive-delete: recursive `rm` and `find -delete` only on what is Claude's.

Blocks recursive `rm` (-r, -R, --recursive, or any short cluster containing
r/R: -rf, -fr, -rfv, -Rf) and `find ... -delete` unless every target,
resolved against the payload's cwd and then through the filesystem, is
Claude's to remove.

The scar: an agent ran `rm -rf examples` to sweep the untracked leftovers
of a refactor and destroyed captures and a watch log the user was using
as an ongoing download area. `git rm --cached` had already handled the
tracked files; the `rm -rf` existed only to sweep the rest, and the rest
was the user's.

Allowlist, not a denylist. A target is allowed only when it is:
  1. under the session scratchpad, an agent worktree, or /tmp -- these are
     Claude's areas, nothing of the user's lives there;
  2. a directory named in GENERATED_NAMES below (its final path component,
     or an ancestor component -- so `dist` and `dist/sub` both pass), and
     not a direct child of $HOME or of the filesystem root: ~/proj/dist and
     /opt/proj/dist are build output, ~/dist and /dist are directories that
     happen to share the name.
Everything else is denied: any other directory under $HOME (a misc
directory in the home tree is the user's by default, whatever it holds), any
repo's tracked or working directories, `public/` included -- one project's
generated `public/` is another's tracked source, so the name stays off the
list. LANGUETTE_RM_ALLOW adds roots and names to the list; it never
replaces them.

Both the path as written and the path as the filesystem resolves it must be
allowed: `rm -rf /tmp/x/` where /tmp/x is a symlink into a repo empties the
repo directory (rm follows a trailing slash), so the physical path is
checked too.

A target this guard cannot resolve to one allowed path is not allowed, and
is denied on sight with a reason naming what it saw: a glob (*, ?, [), a
brace ({}), a shell variable or $(...) or `...`, a `..` segment, a `~`
other than a leading one, a quoted string with whitespace in it, a
control character, a target that resolves to / or $HOME, a relative
target after a `cd` anywhere in the same command (the guard cannot follow
the cd), and a recursive rm with NO visible target -- which is what
`find ... -exec rm -rf {} +`, `xargs rm -rf` and `rm -rf {a,b}` look like
once the scanner is done with them. In every one of those the fix is the
same: run `rm -rf` on the resolved paths, spelled out.

`rm` on a single file (no recursive flag) passes -- where the file is
tracked that is `git rm`'s job, and looking at the target before deleting
it is the agent's job otherwise. `git rm`, `yadm rm` and the other
version-control `rm` subcommands (svn, hg, jj, gsutil) are untouched --
there rm is a subcommand, not the command. Otherwise rm counts as the
command wherever it stands in a segment (after find -exec, xargs, do,
time ...), and the body of a quoted string with whitespace (`sh -c '...'`,
`eval "..."`) is scanned as well, there by command position only.

Out of scope, by design (this is an accident guard, not a sandbox): flags
arriving through a variable (`rm $OPTS x`), `rmdir`, `rsync --delete`,
deletion from inside python/node one-liners.

Scanning is languette/scan.py's (read its docstring). This is a GATE, so it
fails closed: an unreadable payload or a crash here is a deny (run.py), and
the hooks.json wrapper denies when python3 or run.py is missing.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import Refuse, context, deny

NAME = "guard-recursive-delete"

# Adding a name is a PR, not a judgment call in a session.
#   node_modules   npm/yarn/pnpm install output, most JS repos
#   dist           tsc/vite/webpack build output
#   coverage       test coverage reports (nyc/jest/vitest)
#   .pio           PlatformIO build cache
GENERATED_NAMES = ("node_modules", "dist", "coverage", ".pio")

_FIND = re.compile(r"(?:^|/)find\Z")
_RM = re.compile(r"(?:^|/)rm\Z")
_RM_PARENTS = re.compile(r"^(?:git|yadm|svn|hg|jj|gsutil)\Z")
_CD = re.compile(r"^(?:cd|pushd|popd)\Z")
_ALLOW_CHARS = re.compile(r"[A-Za-z0-9._@+/-]*")


def _physical(p):
    """The longest existing prefix resolved through symlinks, the rest
    appended as written. "" for /."""
    rest = ""
    while p != "/" and not os.path.lexists(p):
        head, _, base = p.rpartition("/")
        rest = "/" + base + rest
        p = head or "/"
    r = os.path.realpath(p)
    return ("" if r == "/" else r) + rest


def _normalize(p):
    out = "".join("/" + s for s in p.split("/") if s not in ("", "."))
    return out or "/"


def _parse_allow(value, home, home_p):
    """LANGUETTE_RM_ALLOW -> (extra_roots, extra_names, error or None)."""
    roots, names = [], []
    for ent in value.split(":"):
        if ent == "":
            return roots, names, "an empty entry"
        if not _ALLOW_CHARS.fullmatch(ent):
            return roots, names, f"unsupported character in '{ent}'"
        if ent.startswith("/"):
            if ent.endswith(("/.", "/..")) or "/./" in ent or "/../" in ent or "//" in ent:
                return roots, names, f"'{ent}' has an empty, . or .. segment"
            if ent.endswith("/"):
                ent = ent[:-1]
            if ent in ("", home):
                return roots, names, f"'{ent}' is / or $HOME"
            ent_p = _physical(ent)
            if ent_p in ("", home, home_p):
                return roots, names, f"'{ent}' resolves to / or $HOME"
            roots += [ent, ent_p]
        elif "/" in ent:
            return roots, names, f"'{ent}' is neither a bare name nor an absolute path"
        elif ent in (".", ".."):
            return roots, names, f"'{ent}' is not a name"
        else:
            names.append(ent)
    return roots, names, None


class _Judge:
    """What the awk half of the shell guard does: find every recursive target
    in the command and either refuse it on sight or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home, self.homeN = cwd, home, _normalize(home)
        self.trig, self.moved, self.targets = "rm", False, []

    def lab(self, raw):
        if self.trig == "find":
            return "find" + ("" if raw == "" else " " + raw) + " -delete"
        return "rm -r" + ("" if raw == "" else " " + raw)

    def blocked(self, raw, why):
        raise Refuse(
            f"`{self.lab(raw)}` is blocked: {why}. Resolve the target yourself and spell it out: `rm -rf` on "
            "the absolute path of a generated directory (node_modules, dist, coverage, .pio ...), the "
            "scratchpad, /tmp or an agent worktree. Anything else in a repo or under $HOME is the user's -- "
            "`git status --short` / `git clean -n` show what is there; `git rm` tracked files by path and "
            "hand the rest to the user.")

    def target(self, s, idx):
        raw = t = s.w[idx]
        if s.k[idx] == "q":
            self.blocked(raw, "a quoted string with whitespace in it is not one path this hook can resolve")
        if re.search(r"[*?\[{}]", t):
            self.blocked(t, "a glob or brace expansion could name anything")
        if re.search(r"[$`]", t):
            self.blocked(t, "a variable or command substitution could expand to anything")
        if re.search(r"[\t\n\r]", t):
            self.blocked(t, "it contains a tab or newline")
        if t == ".." or re.search(r"(?:^|/)\.\.(?:/|\Z)", t):
            self.blocked(t, "a `..` segment steps out of the directory the name suggests")
        if "~" in t:
            if t == "~":
                t = self.home
            elif t.startswith("~/"):
                t = self.home + t[1:]
            else:
                self.blocked(t, "only a leading `~/` is understood")
        if not t.startswith("/"):
            if self.moved:
                self.blocked(t, "a `cd` earlier in this command moves the working directory and the hook "
                                "cannot follow it; use an absolute path")
            t = self.cwd + "/" + t
        t = _normalize(t)
        if t in ("/", self.homeN):
            self.blocked(raw, "that is " + ("the root of the filesystem" if t == "/" else "$HOME itself"))
        self.targets.append((t, self.trig, raw))

    def segment(self, s, a, b, nested):
        g = sw.cmd_index(s, a, b, _FIND, nested)
        if g is not None and "-delete" in s.w[g + 1:b + 1]:
            self.trig, starts = "find", 0
            i = g + 1
            while i <= b and not s.w[i].startswith(("-", "!")):
                starts += 1
                self.target(s, i)
                i += 1
            if not starts:
                self.blocked("", "with no start path find deletes under the working directory")
            self.trig = "rm"
        g = sw.cmd_index(s, a, b, _RM, nested, _RM_PARENTS)
        if g is None:
            return
        recursive, dashdash, tgt = False, False, []
        for i in range(g + 1, b + 1):
            x = s.w[i]
            if not dashdash and x == "--":
                dashdash = True
                continue
            # GNU getopt_long takes any unambiguous prefix: --rec, --r are --recursive.
            if not dashdash and s.k[i] == "w" and x.startswith("--"):
                if len(x) >= 3 and "--recursive".startswith(x):
                    recursive = True
                continue
            if not dashdash and s.k[i] == "w" and len(x) >= 2 and x.startswith("-"):
                if re.fullmatch(r"-[A-Za-z0-9]*[rR][A-Za-z0-9]*", x):
                    recursive = True
                continue
            tgt.append(i)
        if not recursive:
            return
        if not tgt:
            self.blocked("", "no target is visible to this hook -- find -exec, xargs, brace expansion and "
                             "quoted lists all look like this. Run rm on the resolved paths directly")
        for i in tgt:
            self.target(s, i)

    def run(self, text):
        texts = sw.texts_of(sw.strip_heredocs(text))
        scans = [(sw.Scan(t), nested) for t, nested in texts]
        # Any cd anywhere makes every relative target in the command unresolvable.
        self.moved = any(a <= b and sw.cmd_index(s, a, b, _CD, True) is not None
                         for s, _ in scans for a, b in s.segments())
        for s, nested in scans:
            for a, b in s.segments():
                if a <= b:
                    self.segment(s, a, b, nested)


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        cwd = os.getcwd()
    home = env.get("HOME", "")
    if not home.startswith("/"):
        return deny("guard-recursive-delete: $HOME is not an absolute path, cannot resolve targets")

    home_p = _physical(home)
    extra_roots, extra_names, allow_err = [], [], None
    if env.get("LANGUETTE_RM_ALLOW"):
        extra_roots, extra_names, allow_err = _parse_allow(env["LANGUETTE_RM_ALLOW"], home, home_p)
    allow_msg = None
    if allow_err:
        allow_msg = (f"LANGUETTE_RM_ALLOW is malformed ({allow_err}). Recursive rm and find -delete are "
                     "blocked until it is fixed or unset; other commands run. It must be a colon-separated "
                     "list of directory names (dist) or absolute paths (/srv/scratch), using only letters, "
                     "digits and . _ @ + - ; a path may not hold a . or .. segment and may not be / or $HOME.")

    judge, refused = _Judge(cwd, home), None
    try:
        judge.run(cmd + "\n")
    except Refuse as e:
        refused = str(e)
    if refused is None and not judge.targets:
        return context("guard-recursive-delete: " + allow_msg) if allow_msg else None
    if allow_msg:
        return deny("guard-recursive-delete: " + allow_msg)
    if refused is not None:
        return deny(refused)

    names = GENERATED_NAMES + tuple(extra_names)
    scratch = home + "/.local/state/claude-tmpdir"
    worktrees = home + "/.claude/worktrees"
    roots = ["/tmp", scratch, worktrees, _physical("/tmp"), _physical(scratch), _physical(worktrees)] + extra_roots

    def is_generated(p):
        if p.startswith(home + "/"):
            p = p[len(home) + 1:]
        for depth, seg in enumerate((s for s in p.split("/") if s), 1):
            if seg in names:
                return depth != 1
        return False

    def allowed(p):
        return any(p == r or p.startswith(r + "/") for r in roots) or is_generated(p)

    for abs_, kind, raw in judge.targets:
        what = f"find {raw} -delete" if kind == "find" else f"rm -r {raw}"
        if not allowed(abs_):
            return deny(
                f"`{what}` is blocked: only the scratchpad, /tmp, agent worktrees and the generated "
                "directories named in guard-recursive-delete (node_modules, dist, coverage, .pio ...) may be removed "
                f"recursively, and {abs_} is none of those. `git status --short {raw}` and `git clean -n {raw}` "
                "show what is there; `git rm` tracked files by path, and hand anything untracked to the user "
                "-- a directory they own can hold downloads and logs no session knows about.")
        phys = _physical(abs_)
        if phys != abs_ and not allowed(phys):
            return deny(
                f"`{what}` is blocked: {abs_} resolves through a symlink to {phys}, which is not a generated "
                "directory, the scratchpad, /tmp or an agent worktree. rm follows a trailing slash into the "
                "link's target.")
    return None
