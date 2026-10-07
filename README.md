**Languette**: sharp hooks need strong guards.

*A deterministic check against risky actions by coding agents.*

![Jacques Callot, Drill with halberds (NGV 32320, public domain)](assets/callot-drill-with-halberds.jpg)

Before a coding agent runs a shell command, a languette guard reads it and
answers: allow, ask, or deny. No model decides, and nothing is run to decide.

*Languette* is French for "little tongue". On a halberd it is the strip of
iron that runs down the shaft from the head, so a stray blow can't cut through
the pole. These guards are that strip, between an agent's sharp tools and
your work.

It's also a pun. Shell is a little language, and languette listens for the
few words in it that can do damage. When it hears one, it tells the agent
"hold your tongue!"

> *"The wise speak only of what they know, Gríma son of Gálmód. A witless worm have you become. Therefore be silent, and keep your forked tongue behind your teeth. I have not passed through fire and death to bandy crooked words with a serving-man till the lightning falls."*
— **Gandalf**, in J.R.R Tolkein's *The Two Towers*, Book 3, Chapter 6

## Install

The guards run as `PreToolUse` hooks in Claude Code today (`guard-github-issues` also
runs on `UserPromptSubmit`, which opens its door); other agent hosts
are planned ([#5](https://github.com/mark-brannan/languette/issues/5)).

```
/plugin marketplace add mark-brannan/languette
/plugin install languette@languette
```

It needs:

- `python3`, standard library only, for every `run.py` guard (`ask-first`,
  `guard-bypass-hooks`, `guard-bypass-labels`, `guard-infra`, `guard-recursive-delete`,
  `guard-unparsable`);
- `jq` and a POSIX `awk`, for the shell guards, until a real shell parser replaces them
  ([#4](https://github.com/mark-brannan/languette/issues/4), planned);
- `gh`, for `guard-git-stacked-base` and `guard-bypass-ruleset`.

Without the plugin system, see [Installing by hand](#installing-by-hand).

## The guards

Each guard denies one class of command:

- [`guard-unparsable`](features/guard-unparsable.feature): a Bash command the shell
  parser refuses (`shfmt`, else `bash -n`), denied whole with its line and
  column; the other guards skip it
- [`guard-recursive-delete`](#allowing-more-for-guard-recursive-delete): a recursive `rm` or
  `find -delete` outside a generated or agent-owned directory
- [`guard-permissions`](features/guard-permissions.feature): recursive `chmod`,
  `chown`, `chgrp` or `chmod 777` outside agent-owned or
  `LANGUETTE_PERM_ALLOW` directories
- [`guard-pipe-to-shell`](features/guard-pipe-to-shell.feature): `curl u | sh`
- [`guard-disk`](features/guard-disk.feature): `dd`, `mkfs`, `wipefs`,
  `shred` onto disks
- [`guard-host-availability`](features/guard-host-availability.feature):
  shutdown, reboot, fork bomb
- [`guard-scheduled-jobs`](features/guard-scheduled-jobs.feature): `crontab -r`
- [`guard-git-work-loss`](hooks/guard-git-work-loss.sh): `add -A`, `commit -a`,
  `stash pop`, force-push, `reset --hard` and other moves that throw work away
- [`guard-git-stacked-base`](hooks/guard-git-stacked-base.sh): deleting a
  remote branch an open PR is based on (GitHub silently closes the PR)
- [`guard-bypass-ruleset`](languette/guards/guard_bypass_ruleset.py): a push to
  a branch GitHub says requires a pull request, or `gh pr merge --admin`; the
  agent holds your credentials, so it holds your bypass
- [`guard-github-issues`](hooks/guard-github-issues.sh): a second GitHub issue create, transfer
  or delete in one human turn, or any inside a loop
- [`guard-private-terms`](#settings-for-guard-private-terms): a term from your
  private list, posted to a public repo (off until you give it the list)
- [`guard-worktrees`](hooks/guard-worktrees.sh): opt-in; a branch switch in a `$HOME`
  that is a worktree, or a reach into another session's worktree
- [`guard-bypass-labels`](languette/guards/guard_bypass_labels.py): a session
  applying a label that waives a CI gate, such as `churn-ok`
- `guard-secrets`, `guard-protected-paths`, `guard-database` (planned)
- [`ask-first`](#ask-first): a command the repo lists as costly, until you
  approve that one run
- [`guard-bypass-hooks`](languette/guards/guard_bypass_hooks.py): `--no-verify` on commit, push,
  merge, pull, rebase or am, and `git -c core.hooksPath=`, until you approve that one run
- [`guard-infra`](languette/guards/guard_infra.py): `terraform destroy`, `kubectl delete` and
  other infrastructure destroys, until you approve that one run
- [`prose-budget-commit`](hooks/prose-budget-commit.sh): a `git commit` whose
  staged prose runs over the repo's word budgets

## The promise

**When a guard can't tell what a command it covers will do, it denies and
says why. When no rule covers a command, it says nothing.**

A variable where a path should be, a brace expansion, a quote it can't
resolve: each is a deny that names what the guard saw. The second half is a
limit, not a bug. A guard reads shell text; it does not open scripts or read
other languages. These are real verdicts, generated from the guards'
scenarios for a command run in `~/project`, and CI fails if the table drifts:

<!-- fixtures-table -->
| Command | Verdict | Why |
|---|---|---|
| `rm -rf build` | DENY | not an allowlisted generated dir |
| `rm -rf node_modules` | allow | allowlisted |
| `rm -rf "$DIR"` | DENY | unresolvable word; loud |
| `rm -rf dist{,2}` | DENY | brace expansion unresolved; loud |
| `sh -c "rm -rf build"` | DENY | nested text scanned |
| `find build -delete` | DENY | rule covers find -delete |
| `python3 -c "shutil.rmtree('build')"` | allow | no rule; silent (known gap) |
| `./cleanup.sh` | allow | no rule; silent (known gap) |
<!-- /fixtures-table -->

With `shfmt` 3.6 or later on `PATH` (else `bash -n`, which says less), the
`guard-unparsable` guard denies a command that doesn't parse.
In a replay of 101,671 agent commands, about 1 in 3,000 didn't parse, and
each [would have broken](features/guard-unparsable.feature).
Bash runs a broken command in part, the lines before the error or prose in
backticks as a command; the deny stops all of it, so the agent looks again.

## Ask first

A repo lists its expensive commands in `.languette/ask-first.json`:

```json
{"commands": [{"id": "e2e",
  "match": [{"cmd": "npm", "args": ["run", "e2e"]},
            {"cmd": "node", "script": "scripts/e2e.mjs"}],
  "cost": "> 40 minutes, using all CPU cores on a typical desktop",
  "approve_label": "Run e2e"}]}
```

When the agent tries a matching command, the guard denies it and tells the
agent to ask you first: the exact command, why now, the cost, any cheaper
form the entry lists under `"cheaper"`, and a button labelled with
`approve_label`. Click it and the next matching command runs. One click is
one run: a command that runs it twice needs two, and one in a loop or `xargs`
is denied whatever you approved. Only your click counts, never what the agent
wrote in the question.

Matching sees through wrappers: `timeout 3h npm run e2e`, `sh -c "..."`,
`pnpm exec node ./scripts/e2e.mjs` and `yarn e2e` all count, while `grep`,
`git commit -m`, `cat` and `pkill -f` that merely name the script do not. A
run hidden inside a script (`./ci.sh`) or behind a variable (`$CMD`) is not
seen.

The guard reads the nearest `.languette/ask-first.json` at or above the
command's working directory, stopping at the repo root, else the one in
`$CLAUDE_PROJECT_DIR`. With no file, it stays silent. A file that doesn't
parse, or that gives two commands the same `approve_label`, denies every
command until it is fixed, because the guard can no longer tell what the repo
meant. Spent approvals are kept beside the session transcript, in
`<transcript>.languette-ask`.

## Configuration

Every guard is on by default except `guard-worktrees`, which is opt-in. Turn
one off (or that one on) with
`/plugin configure languette@languette`,
or at install, by its name with underscores:

```
claude plugin install languette@languette --config guard_recursive_delete=false
```

A guard is skipped only when its setting is exactly `false`. Unset, empty or
anything else runs it, so a misconfiguration cannot open the gate.
`guard_worktrees` is the reverse: it runs only when its setting is exactly
`true`, so a misconfiguration leaves it off. Its two controls,
`guard_worktrees_checkout_home` and `guard_worktrees_foreign`, are each on
unless set to `false`.

### One setting per `guard-git-work-loss` rule

`guard_git_work_loss=false` skips all five rules. To keep four, turn off one:

| Setting | Rule it switches off |
| --- | --- |
| `guard_git_work_loss_blanket_staging` | `add -A`, `add .`, `commit -a` |
| `guard_git_work_loss_stash` | `stash pop`, `stash clear`, a bare `stash drop` |
| `guard_git_work_loss_force_push` | a bare force push; a force push to or delete of main |
| `guard_git_work_loss_discard` | `reset --hard`, `checkout .`, `restore .`, `clean -f` |
| `guard_git_work_loss_branch_delete` | `branch -D`, `branch --delete --force` |

### Allowing more for `guard-recursive-delete`

Built in: the generated directories `node_modules`, `dist`, `coverage` and
`.pio`, and the agent's own places, `/tmp`, `~/.local/state/claude-tmpdir`
and `~/.claude/worktrees`. To allow more, set `LANGUETTE_RM_ALLOW` to a
colon-separated list. It adds to the built-in lists and never replaces them;
unset or empty changes nothing.

```
export LANGUETTE_RM_ALLOW=build:.next:/srv/agent-area
```

- A bare name (`build`) is treated like `dist`: a directory with that name,
  anywhere below the top level of `$HOME` or `/`.
- An absolute path (`/srv/agent-area`) is treated like the scratchpad: a
  place the agent owns.
- Entries use letters, digits and `. _ @ + -` only. A path may not contain a
  `.` or `..` segment, and may not be `/` or `$HOME`.
- If the value doesn't parse (an empty entry, a glob, a space, a relative
  path with a slash), every Bash call carries a warning, and only a recursive
  `rm` or `find -delete` is denied. A typo can't stop unrelated work, and it
  can't open the gate either.

### Settings for `guard-private-terms`

| Setting | Holds | Example |
|---|---|---|
| `private_terms_file` | a text file of terms, one per line, matched case-insensitively | `~/.config/private-terms` |
| `private_repos` | repos whose posts are never scanned, comma-separated | `you/notes,you/scratch` |

Without a terms file the guard is off.

`bypass_labels` lists the labels `guard-bypass-labels` keeps for humans,
comma-separated; empty means `churn-ok,mixed-loops-ok`.

<details>
<summary>How Claude Code passes plugin settings to a hook (measured)</summary>

Claude Code hands each key to the hook as `CLAUDE_PLUGIN_OPTION_<KEY>`.
Measured on Claude Code 2.1.258, with a throwaway plugin loaded by
`--plugin-dir` and options supplied through `pluginConfigs`:

| Setting | Env in the hook |
|---|---|
| key `flag_off`, boolean `false` | `CLAUDE_PLUGIN_OPTION_FLAG_OFF=false` |
| key `flag_on`, boolean `true` | `CLAUDE_PLUGIN_OPTION_FLAG_ON=true` |
| key `camelKey`, boolean `false` | `CLAUDE_PLUGIN_OPTION_CAMELKEY=false` |
| `multiple` string `["a b","c,d"]` | `CLAUDE_PLUGIN_OPTION_LIST_VALS=a b,c,d` |
| `multiple` string `[]` | `CLAUDE_PLUGIN_OPTION_LIST_VALS=` |
| key unset, though the manifest gives a `default` | variable absent |

The name is the key upper-cased, underscores kept and camelCase not split.
Booleans arrive as the words `true` and `false`. A list is joined with a bare
comma and no escaping, so an item holding a comma can't be recovered. A
string `"false"` looks the same as a boolean `false`. A `default` did not
reach the environment under `--plugin-dir`; the installed-plugin path was not
measured, which is why the guards treat unset as on.

</details>

## Strong guards

A guard is a function, pure where it can be: the command and its context in,
a verdict out. It asks no model and runs nothing. The verdict is **deny**
with the reason, **ask**, a **warning**, or **nothing** (*allow*). What a
guard reads beyond the command, it declares:

| Guard | Reads |
|---|---|
| `guard-git-work-loss` | nothing: a pure function of the command |
| `guard-unparsable` | `shfmt`, else `bash -n`, which runs nothing |
| `guard-recursive-delete` | the filesystem, and `LANGUETTE_RM_ALLOW` |
| `ask-first` | the repo's list, the session transcript, the approvals spent |
| `guard-bypass-hooks` | the transcript, and the approvals spent |
| `guard-infra` | the transcript, the approvals spent |
| `guard-git-stacked-base` | GitHub, through `gh` |
| `guard-bypass-ruleset` | git, for where a push lands, and GitHub's rules for the default branch, through `gh`, cached an hour |
| `guard-github-issues` | the payload's `session_id`, and a door file in `$TMPDIR` |
| `guard-private-terms` | the terms file, the files a post reads, and the checkout's `git remote` |
| `guard-bypass-labels` | the `bypass_labels` setting, and a file `gh api --input` names |
| `guard-worktrees` | `$HOME` and what `git rev-parse --show-toplevel` resolves to; git, for where each path lands, and a record per session in `$TMPDIR` |
| `prose-budget-commit` | the staged diff and, for a commit that reaches past the index, the named working-tree files, through `prose-budget` |

A guard that cannot decide denies and says what it saw. A guard that crashes
is a deny naming the guard; the runner holds that rule, so no guard has to.

The contract is written as scenarios, in the words a person uses to state the
rule, and every scenario runs against every engine a guard has, Python and
shell alike:

```gherkin
Scenario: a target the guard cannot resolve is denied on sight
  Given the working directory is "$HOME/project"
  When the agent runs `rm -rf "$DIR"`
  Then the guard denies, naming "variable or command substitution"
```

The scenarios are the seam between the people who set the rules and the code
that enforces them: a reviewer reads them, and the code is judged against
them. The road ahead runs toward properties checked over generated commands,
then a model of each guard from which the scenarios are derived and against
which the code is proven.

## Installing by hand

Clone the repo and copy the entries from `hooks/hooks.json` into
`settings.json`, wrapper and all. The wrapper is what makes a missing or
crashing guard a deny: without it, a missing script is a non-blocking error
to Claude Code, and every command goes through. One entry:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "h=\"$HOME/languette/hooks/guard-recursive-delete.sh\"; { [ -f \"$h\" ] && sh \"$h\"; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"guard-recursive-delete.sh is missing or crashed. This is a gate and fails closed.\"}}'"}]}]}}
```

## Working on it

```
git clone https://github.com/mark-brannan/languette && cd languette
sudo apt install jq gawk mawk shellcheck
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest                       # every scenario, every engine
AWK_PATH=/dir/with/an/awk python3 -m pytest
python3 tests/readme_table.py           # regenerate the table
shellcheck --severity=warning hooks/*.sh tests/stubs/*   # as CI runs it
```

Running the tests needs pytest, pytest-bdd and PyHamcrest; the hooks do not.

The same run checks the shape of `hooks/hooks.json`, because
`claude plugin validate --strict` passes a malformed one. The headless smoke
test, which installs the plugin in a scratch project and confirms a recursive
`rm` is really blocked, stays manual: it needs a model call and a login.

`features/` holds the contract as scenarios: a command in, tokens or a
verdict out. The scanner (`hooks/lib-shell-words.awk`) and the guards began
as copies of the ones in
[mark-brannan/dotfiles](https://github.com/mark-brannan/dotfiles); this repo
is where they are maintained now.
