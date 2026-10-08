"""The verdicts a guard returns, in Claude Code's hookSpecificOutput words,
and the facts a guard may ask for.

A guard's check returns deny(reason), ask(reason), context(text), allow(input)
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
        pr-list       cwd, *argv          -> stdout of argv run in cwd, stripped, or None
        which         name                -> the program's path on the env's PATH, or None
        read          path                -> the file's text
        path          op, path            -> os.path.<op>(path): isdir, isfile, islink, exists,
                                             lexists, realpath; or executable
        cwd                               -> the hook process's own directory
        ruleset-cache slug, branch        -> (mtime, text), or None
        ruleset-keep  slug, branch, text  -> None, once written
        clock                             -> seconds since the epoch
        worktree      op, *args           -> guard-worktrees' per-session record: arrive rec, top
                                             -> (usable, adopt); recorded rec, top -> bool; keep rec, top
                                             and leave rec, text -> None; scratchpad sid -> dir, or None
        claim         {label: runs}       -> ({label: [AskUserQuestion ids]}, spent)
        run           cwd, timeout, *argv -> (exit code, stdout, stderr); raises on a
                                             program that cannot start or times out
        door          op, session[, call] -> guard-github-issues' per-session door
                                             (world.World._door)
        send-state    session             -> {"subagents": [names, ids], "read": tool or None}
        send-keep     session, op, arg    -> None, once written (op: clear, read, names)
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


def allow(updated_input):
    """Let the call run with its input rewritten to `updated_input`."""
    return {"permissionDecision": "allow", "updatedInput": updated_input}
