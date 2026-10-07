"""guard-permissions: a port of hooks/guard-permissions.sh, whose header is the spec.

Blocks a recursive chown, chgrp or chmod (-R, --recursive, a short cluster
holding R), `chmod 777`, and `find ... -exec chown|chgrp|chmod` unless every
target, resolved against the payload's cwd and then through the filesystem,
is the agent's own: under the scratchpad, an agent worktree or /tmp, or an
absolute path named in LANGUETTE_PERM_ALLOW. Never `/`, $HOME itself, or
anything inside a .git. A target this guard cannot resolve to one allowed path
is denied on sight, with a reason naming what it saw.
"""

import json
import os
import re

from languette import paths
from languette import scan as sw
from languette.verdict import Refuse, context, deny

NAME = "guard-permissions"

_CMD = re.compile(r"(?:^|/)(chown|chgrp|chmod)\Z")
_FIND = re.compile(r"(?:^|/)find\Z")
_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_WRAPPERS = re.compile(r"(?:sudo|doas|env|nice|nohup|timeout|command|exec|time|ionice|stdbuf|sh|bash|dash|zsh|ksh)\Z")
_PERM_IN_TEXT = re.compile(r"(?:^|[^A-Za-z0-9_./-])(chmod|chown|chgrp)(?![A-Za-z0-9_-])")
_CHMOD_FLAGS = re.compile(r"-[Rcfv]+\Z")
_WORLD = re.compile(r"(?:0*777|(?:a|ugo)[+=]rwx)\Z")
_ALLOW_CHARS = re.compile(r"[A-Za-z0-9._@+/-]*")

_WAY_OUT = ("Spell the files out: chmod or chown the paths themselves, without -R (`git ls-files <dir>` lists "
            "what a sweep would touch), or sweep inside the scratchpad, /tmp or an agent worktree. Anything "
            "else is the user's; a sweep over a project tree is theirs to run, or to allow with "
            "LANGUETTE_PERM_ALLOW.")


def _parse_allow(value, home, home_p):
    """LANGUETTE_PERM_ALLOW -> (extra_roots, error or None): absolute paths only."""
    roots = []
    for ent in value.split(":"):
        if ent == "":
            return roots, "an empty entry"
        if not _ALLOW_CHARS.fullmatch(ent):
            return roots, f"unsupported character in '{ent}'"
        if not ent.startswith("/"):
            return roots, f"'{ent}' is not an absolute path"
        if ent.endswith(("/.", "/..")) or "/./" in ent or "/../" in ent or "//" in ent:
            return roots, f"'{ent}' has an empty, . or .. segment"
        if ent.endswith("/"):
            ent = ent[:-1]
        if ent in ("", home):
            return roots, f"'{ent}' is / or $HOME"
        ent_p = paths.physical(ent)
        if ent_p in ("", home, home_p):
            return roots, f"'{ent}' resolves to / or $HOME"
        roots += [ent, ent_p]
    return roots, None


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
    """What the awk half of the shell guard does: find every judged target in
    the command and either refuse it on sight or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home, self.homeN = cwd, home, paths.normalize(home)
        self.moved, self.targets, self.what = False, [], ""

    def blocked(self, raw, why):
        raise Refuse(f"`{self.what}{' ' + raw if raw else ''}` is blocked: {why}. {_WAY_OUT}")

    def target(self, s, idx):
        raw = s.w[idx]
        try:
            t = paths.resolve(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.blocked(raw, str(e))
        if t == "/" or t == self.homeN:
            self.blocked(raw, "that is " + ("the root of the filesystem" if t == "/" else "$HOME itself"))
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
                i, starts = g + 1, 0
                while i <= b and not s.w[i].startswith(("-", "!")):
                    starts += 1
                    self.target(s, i)
                    i += 1
                if not starts:
                    self.blocked("", "with no start path find sweeps the working directory")
        g = sw.cmd_index(s, a, b, _CMD, nested)
        if g is not None:
            self.perm(s, g, b, sweep)

    def run(self, text):
        texts = sw.texts_of(sw.strip_heredocs(text))
        scans = [(sw.Scan(t), nested) for t, nested in texts]
        self.moved = paths.moves_directory(scans)
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
        return deny("guard-permissions: $HOME is not an absolute path, cannot resolve targets")

    home_p = paths.physical(home)
    extra_roots, allow_err = [], None
    if env.get("LANGUETTE_PERM_ALLOW"):
        extra_roots, allow_err = _parse_allow(env["LANGUETTE_PERM_ALLOW"], home, home_p)
    allow_msg = None
    if allow_err:
        allow_msg = (f"LANGUETTE_PERM_ALLOW is malformed ({allow_err}). Recursive chown, chgrp and chmod, and "
                     "chmod 777, are blocked until it is fixed or unset; other commands run. It must be a "
                     "colon-separated list of absolute paths (/srv/scratch), using only letters, digits and "
                     ". _ @ + - ; a path may not hold a . or .. segment and may not be / or $HOME.")

    judge, refused = _Judge(cwd, home), None
    try:
        judge.run(cmd + "\n")
    except Refuse as e:
        refused = str(e)
    if refused is None and not judge.targets:
        return context("guard-permissions: " + allow_msg) if allow_msg else None
    if allow_msg:
        return deny("guard-permissions: " + allow_msg)
    if refused is not None:
        return deny(refused)

    roots = paths.own_roots(home, extra_roots)
    for abs_, what, raw in judge.targets:
        if not paths.under(abs_, roots):
            return deny(f"`{what} {raw}` is blocked: only the scratchpad, /tmp, agent worktrees and paths named "
                        f"in LANGUETTE_PERM_ALLOW may be swept, and {abs_} is none of those. {_WAY_OUT}")
        phys = paths.physical(abs_)
        if phys != abs_ and not paths.under(phys, roots):
            return deny(f"`{what} {raw}` is blocked: {abs_} resolves through a symlink to {phys}, which is not "
                        f"the scratchpad, /tmp or an agent worktree. {_WAY_OUT}")
    return None
