**Languette**: sharp hooks need strong guards.

*A deterministic check against risky actions by coding agents.*

![Jacques Callot, Drill with halberds (NGV 32320, public domain)](assets/callot-drill-with-halberds.jpg)

Before a coding agent runs a shell command, a languette guard reads it and
answers: allow, ask, or deny. No model decides, and nothing is run to decide.
The guards run in Claude Code today; other agent hosts are planned
([#5](https://github.com/mark-brannan/languette/issues/5)).

## Install

In Claude Code:

```
/plugin marketplace add mark-brannan/languette
/plugin install languette@languette
```

It needs `jq` and a POSIX `awk`; `no-delete-stacked-base` also uses `gh`, and
`ask-first` uses `python3`.

Without the plugin system, clone the repo and copy the entries from
`hooks/hooks.json` into `settings.json`, wrapper and all. The wrapper is what
makes a missing or crashing guard a deny: without it, `sh missing.sh` exits
127, Claude Code treats that as a non-blocking error, and every command goes
through. One entry:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "h=\"$HOME/languette/hooks/no-rm-tree.sh\"; { [ -f \"$h\" ] && sh \"$h\"; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"no-rm-tree.sh is missing or crashed. This is a gate and fails closed.\"}}'"}]}]}}
```

## The guards

- **`no-rm-tree`** denies a recursive `rm` or `find -delete` unless the
  target is a generated directory (`node_modules`, `dist`, `coverage`,
  `.pio`) or a place the agent owns (`/tmp`, `~/.local/state/claude-tmpdir`,
  `~/.claude/worktrees`). It exists because an agent once ran
  `rm -rf examples` and took a directory of the user's captures with it.
- **`no-git-footguns`** denies `git add -A`, `commit -a`, `stash pop`,
  force-push, `checkout .`, `clean -f`, `branch -D` and `reset --hard`. Each
  throws work away, often in a checkout another session shares.
- **`no-delete-stacked-base`** asks GitHub whether an open PR is based on a
  remote branch before it is deleted, and denies if one is. GitHub silently
  closes every PR stacked on a branch deleted outside a merge.
- **`ask-first`** denies a command the repo marks as costly until the user
  approves that one run. It exists because an agent once ran a 46-minute
  test sweep on a 16-core workstation to check a small change, then started
  it again. See [Ask first](#ask-first).

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

Set `LANGUETTE_RM_ALLOW` to a colon-separated list. It adds to the built-in
lists and never replaces them; unset or empty changes nothing.

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

The guards began as copies of the ones in
[mark-brannan/dotfiles](https://github.com/mark-brannan/dotfiles); this repo
is where they are maintained now. The product name appears only in
`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the
install lines above, so a rename touches those and nothing else.
