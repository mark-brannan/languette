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
    "cross_session_ask": (
        "{guard}: a message to {target}, which may be another of the user's sessions, "
        "leaves this one: {first_line}"
    ),
    "rd_quoted_space": "a quoted string with whitespace in it is not one path this hook can resolve",
    "rd_glob": "a glob or brace expansion could name anything",
    "rd_substitution": "a variable or command substitution could expand to anything",
    "rd_tab_newline": "it contains a tab or newline",
    "rd_dotdot": "a `..` segment steps out of the directory the name suggests",
    "rd_tilde": "only a leading `~/` is understood",
    "rd_cd_moved": (
        "a `cd` earlier in this command moves the working directory and the hook "
        "cannot follow it; use an absolute path"
    ),
    "rd_root": "that is the root of the filesystem",
    "rd_home": "that is $HOME itself",
    "rd_find_no_start": "with no start path find deletes under the working directory",
    "rd_no_target": (
        "no target is visible to this hook -- find -exec, xargs, brace expansion and "
        "quoted lists all look like this. Run rm on the resolved paths directly"
    ),
    "pipe_into": "a download piped into `{name}`",
    "pipe_substituted": "`{name}` run on a download substituted into its command line",
    "pipe_substituted_c": "`{name} -c` run on a download substituted into its command line",
    "pipe_eval": "`eval` of a download",
    "pipe_source": "`{name}` of a download",
    # A git checkout or a worktree the session does not own.
    "wt_checkout_home": (
        "{guard}: `checkout`/`switch` in $HOME switches the branch every shell and session on "
        "this machine sees until someone checks the old branch back out. Use a worktree "
        "instead:\n  {prog} worktree add -b <branch> <path> main\nthen cd into it and work there."
    ),
    "wt_git_missing_checkout": (
        "{guard}: git is missing, so a checkout/switch can't be checked against $HOME. This is a "
        "gate and fails closed."
    ),
    "wt_home_unresolved_checkout": (
        "{guard}: $HOME does not resolve, so a git checkout/switch can't be checked against it."
    ),
    "wt_repo_unclear": (
        "{guard}: can't tell which repository or work tree this git checkout/switch runs against "
        "(a --git-dir or --work-tree that doesn't resolve), so it can't be checked against "
        "$HOME. Use an absolute path."
    ),
    "wt_dir_unclear": (
        "{guard}: can't tell which directory this git checkout/switch runs in (a cd, -C or "
        "session cwd that doesn't resolve), so it can't be checked against $HOME. Use an "
        "absolute path with git -C."
    ),
    "wt_foreign": (
        "{guard}: `{word}` is inside {ft}, a git worktree this session does not own. A hand-off "
        "carries a branch, an issue and a PR -- never a directory; another session may still be "
        "running in there, and it may be archived out from under you mid-turn (an agent once "
        "lost a worktree that way).\nTo read that branch, stay here: `git log/diff/show "
        "<branch>`, `git show <branch>:<path>` -- worktrees of a repo share objects and refs.\nTo "
        "work on it, take your own worktree, one command, from anywhere: `{recipe}`, then `git "
        "merge --ff-only {branch}` inside it. If --ff-only fails, the histories have diverged: "
        "report that and stop.\nIf you made this worktree yourself in an earlier call, that is "
        "why: a worktree is yours only when the command that creates it also `cd`s into it, or "
        "it lives under your scratchpad. The recipe above does both.\nWorktree hygiene is the "
        "user's call, not a session's."
    ),
    "wt_dotdot_missing": (
        "{guard}: `{raw}` has a `..` after a directory that does not exist, so where it lands "
        "cannot be resolved. Spell the path without `..`."
    ),
    "wt_git_missing_owner": (
        "{guard}: git is missing, so worktree ownership cannot be checked. This is a gate and "
        "fails closed."
    ),
    "wt_home_unresolved_owner": (
        "{guard}: $HOME does not resolve, so worktree ownership cannot be checked. This is a "
        "gate and fails closed."
    ),
    "wt_enter_existing": (
        "{guard}: EnterWorktree(path=...) enters a worktree that already exists, with no check "
        "on whose it is -- the tool only requires that the path appear in `git worktree list`. "
        "That is how an agent once lost a worktree mid-turn: the session that owned it was "
        "archived and the directory went away underneath the session that had attached to "
        "it.\nTake your own instead, one command, from anywhere: `{recipe}`, then `git merge "
        "--ff-only <branch>` inside it to bring the branch you are resuming into your own "
        "directory. If --ff-only fails, the histories have diverged: report that and "
        "stop.\nNothing needs the other directory -- worktrees of a repo share objects and refs, "
        "so `git log/diff/show <branch>` and `git show <branch>:<path>` read it from here."
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
    # A command the user runs, not an agent: the host, the crontab, a protected service.
    "judged": "{guard}: {why}",
    "cron_remove": "`crontab -r` is blocked: it deletes the whole crontab with no undo. {way_user}",
    "rule_deny": "`{cmd}` is blocked by rule `{id}` in {file}: {why}. {way_user}",
    "rules_bad": (
        "{file} is invalid: {err}. Every Bash command is denied until it is fixed, because the guard "
        "cannot tell what it was meant to cover. Fix the file, or tell the user."
    ),
    "host_power": "`{what}` is blocked: it takes the machine down, with the user's session on it. {way_user}",
    "host_ctl": (
        "`systemctl {verb}` is blocked: it takes down the host or a service the "
        "user's session runs on. {way_user}"
    ),
    "host_sysv": "`{verb}` is blocked: it takes down a service the user's session runs on. {way_user}",
    "host_fork_bomb": (
        "`:(){{ :|:& }};:` is blocked: that is the fork-bomb shape, a function that pipes itself into "
        "itself in the background, and it freezes the machine. {way_user}"
    ),
    "protected_stop": (
        "`systemctl {verb}` is blocked: it stops a protected service, one the user's machine "
        "depends on (the protected_services setting). {way_user}"
    ),
    # Pass 5: approval-gated commands, pushes, disks, cross-session sends, duplicate PRs.
    "ask_first_cannot_look": "ask-first: {err}. A gate that cannot look fails closed: retry from the project directory.",
    "ask_first_invalid": (
        "ask-first: {path} is invalid: {err}. Every Bash command is denied until it is fixed, "
        "because the guard cannot tell which commands the repo meant to cover. Fix it with "
        "the Edit tool, or tell the user."
    ),
    "ask_first_times": "; this command runs it {n} times and has {have} unspent",
    "ask_first_cheaper": " Cheaper forms: {cheaper}.",
    "ask_first_need": (
        "`{id}` ({path}) needs the user's approval for each run{times}. Cost: {cost}.{cheaper}"
        " If a cheaper form answers the question, use it instead. Otherwise call AskUserQuestion: "
        "give the exact command (`{cmd}`), why it must run now, and the "
        "cost above, with one option labelled exactly \"{label}\" and one to skip. "
        "One approval is one run; ask again before running it again."
    ),
    "hooks_skipped": (
        "{guard}: --no-verify, -n or core.hooksPath skips this repo's hooks, and that is the user's call, not "
        "yours: a hook that blocks a commit, push or merge is telling you something. "
        "`{cmd}` skips them {runs} time{runs_s} and has {have} "
        "unspent approval{have_s}. "
        "Better, fix what the blocking hook reported and run it without the flag. "
        "If the user must have the hooks skipped, call AskUserQuestion: give the exact "
        "command and why it cannot pass the hooks, with one option labelled exactly "
        "\"{label}\" and one to decline. One approval is one run; ask again "
        "before skipping the hooks again."
    ),
    "disks_way_out": (
        "Work on an image file in /tmp or the scratchpad instead; a real disk is the user's to write, so "
        "hand them the exact command."
    ),
    "disks_refused": "`{what}` is blocked: {why}. {way_out}",
    "disks_blocked": "`{what} {raw}` is blocked: {abs_} is {kind}. {way_out}",
    "cross_session_way_out": (
        "Ask the user to send it themselves, or from a session that has not read untrusted content; "
        "/clear starts this one afresh."
    ),
    "cross_session_deny": (
        "{guard}: a message to {target} is blocked: {why}, and in "
        "{mode} no prompt can show the user what leaves the "
        "session. {way_out}"
    ),
    "ruleset_admin": (
        "guard-bypass-ruleset: `gh pr merge --admin` merges past the PR's required reviews and checks on "
        "the user's bypass. Merge without --admin, or with --auto to merge once the checks pass. "
        "Bypassing is the user's to do, from their own terminal."
    ),
    "ruleset_head_unknown": (
        "guard-bypass-ruleset: this {prog} push sends the current branch, and the hook can't "
        "tell which branch that is (another directory, or a detached HEAD), so it can't check "
        "whether the push goes around a rule that requires a pull request."
    ),
    "ruleset_repo_unknown": (
        "guard-bypass-ruleset: this pushes to `{branch}` through remote `{remote}`, in a repository the "
        "hook can't find (a cd or -C it can't follow, or GIT_DIR), so it can't ask GitHub whether "
        "`{branch}` requires a pull request. The agent runs on your credentials, so it can use your "
        "bypass."
    ),
    "ruleset_needs_pr": (
        "guard-bypass-ruleset: `{branch}` on {slug} requires a pull request, and this push would go "
        "around it on the user's bypass. Push a branch and open a PR. A direct push is the user's "
        "to make, from their own terminal."
    ),
    "ruleset_github_silent": (
        "guard-bypass-ruleset: this pushes to `{branch}` on {slug}, and GitHub couldn't say "
        "whether `{branch}` requires a pull request (gh missing, signed out, offline or "
        "an error):\n  gh api repos/{slug}/rules/branches/{branch_q}\n"
        "The agent runs on your credentials, so it can use your bypass."
    ),
    "ruleset_refused": (
        "guard-bypass-ruleset: {refused}, so the hook can't check whether it goes around a rule that "
        "requires a pull request. The agent runs on your credentials, so it can use your bypass."
    ),
    "dup_body_opaque": (
        "the body is built at run time ({v}) and no heredoc in this command feeds it, so its "
        "text cannot be checked for an issue it closes. Write it literally, in a heredoc in the "
        "same command, or in a file and pass --body-file <path>."
    ),
    "dup_body_stdin": (
        "the body comes from stdin (--body-file -) and there is no heredoc in the command, so "
        "it cannot be checked. Put the text in a heredoc in the same command, or in a file and "
        "pass --body-file <path>."
    ),
    "dup_body_file": (
        "--body-file {v} {got}, so the body cannot be checked for an issue it closes. Write "
        "it to that path from a heredoc in this same command, or create the file in an "
        "earlier command and retry; spell the path out, since a variable set in an earlier "
        "command is invisible here."
    ),
    "dup_body_rewritten": (
        "--body-file {v} is changed again in this same command (written {n} times), so neither "
        "a heredoc nor the file on disk is the text gh sends. Write the body to that path from "
        "one heredoc and nothing else in this command, or write the file in an earlier command "
        "and retry."
    ),
    "dup_body_not_heredoc": (
        "--body-file {v} is changed in this same command, and not from a heredoc, so the file "
        "on disk is not yet the text gh sends. Write the body to that path from a heredoc in "
        "this command, or write the file in an earlier command and retry."
    ),
    "dup_repo_unknown": (
        "{guard}: this PR would close #{n}, and the hook can't tell which repo it is opened "
        "on (no --repo, and the working directory's origin is not on github.com, or a cd "
        "moves it), so it can't check whether an open PR already references #{n}. Pass "
        "--repo owner/name, or read the issue first."
    ),
    "dup_github_silent": (
        "{guard}: this PR would close {repo}#{n}, and GitHub couldn't say whether an open PR "
        "already references it (gh missing, signed out, offline, an error, or a "
        "timeline past {page} events):\n"
        "  gh api repos/{repo}/issues/{n}/timeline\n"
        "Read the issue before opening a second PR on it."
    ),
    "dup_open": (
        "PR {named} is open and already references {issue}, which this PR would close "
        "too, so this command is blocked. If this PR replaces it, close "
        "{pr} first or say `Supersedes {pr}` in this body. If both "
        "are wanted, drop the closing keyword here and link the issue in prose."
    ),
}


def say(code, **blanks):
    """The message `code` with its blanks filled; a blank left out is a KeyError."""
    return MESSAGES[code].format(**blanks)
