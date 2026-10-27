"""guard-permissions: features/guard-permissions.feature is the spec.

Blocks a recursive chown, chgrp or chmod (-R, --recursive, a short cluster
holding R), `chmod 777`, and `find ... -exec chown|chgrp|chmod` unless every
target, resolved against the payload's cwd and then through the filesystem,
is the agent's own: under the scratchpad, an agent worktree or /tmp, or an
absolute path named in LANGUETTE_PERM_ALLOW. Never `/`, $HOME itself, or
anything inside a .git. A target this guard cannot resolve to one allowed path
is denied on sight, with a reason naming what it saw.
"""

import os
import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import Refuse, deny

NAME = "guard-permissions"

_CMD = re.compile(r"(?:^|/)(chown|chgrp|chmod)\Z")
_FIND = re.compile(r"(?:^|/)find\Z")
_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_WRAPPERS = re.compile(r"(?:sudo|doas|env|nice|nohup|timeout|command|exec|time|ionice|stdbuf|sh|bash|dash|zsh|ksh)\Z")
_PERM_IN_TEXT = re.compile(r"(?:^|[^A-Za-z0-9_./-])(chmod|chown|chgrp)(?![A-Za-z0-9_-])")
_CHMOD_FLAGS = re.compile(r"-[Rcfv]+\Z")
_WORLD = re.compile(r"(?:0*777|(?:a|ugo)[+=]rwx)\Z")

_WAY_OUT = ("Spell the files out: chmod or chown the paths themselves, without -R (`git ls-files <dir>` lists "
            "what a sweep would touch), or sweep inside the scratchpad, /tmp or an agent worktree. Anything "
            "else is the user's; a sweep over a project tree is theirs to run, or to allow with "
            "LANGUETTE_PERM_ALLOW.")


def _parse_allow(value, home, home_p, physical):
    """LANGUETTE_PERM_ALLOW -> (extra_roots, error or None): absolute paths only."""
    roots, _, err = paths.parse_allow(value, home, home_p, physical)
    return roots, err


def _exec_perm(s, g, b):
    """The chmod, chown or chgrp that a find at g runs with -exec, even behind a
    wrapper (`-exec sudo chmod`, `-exec sh -c 'chmod ..'`), else None. Once the
    command after -exec is a wrapper, the rest of the clause is searched."""
    for i in range(g + 1, b):
        if s.k[i] != "w" or s.w[i] not in _EXEC:
            continue
        m = _CMD.search(s.w[i + 1]) if s.k[i + 1] == "w" else None
        if m:
            return m.group(1)
        if s.k[i + 1] != "w" or not _WRAPPERS.fullmatch(os.path.basename(s.w[i + 1])):
            continue
        for j in range(i + 1, b + 1):
            m = _CMD.search(s.w[j]) if s.k[j] == "w" else _PERM_IN_TEXT.search(s.q[j])
            if m:
                return m.group(1)
    return None


class _Judge:
    """Find every judged target in the command and either refuse it on sight
    or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home = cwd, home
        self.moved, self.targets, self.what = False, [], ""

    def blocked(self, raw, why):
        raise Refuse(f"`{self.what}{' ' + raw if raw else ''}` is blocked: {why}. {_WAY_OUT}")

    def target(self, s, idx):
        raw = s.w[idx]
        try:
            t = paths.resolve_target(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.blocked(raw, str(e))
        if ".git" in t.split("/"):
            self.blocked(raw, "it is inside a .git directory, the repository's own store")
        self.targets.append((t, self.what, raw))

    def perm(self, s, g, b, sweep):
        """chown, chgrp or chmod at g. `sweep`: a find -exec runs it over a tree."""
        name = _CMD.search(s.w[g]).group(1)
        recursive = ref = dashdash = False
        ops = []
        i = g + 1
        while i <= b:
            x, at, i = s.w[i], i, i + 1
            if s.k[at] != "w":
                ops.append(at)
            elif not dashdash and x == "--":
                dashdash = True
            elif not dashdash and x.startswith("--"):
                # GNU getopt_long takes any unambiguous prefix: --rec is --recursive.
                if len(x) >= 3 and "--recursive".startswith(x):
                    recursive = True
                elif x == "--reference":
                    ref, i = True, i + 1
                elif x.startswith("--reference="):
                    ref = True
            elif not dashdash and len(x) > 1 and x[0] == "-":
                if re.fullmatch(r"-[A-Za-z0-9]*R[A-Za-z0-9]*", x):
                    recursive = True
                # chmod's mode may begin with a dash (-x, -w): it is the first operand, not an option.
                if name == "chmod" and not ref and not ops and not _CHMOD_FLAGS.fullmatch(x):
                    ops.append(at)
            else:
                ops.append(at)
        mode = None
        if not ref and ops:
            mode = s.w[ops.pop(0)]
        world = name == "chmod" and mode is not None and bool(_WORLD.fullmatch(mode))
        if not (recursive or world or sweep):
            return
        self.what = f"{name} -R" if recursive else f"{name} {mode}" if world else f"find -exec {name}"
        if not ops:
            if sweep:
                return
            self.blocked("", "no target is visible to this hook -- xargs, brace expansion and quoted lists all "
                             "look like this. Run it on the resolved paths directly")
        for i in ops:
            self.target(s, i)

    def segment(self, s, a, b, nested):
        g, sweep = sw.cmd_index(s, a, b, _FIND, nested), False
        if g is not None:
            name = _exec_perm(s, g, b)
            if name is not None:
                sweep, self.what = True, "find -exec " + name
                starts = paths.find_starts(s, g, b)
                if not starts:
                    self.blocked("", "with no start path find sweeps the working directory")
                for i in starts:
                    self.target(s, i)
        g = sw.cmd_index(s, a, b, _CMD, nested)
        if g is not None:
            self.perm(s, g, b, sweep)

    def run(self, doc):
        scans = [(doc.scan(t), nested) for t, nested in doc.texts()]
        self.moved = paths.moves_directory(scans)
        paths.judge_segments(self, scans)


_MALFORMED = ("LANGUETTE_PERM_ALLOW is malformed ({}). Recursive chown, chgrp and chmod, and "
              "chmod 777, are blocked until it is fixed or unset; other commands run. It must be a "
              "colon-separated list of absolute paths (/srv/scratch), using only letters, digits and "
              ". _ @ + - ; a path may not hold a . or .. segment and may not be / or $HOME.")


def _verdict(targets, home, physical, extra_roots=()):
    roots = paths.own_roots(home, physical, extra_roots)
    for abs_, what, raw in targets:
        if not paths.under(abs_, roots):
            return deny(say("perm_not_allowed", what=what, raw=raw, abs_=abs_, way_out=_WAY_OUT))
        phys = physical(abs_)
        if phys != abs_ and not paths.under(phys, roots):
            return deny(say("symlink_out", what=what, raw=raw, abs_=abs_, phys=phys, way_out=_WAY_OUT))
    return None


def check(doc):
    return (yield from paths.check_targets(doc, NAME, _Judge, "LANGUETTE_PERM_ALLOW", _parse_allow, _MALFORMED,
                                           _verdict))
