"""guard-scheduled-jobs: the Python guard (it replaced hooks/guard-scheduled-jobs.sh).

Blocks `crontab -r`, which deletes the whole crontab with no undo: at command
position, behind a wrapper, and with r in a short-option cluster (`-ir`).
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-scheduled-jobs"

_CRON = re.compile(r"(?:^|/)crontab\Z")
_WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


def judge(text):
    """The deny reason for `text`, or None."""
    for t, nested in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, _CRON, nested) if a <= b else None
            if g is not None and any(s.k[i] == "w" and re.fullmatch(r"-[A-Za-z]*r[A-Za-z]*", s.w[i])
                                     for i in range(g + 1, b + 1)):
                return f"`crontab -r` is blocked: it deletes the whole crontab with no undo. {_WAY_USER}"
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
