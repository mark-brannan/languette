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
    # A credential in the command.
    "secrets_way_out": (
        "Keep the value out of the command: read it from the environment (`\"$TOKEN\"`), a file "
        "(`--password-file`, `gh auth login --with-token < file`) or the tool's own credential store, so the "
        "secret is not in the transcript or in what the command writes."
    ),
    "secrets_config": (
        "guard-secrets: {config} is {err}, so the project's secret patterns cannot be read. "
        "Fix the file; until then every Bash command is denied."
    ),
    "secrets_shape": (
        "guard-secrets: the command holds what looks like a credential: {found}. "
        "A secret pasted into a command is in the transcript and in anything it writes or posts. {way_out}"
    ),
    "secrets_context": (
        "guard-secrets: a value here is named as a credential: {found}. "
        "If it is a real secret, say no and keep it out of the command. {way_out}"
    ),
    # A download piped into a shell.
    "pipe_to_shell_way_out": (
        "Download it to a file, read it, then run the file: `curl -fsSLo install.sh <url>`, read "
        "install.sh, `sh install.sh`. The same install, one more command, and the script has been "
        "seen before it ran."
    ),
    "pipe_to_shell": "guard-pipe-to-shell: {why} runs whatever the server sends, unread. {way_out}",
    # A recursive delete that is not a generated directory.
    "recursive_delete": (
        "`{label}` is blocked: {why}. Resolve the target yourself and spell it out: `rm -rf` on "
        "the absolute path of a generated directory (node_modules, dist, coverage, .pio ...), the "
        "scratchpad, /tmp or an agent worktree. Anything else in a repo or under $HOME is the user's -- "
        "`git status --short` / `git clean -n` show what is there; `git rm` tracked files by path and "
        "hand the rest to the user."
    ),
    # A label that waives a CI gate.
    "bypass_label": (
        "{guard}: the label `{label}` is a human's to apply, not a session's: it waives a CI gate, "
        "and a gate whose bypass the gated party can apply is not a gate. Split the change "
        "instead, or say in the PR body why it needs the waiver and leave the label for the "
        "user to add by hand."
    ),
    "bypass_label_unseen": (
        "{guard}: {unseen}, so the guard cannot tell whether it applies a bypass label "
        "({labels}). Write the label literally in the command, or leave it for the "
        "user to add."
    ),
    # A GitHub comment that is not signed as an agent's.
    "signature_not_regex": (
        "{guard}: the signed_comments_signature setting `{pattern}` is not a regular expression "
        "({err}), so no comment's signature can be checked. Fix the setting, or empty it for the default."
    ),
    "signature_unread": "{guard}: {why}\n\n{signed}",
    "signature_opaque_body": (
        "{what}, so its signature cannot be checked before it is posted. Write it literally, "
        "in a heredoc in the same command, or in a file and pass --body-file <path>."
    ),
    "signature_body_file": (
        "the body file {why}, so its signature cannot be checked before it is posted. Spell "
        "out the path, or write the file from a heredoc in this same command (cat > PATH <<'EOF' "
        "... EOF), or put the body in a heredoc and pass --body-file -."
    ),
    "signature_input_not_json": (
        "the --input payload is not JSON this hook can read, so its signature cannot be "
        "checked. Write the JSON literally in a heredoc fed to --input -."
    ),
    "signature_graphql_not_literal": (
        "the graphql body is not a string literal this hook can read, so its signature "
        "cannot be checked. Pass it as a variable (-f body=..., or from a heredoc)."
    ),
    "signature_graphql_variable": (
        "the graphql {field} comes from ${name}, which this hook cannot read, so its "
        "signature cannot be checked. Pass the body as its own variable, -f body=... or "
        "from a heredoc in the same command."
    ),
    "signature_wrong": (
        "{guard}: this posts a GitHub comment under the user's login, so it must be signed as an agent's, "
        "or a reader takes it for the user's own words. Here {problems}. {shape}"
    ),
}


def say(code, **blanks):
    """The message `code` with its blanks filled; a blank left out is a KeyError."""
    return MESSAGES[code].format(**blanks)
