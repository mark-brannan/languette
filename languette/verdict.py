"""The verdicts a guard returns, in Claude Code's hookSpecificOutput words,
and the facts a guard may ask for.

A guard's check returns deny(reason), ask(reason), context(text), allow(input)
or None; or it is a generator that yields Needs and Acts and returns one of those.
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
        read          path [limit]        -> a regular file's text; ValueError past `limit` bytes
        path          op, path            -> os.path.<op>(path): isdir, isfile, islink, exists,
                                             lexists, realpath; or executable
        cwd                               -> the hook process's own directory
        ruleset-cache slug, branch        -> (mtime, text), or None
        clock                             -> seconds since the epoch
        worktree      op, *args           -> guard-worktrees' per-session record: arrive rec, top
                                             -> (usable, adopt); recorded rec, top -> bool;
                                             scratchpad sid -> dir, or None
        claim         {label: runs}       -> ({label: [AskUserQuestion ids]}, spent)
        run           cwd, timeout, *argv -> (exit code, stdout, stderr); raises on a
                                             program that cannot start or times out
        door          op, session, call   -> guard-github-issues' per-session door, claim or take
                                             (world.World._door)
        send-state    session             -> {"subagents": [names, ids], "read": tool or None}

    claim, door and worktree arrive write as they read, under one lock or rename:
    they move with the approval spend (#84).
    """

    __slots__ = ("kind", "args")

    def __init__(self, kind, *args):
        self.kind, self.args = kind, args

    def __repr__(self):
        return f"{type(self).__name__}({self.kind!r}{''.join(', ' + repr(a) for a in self.args)})"


class Act(Need):
    """A write a guard asks for. The runner sends None back at once and does
    every Act through languette.world after the verdict, whatever the verdict;
    one that fails changes nothing.

        ruleset-keep    slug, branch, text  the ruleset cache's entry
        send-keep       session, op, arg    guard-cross-session-send's state (op: clear, read, names)
        worktree-keep   rec, top            a toplevel into guard-worktrees' per-session record
        worktree-leave  rec, text           what the next call may adopt (<rec>.arrive)
        door-open       session             guard-github-issues' door, fresh; any claim dropped
        door-spend      session             that door and its claim, gone
    """

    __slots__ = ()


def deny(reason):
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def ask(reason):
    return {"permissionDecision": "ask", "permissionDecisionReason": reason}


def context(text):
    return {"additionalContext": text}


def allow(updated_input):
    """Let the call run with its input rewritten to `updated_input`."""
    return {"permissionDecision": "allow", "updatedInput": updated_input}
