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

## Install

The guards run as `PreToolUse` hooks in Claude Code today; other agent hosts
are planned ([#5](https://github.com/mark-brannan/languette/issues/5)).

```
/plugin marketplace add mark-brannan/languette
/plugin install languette@languette
```

It needs:

- `jq` and a POSIX `awk`, until a real shell parser replaces them
  ([#4](https://github.com/mark-brannan/languette/issues/4), planned);
- `python3`, standard library only, for `ask-first`;
- `gh`, for `no-delete-stacked-base`.

Without the plugin system, see [Installing by hand](#installing-by-hand).

## The guards

Each guard denies one class of command:

- [`no-rm-tree`](hooks/no-rm-tree.sh): a recursive `rm` or `find -delete`,
  unless the target is a generated directory or a place the agent owns (an
  agent once took a directory of the user's captures with `rm -rf examples`).
- [`no-git-footguns`](hooks/no-git-footguns.sh): `git add -A`, `commit -a`,
  `stash pop`, force-push, `reset --hard` and the other moves that throw work
  away, often in a checkout another session shares.
- [`no-delete-stacked-base`](hooks/no-delete-stacked-base.sh): deleting a
  remote branch that an open PR is based on (GitHub silently closes the PR).
- [`ask-first`](languette/guards/ask_first.py): a command the repo lists as
  costly, until you approve that one run (an agent once ran a 46-minute,
  all-core test sweep to check a small change, then started it again). See
  [Ask first](#ask-first).

## The promise

**When a guard can't tell what a command it covers will do, it denies and
says why. When no rule covers a command, it says nothing.**

A variable where a path should be, a brace expansion, a quote it can't
resolve: each is a deny that names what the guard saw. The second half is a
limit, not a bug. A guard reads shell text; it does not open scripts or read
other languages. These are real verdicts, generated from the guards' test
cases for a command run in `~/project`, and CI fails if the table drifts:

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

Every guard is on by default. Turn one off with
`/plugin configure languette@languette`, or at install:

```
claude plugin install languette@languette --config no_rm_tree=false
```

| Key | Guard |
|---|---|
| `no_git_footguns` | `no-git-footguns` |
| `no_rm_tree` | `no-rm-tree` |
| `no_delete_stacked_base` | `no-delete-stacked-base` |
| `ask_first` | `ask-first` |

A guard is skipped only when its setting is exactly `false`. Unset, empty or
anything else runs it, so a misconfiguration cannot open the gate.

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

A guard that cannot decide denies and says what it saw. A guard that crashes
is a deny naming the guard; the runner holds that rule, so no guard has to.

The contract is written as scenarios, in the words a person uses to state the
rule, and every scenario runs against every engine a guard has, Python and
shell alike (in progress: [#31](https://github.com/mark-brannan/languette/pull/31)):

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
bash hooks/no-rm-tree.test.sh               # the three shell suites
bash hooks/no-git-footguns.test.sh
bash hooks/no-delete-stacked-base.test.sh
fixtures/run.sh                             # the scanner and guard contract, and the hooks.json wiring
AWK_PATH=/dir/with/an/awk fixtures/run.sh   # the same under another awk
```

CI also checks the shape of `hooks/hooks.json` (`fixtures/run.sh --shape`),
because `claude plugin validate --strict` passes a malformed one. The
headless smoke test, which installs the plugin in a scratch project and
confirms a recursive `rm` is really blocked, stays manual: it needs a model
call and a login.

`fixtures/` holds the contract as data (witness test cases): a command in,
tokens or a verdict out, until [#31](https://github.com/mark-brannan/languette/pull/31)
moves it to scenarios under `features/`. The scanner (`hooks/lib-shell-words.awk`)
and the guards began as copies of the ones in
[mark-brannan/dotfiles](https://github.com/mark-brannan/dotfiles); this repo
is where they are maintained now.
