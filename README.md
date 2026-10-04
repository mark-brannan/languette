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

The guards run as `PreToolUse` hooks in Claude Code today (`issue-door` also
runs on `UserPromptSubmit`, which opens its door); other agent hosts
are planned ([#5](https://github.com/mark-brannan/languette/issues/5)).

```
/plugin marketplace add mark-brannan/languette
/plugin install languette@languette
```

It needs:

- `jq` and a POSIX `awk`, until a real shell parser replaces them
  ([#4](https://github.com/mark-brannan/languette/issues/4), planned);
- `python3`, standard library only, for `ask-first` and `no-bypass-labels`;
- `gh`, for `no-delete-stacked-base`.

Without the plugin system, see [Installing by hand](#installing-by-hand).

## The guards

Each guard denies one class of command:

- [`no-rm-tree`](#allowing-more-for-no-rm-tree): a recursive `rm` or
  `find -delete` outside a generated or agent-owned directory
- [`no-git-footguns`](hooks/no-git-footguns.sh): `add -A`, `commit -a`,
  `stash pop`, force-push, `reset --hard` and other moves that throw work away
- [`no-delete-stacked-base`](hooks/no-delete-stacked-base.sh): deleting a
  remote branch an open PR is based on (GitHub silently closes the PR)
- [`issue-door`](hooks/issue-door.sh): a second GitHub issue create, transfer
  or delete in one human turn, or any inside a loop
- [`public-issue-guard`](#settings-for-public-issue-guard): a term from your
  private list, posted to a public repo (off until you give it the list)
- [`no-checkout-home`](hooks/no-checkout-home.sh): switching the branch
  checked out in `$HOME`, when home is itself a worktree (opt-in)
- [`no-foreign-worktree`](hooks/no-foreign-worktree.sh): a command or edit
  that reaches into another session's git worktree (opt-in)
- [`no-bypass-labels`](languette/guards/no_bypass_labels.py): a session
  applying a label that waives a CI gate, such as `churn-ok`
- [`ask-first`](#ask-first): a command the repo lists as costly, until you
  approve that one run
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

Every guard is on by default except `no-checkout-home` and
`no-foreign-worktree`, which are opt-in. Turn one off (or those on) with
`/plugin configure languette@languette`,
or at install, by its name with underscores:

```
claude plugin install languette@languette --config no_rm_tree=false
```

A guard is skipped only when its setting is exactly `false`. Unset, empty or
anything else runs it, so a misconfiguration cannot open the gate.
`no_checkout_home` and `no_foreign_worktree` are the reverse: each runs only
when its setting is exactly `true`, so a misconfiguration leaves it off.

### One setting per `no-git-footguns` rule

`no_git_footguns=false` skips all five rules. To keep four, turn off one:

| Setting | Rule it switches off |
| --- | --- |
| `no_git_footguns_blanket_staging` | `add -A`, `add .`, `commit -a` |
| `no_git_footguns_stash` | `stash pop`, `stash clear`, a bare `stash drop` |
| `no_git_footguns_force_push` | a bare force push; a force push to or delete of main |
| `no_git_footguns_discard` | `reset --hard`, `checkout .`, `restore .`, `clean -f` |
| `no_git_footguns_branch_delete` | `branch -D`, `branch --delete --force` |

### Allowing more for `no-rm-tree`

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

### Settings for `public-issue-guard`

| Setting | Holds | Example |
|---|---|---|
| `private_terms_file` | a text file of terms, one per line, matched case-insensitively | `~/.config/private-terms` |
| `private_repos` | repos whose posts are never scanned, comma-separated | `you/notes,you/scratch` |

Without a terms file the guard is off.

`bypass_labels` lists the labels `no-bypass-labels` keeps for humans,
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
| `no-git-footguns` | nothing: a pure function of the command |
| `no-rm-tree` | the filesystem, and `LANGUETTE_RM_ALLOW` |
| `ask-first` | the repo's list, the session transcript, the approvals spent |
| `no-delete-stacked-base` | GitHub, through `gh` |
| `issue-door` | the payload's `session_id`, and a door file in `$TMPDIR` |
| `no-checkout-home` | `$HOME`, and what `git rev-parse --show-toplevel` resolves to |
| `public-issue-guard` | the terms file, the files a post reads, and the checkout's `git remote` |
| `no-bypass-labels` | the `bypass_labels` setting, and a file `gh api --input` names |
| `no-foreign-worktree` | git, for where each path lands, and a record per session in `$TMPDIR` |
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
  "command": "h=\"$HOME/languette/hooks/no-rm-tree.sh\"; { [ -f \"$h\" ] && sh \"$h\"; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"no-rm-tree.sh is missing or crashed. This is a gate and fails closed.\"}}'"}]}]}}
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
