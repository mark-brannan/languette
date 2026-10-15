"""guard-scheduled-jobs: features/guard-scheduled-jobs.feature is the spec.

Blocks `crontab -r`, which deletes the whole crontab with no undo: at command
position, behind a wrapper, and with r in a short-option cluster (`-ir`).
"""

import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, judged

NAME = "guard-scheduled-jobs"

_CRON = re.compile(r"(?:^|/)crontab\Z")


def judge(doc):
    """The deny reason for the command, or None."""
    for t, nested in doc.texts():
        s = doc.scan(t)
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, _CRON, nested) if a <= b else None
            if g is not None and any(s.k[i] == "w" and re.fullmatch(r"-[A-Za-z]*r[A-Za-z]*", s.w[i])
                                     for i in range(g + 1, b + 1)):
                return say("cron_remove", way_user=WAY_USER)
    return None


def check(doc):
    return judged(doc, NAME, judge)
