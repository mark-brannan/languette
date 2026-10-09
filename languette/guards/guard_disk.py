"""guard-disk: features/guard-disk.feature is the spec.

Blocks the commands that overwrite a disk: `dd` with of= under /dev, mkfs*,
wipefs and shred on anything but the agent's own area, and a redirection or
tee onto a disk device. A target this guard cannot
resolve to one allowed path is denied on sight, with a reason naming what it
saw.
"""

import json
import os
import re

from languette import paths
from languette import scan as sw
from languette.verdict import Need, Refuse, deny

NAME = "guard-disk"

_DD = re.compile(r"(?:^|/)dd\Z")
_MKFS = re.compile(r"(?:^|/)(?:mkfs(?:\.[A-Za-z0-9]+)?|mke2fs|mkswap|mkdosfs)\Z")
_WIPE = re.compile(r"(?:^|/)(?:wipefs|shred)\Z")
_TEE = re.compile(r"(?:^|/)tee\Z")
_DEVICE = re.compile(r"/dev/(?:sd|hd|vd|xvd|nvme|disk|rdisk|mmcblk|mtdblock|loop|md|dm-|mapper/|sr|mem|kmem|port|ram|nbd|zram)")
_DEV_OK = ("/dev/null", "/dev/zero", "/dev/full", "/dev/stdout", "/dev/stderr", "/dev/tty")
_VALUE_OPTS = {
    "mkfs": ("-t", "-L", "-U", "-b", "-i", "-I", "-N", "-m", "-E", "-O", "-d", "-r", "-T", "-C", "-g", "-G", "--type"),
    "wipe": ("-t", "-o", "-n", "-s", "--types", "--offset", "--iterations", "--size", "--random-source"),
}
_CD = re.compile(r"(?:cd|pushd|popd)\Z")
_CD_FLAGS = ("-P", "-L", "-e", "-@", "--")

_WAY_OUT = ("Work on an image file in /tmp or the scratchpad instead; a real disk is the user's to write, so "
            "hand them the exact command.")


def redirect_targets(text):
    """The words an unquoted `>`, `>>`, `&>` or `>|` in `text` writes to, quotes
    removed; a dup like 2>&1 has none. Heredoc bodies are not in `text`."""
    out, i, L = [], 0, len(text)
    while i < L:
        c = text[i]
        if c == "\\":
            i += 2
        elif c == "'":
            j = text.find("'", i + 1)
            i = L if j < 0 else j + 1
        elif c == '"':
            i += 1
            while i < L and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;|&()"):
            j = text.find("\n", i)
            i = L if j < 0 else j
        elif c == ">":
            i += 1
            while i < L and text[i] in ">|":
                i += 1
            if i < L and text[i] == "&":
                i += 1
                if i < L and text[i] in "0123456789-":
                    continue
            while i < L and text[i] in " \t":
                i += 1
            word = ""
            while i < L and text[i] not in " \t\n;|&()<>":
                d = text[i]
                if d == "\\":
                    word += text[i + 1:i + 2]
                    i += 2
                elif d in "'\"":
                    j = text.find(d, i + 1)
                    j = L if j < 0 else j
                    word += text[i + 1:j]
                    i = j + 1
                else:
                    word += d
                    i += 1
            if word:
                out.append(word)
        else:
            i += 1
    return out


