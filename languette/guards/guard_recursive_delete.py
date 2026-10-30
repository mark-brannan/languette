"""guard-recursive-delete: features/guard-recursive-delete.feature is the spec.

Blocks recursive `rm` and `find ... -delete` unless every target, resolved
against the payload's cwd and then through the filesystem, is the agent's to
remove: under the scratchpad, an agent worktree or /tmp, or a generated
directory (GENERATED_NAMES) that is not a direct child of $HOME or of /.
A target this guard cannot resolve to one allowed path is denied on sight,
with a reason naming what it saw.
"""

import functools
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
_RM_PARENTS = re.compile(r"^(?:" + "|".join(sw.GIT_WRAPPERS) + r"|svn|hg|jj|gsutil)\Z")


class _Judge:
    """Find every recursive target in the command and either refuse it on
    sight or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home = cwd, home
        self.trig, self.moved, self.targets = "rm", False, []

    def lab(self, raw):
        if self.trig == "find":
            return "find" + ("" if raw == "" else " " + raw) + " -delete"
        return "rm -r" + ("" if raw == "" else " " + raw)

    def blocked(self, raw, why):
        raise Refuse(say("recursive_delete", label=self.lab(raw), why=why))

    def target(self, s, idx):
        raw = s.w[idx]
        try:
            t = paths.resolve_target(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.blocked(raw, str(e))
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


def _malformed(guard, err):
    return say("rm_malformed", guard=guard, err=err)


def _verdict(targets, home, bases, physical, extra_roots=(), extra_names=()):
    names = GENERATED_NAMES + tuple(extra_names)
    roots = paths.own_roots(home, bases, physical, extra_roots)

    def is_generated(p):
        if p.startswith(home + "/"):
            p = p[len(home) + 1:]
        for depth, seg in enumerate((s for s in p.split("/") if s), 1):
            if seg in names:
                return depth != 1
        return False

    def allowed(p):
        return paths.under(p, roots) or is_generated(p)

    for abs_, kind, raw in targets:
        what = f"find {raw} -delete" if kind == "find" else f"rm -r {raw}"
        if not allowed(abs_):
            return deny(say("rd_not_allowed", what=what, raw=raw, abs_=abs_))
        phys = physical(abs_)
        if phys != abs_ and not allowed(phys):
            return deny(say("rd_symlink_out", what=what, abs_=abs_, phys=phys))
    return None


_PARSE_ALLOW = functools.partial(paths.parse_allow, bare_names=True)


def check(doc):
    return (yield from paths.check_targets(doc, NAME, _Judge, "LANGUETTE_RM_ALLOW", _PARSE_ALLOW, _malformed,
                                           _verdict))
