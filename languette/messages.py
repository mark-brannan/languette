"""Every sentence a guard says to the agent or the person, in one place.

A guard names a message by code and fills its blanks: `say("loop", guard=NAME,
what=..., then=...)`. The text lives only here, so it can be read whole, worded
with one voice and reviewed as a diff. tests/test_messages.py holds the codes and
their blanks to the call sites. Standard library only.
"""

MESSAGES = {
    # A gate that cannot run its check denies rather than guess.
    "payload_unreadable": "languette: unreadable hook payload ({err})",
    "no_cwd": (
        "languette: the hook payload has no working directory, or only a relative one, so no path in "
        "the call can be resolved. This is a gate and fails closed."
    ),
    "unknown_guard": (
        "languette: no guard is named {name}, so this hook checks nothing. This is a gate and fails "
        "closed: reinstall the plugin, or copy the entry again from hooks/hooks.json"
    ),
    "guard_crashed": "{guard}: guard crashed ({kind}: {err}), cannot inspect the command",
    "home_not_absolute": "{guard}: $HOME is not an absolute path, cannot resolve targets",
    "too_many": (
        "require-well-formed: this command is too big to check: {err}. Nothing ran. "
        "Every quoted string that may run as shell, and every $( ) inside double quotes, "
        "is one; the guards read only so many. Split it into several smaller commands, "
        "or put the script in a file and run that"
    ),
    "too_deep": (
        "require-well-formed: this command is too big to check: {err}. Nothing ran. "
        "Every $( ), ( ), {{ }}, backtick, if, case and do adds the depth it stands at, "
        "and so does every &&, || and | (a chain nests one level per operator). "
        "Split it into several smaller commands, or nest less"
    ),
    "unparsed": (
        "require-well-formed: this command does not parse ({rung}: {err}). Nothing ran: "
        "bad input is a deny; fix the syntax and run it again"
    ),
    # A command that needs the user's approval for each run, found in a loop or not checkable.
    "loop": (
        "{guard}: {what} inside a loop, xargs, parallel or watch runs an unknown number of times, "
        "and each run needs its own approval. {then}"
    ),
    "loop_hooks": (
        "{guard}: skipping the hooks inside a loop, xargs, parallel or watch skips the hooks an "
        "unknown number of times, and each run needs its own approval. Fix what the blocking "
        "hook reported, or run it once, on its own, after asking."
    ),
    "transcript_unreadable": (
        "{guard}: cannot read the session transcript to look for the user's approval, or "
        "record it as spent ({err}), so `{cmd}` is denied. {then}"
    ),
    # A target path outside the places an agent may write.
    "symlink_out": (
        "`{what} {raw}` is blocked: {abs_} resolves through a symlink to {phys}, which is not "
        "the scratchpad, /tmp or an agent worktree. {way_out}"
    ),
}


def say(code, **blanks):
    """The message `code` with its blanks filled; a blank left out is a KeyError."""
    return MESSAGES[code].format(**blanks)
