"""guard-recursive-delete: features/guard-recursive-delete.feature is the spec.

Blocks recursive `rm` and `find ... -delete` unless every target, resolved
against the payload's cwd and then through the filesystem, is Claude's to
remove: under the scratchpad, an agent worktree or /tmp, or a generated
directory (GENERATED_NAMES) that is not a direct child of $HOME or of /.
A target this guard cannot resolve to one allowed path is denied on sight,
with a reason naming what it saw.
"""

import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import Refuse, deny

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
_ALLOW_CHARS = re.compile(r"[A-Za-z0-9._@+/-]*")


def _parse_allow(value, home, home_p, physical):
    """LANGUETTE_RM_ALLOW -> (extra_roots, extra_names, error or None).
    `physical` resolves each path entry through the disk."""
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
            ent_p = physical(ent)
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
        self.cwd, self.home, self.homeN = cwd, home, paths.normalize(home)
        self.trig, self.moved, self.targets = "rm", False, []

    def lab(self, raw):
        if self.trig == "find":
            return "find" + ("" if raw == "" else " " + raw) + " -delete"
        return "rm -r" + ("" if raw == "" else " " + raw)

    def blocked(self, raw, why):
        raise Refuse(say("recursive_delete", label=self.lab(raw), why=why))

    def target(self, s, idx):
        raw = t = s.w[idx]
        if s.k[idx] == "q":
            self.blocked(raw, say("rd_quoted_space"))
        if re.search(r"[*?\[{}]", t):
            self.blocked(t, say("rd_glob"))
        if re.search(r"[$`]", t):
            self.blocked(t, say("rd_substitution"))
        if re.search(r"[\t\n\r]", t):
            self.blocked(t, say("rd_tab_newline"))
        if t == ".." or re.search(r"(?:^|/)\.\.(?:/|\Z)", t):
            self.blocked(t, say("rd_dotdot"))
        if "~" in t:
            if t == "~":
                t = self.home
            elif t.startswith("~/"):
                t = self.home + t[1:]
            else:
                self.blocked(t, say("rd_tilde"))
        if not t.startswith("/"):
            if self.moved:
                self.blocked(t, say("rd_cd_moved"))
            t = self.cwd + "/" + t
        t = paths.normalize(t)
        if t in ("/", self.homeN):
            self.blocked(raw, (say("rd_root") if t == "/" else say("rd_home")))
        self.targets.append((t, self.trig, raw))

    def segment(self, s, a, b, nested):
        g = sw.cmd_index(s, a, b, _FIND, nested)
        if g is not None and "-delete" in s.w[g + 1:b + 1]:
            self.trig, starts = "find", paths.find_starts(s, g, b)
            if not starts:
                self.blocked("", say("rd_find_no_start"))
            for i in starts:
                self.target(s, i)
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
            self.blocked("", say("rd_no_target"))
        for i in tgt:
            self.target(s, i)

    def run(self, doc):
        scans = [(doc.scan(t), nested) for t, nested in doc.texts()]
        # Any cd anywhere makes every relative target in the command unresolvable.
        self.moved = paths.moves_directory(scans)
        paths.judge_segments(self, scans)


_MALFORMED = ("LANGUETTE_RM_ALLOW is malformed ({}). Recursive rm and find -delete are "
              "blocked until it is fixed or unset; other commands run. It must be a colon-separated "
              "list of directory names (dist) or absolute paths (/srv/scratch), using only letters, "
              "digits and . _ @ + - ; a path may not hold a . or .. segment and may not be / or $HOME.")


def _verdict(targets, home, physical, extra_roots=(), extra_names=()):
    names = GENERATED_NAMES + tuple(extra_names)
    roots = paths.own_roots(home, physical, extra_roots)

    def is_generated(p):
        if p.startswith(home + "/"):
            p = p[len(home) + 1:]
        for depth, seg in enumerate((s for s in p.split("/") if s), 1):
            if seg in names:
                return depth != 1
        return False

    def allowed(p):
        return any(p == r or p.startswith(r + "/") for r in roots) or is_generated(p)

    for abs_, kind, raw in targets:
        what = f"find {raw} -delete" if kind == "find" else f"rm -r {raw}"
        if not allowed(abs_):
            return deny(
                f"`{what}` is blocked: only the scratchpad, /tmp, agent worktrees and the generated "
                "directories in GENERATED_NAMES in languette/guards/guard_recursive_delete.py (node_modules, dist, coverage, .pio ...) may be removed "
                f"recursively, and {abs_} is none of those. `git status --short {raw}` and `git clean -n {raw}` "
                "show what is there; `git rm` tracked files by path, and hand anything untracked to the user "
                "-- a directory they own can hold downloads and logs no session knows about.")
        phys = physical(abs_)
        if phys != abs_ and not allowed(phys):
            return deny(
                f"`{what}` is blocked: {abs_} resolves through a symlink to {phys}, which is not a generated "
                "directory, the scratchpad, /tmp or an agent worktree. rm follows a trailing slash into the "
                "link's target.")
    return None


def check(doc):
    return (yield from paths.check_targets(doc, NAME, _Judge, "LANGUETTE_RM_ALLOW", _parse_allow, _MALFORMED,
                                           _verdict))
