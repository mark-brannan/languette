"""guard-scheduled-jobs: features/guard-scheduled-jobs.feature is the spec.

Blocks `crontab -r`, which deletes the whole crontab with no undo: at command
position, behind a wrapper, and with r in a short-option cluster (`-ir`).
Its one rule is a command rule (docs/design/guard-rules.md), matched by scan's
command-rule matcher.
"""

from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, judged

NAME = "guard-scheduled-jobs"

RULES = [{"id": "crontab-wipe", "match": {"cmd": "crontab", "flags": ["r"]}, "action": "deny"}]


def judge(doc):
    """The deny reason for the command, or None."""
    for rule in RULES:
        # PROSE, not PROSE_PROCESS, and no launchers: `pkill crontab -r` is denied
        # and `sh -c "npx crontab -r"` passes, as before the shared matcher.
        n, _ = sw.matches(doc, rule["match"], prose=sw.PROSE, launchers=False)
        if n and rule["action"] == "deny":
            return say("cron_remove", way_user=WAY_USER)
    return None


def check(doc):
    return judged(doc, NAME, judge)