class _Judge:
    def __init__(self, cwd, home):
        self.cwd, self.home, self.homeN = cwd, home, paths.normalize(home)
        self.moved, self.dev_moved, self.targets = False, False, []

    def refuse(self, what, why):
        raise Refuse(f"`{what}` is blocked: {why}. {_WAY_OUT}")

    def lands_in_dev(self, s, a, b):
        """A cd (or `env -C`, `sudo -D`) in a..b that may leave the working directory under /dev, or
        whose target the hook cannot resolve."""
        g = sw.cmd_index(s, a, b, _CD, True)
        if g is not None:
            ops = [i for i in range(g + 1, b + 1) if not (s.k[i] == "w" and s.w[i] in _CD_FLAGS)]
            if not ops:
                return s.w[g] != "cd"
            x, i = s.w[ops[0]], ops[0]
            if s.k[i] == "q" or x == "-" or re.search(r"[$`*?\[{}]", x) or re.match(r"~[^/]", x):
                return True
            if x == "~" or x.startswith("~/"):
                x = self.home + x[1:]
            p = paths.lexical(x if x.startswith("/") else self.cwd + "/" + x)
            if p == "/dev" or p.startswith("/dev/"):
                return True
        return paths.chdir_wrapper(s, a, b)

    def is_device(self, raw, what):
        """A written path is a disk device as the filesystem would see it: `..`, `.` and `//` applied."""
        if not raw.startswith("/") and self.dev_moved:
            self.refuse(f"{what} {raw}", "a `cd` earlier in this command may move the working directory into /dev and the hook cannot follow it; use an absolute path")
        return bool(_DEVICE.match(paths.lexical(raw if raw.startswith("/") else self.cwd + "/" + raw)))

    def target(self, s, idx, what):
        raw = s.w[idx]
        try:
            t = paths.resolve(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.refuse(f"{what} {raw}", str(e))
        self.targets.append((t, what, raw))

    def operands(self, s, g, b, opts, numeric=False):
        out, dashdash, i = [], False, g + 1
        while i <= b:
            x, at, i = s.w[i], i, i + 1
            if s.k[at] != "w":
                out.append(at)
            elif not dashdash and x == "--":
                dashdash = True
            elif not dashdash and len(x) > 1 and x[0] == "-":
                if x in opts:
                    i += 1
            elif not (numeric and re.fullmatch(r"[0-9]+[A-Za-z]?", x)):
                out.append(at)
        return out

    def segment(self, s, a, b, nested):
        g = sw.cmd_index(s, a, b, _DD, nested)
        if g is not None:
            for i in range(g + 1, b + 1):
                x = s.w[i]
                if s.k[i] == "q" and "of=" in s.q[i]:
                    self.refuse("dd", "a quoted string with whitespace in it is not one path this hook can resolve")
                if s.k[i] != "w" or not x.startswith("of="):
                    continue
                v = x[3:]
                if not v.startswith("/") and self.dev_moved:
                    self.refuse(f"dd {x}", "a `cd` earlier in this command may move the working directory into /dev and the hook cannot follow it; use an absolute path")
                if re.search(r"[*?\[{}$`]", v):
                    self.refuse(f"dd {x}", "a glob, brace or variable could name a disk device")
                p = paths.lexical(v if v.startswith("/") else self.cwd + "/" + v)
                if (p == "/dev" or p.startswith("/dev/")) and p not in _DEV_OK and not p.startswith("/dev/fd/"):
                    self.refuse(f"dd {x}", f"{p} is a device node, and dd overwrites whatever is on it")
        g = sw.cmd_index(s, a, b, _MKFS, nested)
        if g is not None:
            what = os.path.basename(s.w[g])
            ops = self.operands(s, g, b, _VALUE_OPTS["mkfs"], numeric=True)
            if not ops:
                self.refuse(what, "no device or image file is visible to this hook")
            for i in ops:
                self.target(s, i, what)
        g = sw.cmd_index(s, a, b, _WIPE, nested)
        if g is not None:
            what = os.path.basename(s.w[g])
            ops = self.operands(s, g, b, _VALUE_OPTS["wipe"])
            if not ops:
                self.refuse(what, "no target is visible to this hook -- xargs and quoted lists look like this. "
                                  "Run it on the resolved paths directly")
            for i in ops:
                self.target(s, i, what)
        g = sw.cmd_index(s, a, b, _TEE, nested)
        if g is not None:
            for i in range(g + 1, b + 1):
                if s.k[i] == "w" and self.is_device(s.w[i], "tee"):
                    self.refuse(f"tee {s.w[i]}", "it writes onto a disk device")

    def run(self, text):
        texts = sw.texts_of(sw.strip_heredocs(text))
        scans = [(sw.Scan(t), nested) for t, nested in texts]
        self.moved = paths.moves_directory(scans)
        self.dev_moved = any(a <= b and self.lands_in_dev(s, a, b) for s, _ in scans for a, b in s.segments())
        for (t, _), (s, nested) in zip(texts, scans):
            for target in redirect_targets(t):
                if self.is_device(target, ">"):
                    self.refuse(f"> {target}", "it writes onto a disk device")
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
        cwd = yield Need("cwd")
    home = env.get("HOME", "")
    if not home.startswith("/"):
        return deny("guard-disk: $HOME is not an absolute path, cannot resolve targets")

    judge = _Judge(cwd, home)
    try:
        judge.run(cmd + "\n")
    except Refuse as e:
        return deny(f"guard-disk: {e}")

    roots = yield from paths.own_roots(home)
    for abs_, what, raw in judge.targets:
        if not paths.under(abs_, roots):
            kind = "a device node" if abs_.startswith("/dev/") else "outside the scratchpad, /tmp and agent worktrees"
            return deny(f"guard-disk: `{what} {raw}` is blocked: {abs_} is {kind}. {_WAY_OUT}")
        phys = yield from paths.physical(abs_)
        if phys != abs_ and not paths.under(phys, roots):
            return deny(f"guard-disk: `{what} {raw}` is blocked: {abs_} resolves through a symlink to {phys}, "
                        f"which is not the scratchpad, /tmp or an agent worktree. {_WAY_OUT}")
    return None
