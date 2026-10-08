"""guard-host-availability: the commands that take the machine down.

No coding task has a use for any of them; a user who wants one runs it.

Denied outright:
  - shutdown, reboot, halt, poweroff -- at command position, behind sudo,
    env, nohup ... and their options, and as the one-word script of `sh -c`
  - the fork-bomb shape: a function that pipes itself into itself in the
    background (`:(){ :|:& };:`, under any name)

Out of scope, by design (an accident guard, not a sandbox): `systemctl
reboot`, `init 6`, a power command behind a wrapper option that takes a
value (`sudo -u root reboot`), and what a script or an interpreter one-liner
does.

The fork-bomb pattern reads raw text, so a quoted string that mentions it
(`git commit -m "..."`, `echo '...'`) passes: it is read only in a text that
has a segment not led by a prose consumer.

Scanning is languette/scan.py's (read its docstring). This is a GATE, so it
fails closed: an unreadable payload or a crash here is a deny (run.py), and
the hooks.json wrapper denies when python3 or run.py is missing.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-host-availability"

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_FORK = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&")
_WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


def _power(s, a, b):
    g = sw.cmd_index(s, a, b, _POWER, True)
    if g is None:                              # `sh -c reboot`: a one-word script is not a nested text
        g = next((i for i in range(a + 1, b + 1) if s.k[i] == "w" and _POWER.search(s.w[i])
                  and re.fullmatch(r"-[A-Za-z]*c", s.w[i - 1])), None)
    return None if g is None else os.path.basename(s.w[g])


def judge(text):
    """The deny reason for `text`, or None."""
    for t, _ in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        for a, b in segs:
            what = _power(s, a, b)
            if what:
                return f"`{what}` is blocked: it takes the machine down, with the user's session on it. {_WAY_USER}"
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
