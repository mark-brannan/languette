"""The verdicts a guard returns, in Claude Code's hookSpecificOutput words.

A guard's check returns deny(reason), context(text) or None. Refuse is how a
guard's internals say "deny, for this reason" from deep inside a walk; check
catches it and returns deny. Standard library only.
"""


class Refuse(Exception):
    pass


def deny(reason):
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def context(text):
    return {"additionalContext": text}
