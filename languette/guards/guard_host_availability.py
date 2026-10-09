"""guard-host-availability: features/guard-host-availability.feature is the spec.

Blocks the commands that take the machine down: shutdown, reboot, halt and
poweroff, at command position or as the one-word script of `sh -c`, the
fork-bomb shape, and `systemctl stop|restart` of a host service (the user's
own `--user` manager and a remote `-H`/`-M` host are not the host).
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-host-availability"

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_CTL = re.compile(r"(?:^|/)systemctl\Z")
_CTL_OTHER = {"--user", "-H", "--host", "-M", "--machine"}
_CTL_ARG = {"-t", "--type", "-p", "--property", "-s", "--signal", "-n", "--lines", "-o", "--output", "-T"}
_FORK = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&")
_WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


def _power(s, a, b):
    g = sw.cmd_index(s, a, b, _POWER, True)
    if g is None:                              # `sh -c reboot`: a one-word script is not a nested text
        g = next((i for i in range(a + 1, b + 1) if s.k[i] == "w" and _POWER.search(s.w[i])
                  and re.fullmatch(r"-[A-Za-z]*c", s.w[i - 1])), None)
    return None if g is None else os.path.basename(s.w[g])


def _service_stop(s, a, b):
    """`stop` or `restart` when the segment stops a host service with systemctl, else None."""
    g = sw.cmd_index(s, a, b, _CTL, True)
    if g is None:
        return None
    words = [s.w[i] for i in range(g + 1, b + 1) if s.k[i] == "w"]
    if any(w in _CTL_OTHER or w.startswith(("--host=", "--machine=")) for w in words):
        return None
    skip = False
    for w in words:
        if skip:
            skip = False
        elif w in _CTL_ARG:
            skip = True
        elif not w.startswith("-"):
            return w if w in ("stop", "restart") else None
    return None


def judge(text):
    """The deny reason for `text`, or None."""
    for t, _ in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        for a, b in segs:
            what = _power(s, a, b)
            if what:
                return f"`{what}` is blocked: it takes the machine down, with the user's session on it. {_WAY_USER}"
        for a, b in segs:
            verb = _service_stop(s, a, b)
            if verb:
                return (f"`systemctl {verb}` is blocked: it takes a host service down, with the user's session "
                        f"possibly on it. {_WAY_USER}")
        # The fork bomb is raw text, so a commit message that quotes it must not trip it:
        # only a text with a segment that is not led by a prose consumer is read.
        if any(sw.seg_cmd(s, a, b) is None or s.w[sw.seg_cmd(s, a, b)] not in sw.PROSE or s.shellseg
               for a, b in segs) and _FORK.search(t):
            return ("`:(){ :|:& };:` is blocked: that is the fork-bomb shape, a function that pipes itself into "
                    f"itself in the background, and it freezes the machine. {_WAY_USER}")
    return None


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    why = judge(cmd + "\n")
    return deny(f"{NAME}: {why}") if why else None
