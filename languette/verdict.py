"""The verdicts a guard returns, in Claude Code's hookSpecificOutput words,
and the facts a guard may ask for.

A guard's check returns deny(reason), ask(reason), context(text), spend(wants)
or None; or it is a generator that yields Needs and returns one of those.
Refuse is how a guard's internals say "deny, for this reason" from deep inside
a walk; check catches it and returns deny. Standard library only.
"""


class Refuse(Exception):
    pass


class Need:
    """A fact a guard cannot read from the payload or env: its kind and arguments.
    The runner answers it through languette.world and sends the answer back into
    the guard; a fact that cannot be had is thrown in as the exception world raised.

        git           prog, cwd, *argv    -> stdout, stripped, or None
        gh-api        path                -> (status, body), or (None, None)
        read          path                -> the file's text
        path          op, path            -> os.path.<op>(path): isdir, lexists, realpath
        cwd                               -> the hook process's own directory
        ruleset-cache slug, branch        -> (mtime, text), or None
        ruleset-keep  slug, branch, text  -> None, once written
        clock                             -> seconds since the epoch
        approvals     labels              -> {label: [unspent AskUserQuestion ids]}
    """

    __slots__ = ("kind", "args")

    def __init__(self, kind, *args):
        self.kind, self.args = kind, args

    def __repr__(self):
        return f"Need({self.kind!r}{''.join(', ' + repr(a) for a in self.args)})"


def deny(reason):
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def ask(reason):
    return {"permissionDecision": "ask", "permissionDecisionReason": reason}


def context(text):
    return {"additionalContext": text}


def spend(wants, finding=None):
    """`finding`, or no objection, that spends `wants` ({approve_label: runs}) once
    the verdict is in. The runner spends only when the verdict is not a deny."""
    return {**(finding or {}), "spend": dict(wants)}
