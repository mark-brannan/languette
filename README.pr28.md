**Languette**: sharp hooks need strong guards.

*A deterministic check against risky actions by coding agents.*

![Jacques Callot, Drill with halberds (NGV 32320, public domain)](assets/callot-drill-with-halberds.jpg)

Languette is a set of `PreToolUse` hooks for Claude Code. Each one reads the
Bash command an agent is about to run and decides: allow, ask, or deny. No
model is involved, and no command is executed to decide.

## Install

In Claude Code:

```
/plugin marketplace add mark-brannan/languette
/plugin install languette@languette
```

Without the plugin system, clone the repo and point `settings.json` at the
scripts. Keep the wrapper: a plain `sh missing.sh` exits 127, which Claude
Code treats as a non-blocking error, so a guard that vanished would let every
command through. The wrapper turns a missing or crashing script into a deny.
`hooks/hooks.json` has the four entries to copy; this is one:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "h=\"$HOME/languette/hooks/no-rm-tree.sh\"; { [ -f \"$h\" ] && sh \"$h\"; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"no-rm-tree.sh is missing or crashed. This is a gate and fails closed.\"}}'"}]}]}}
```

Requires `jq` and a POSIX `awk` (the suites run under mawk, gawk and
original-awk); `no-delete-stacked-base` also uses `gh`, and `ask-first` needs `python3` (standard library only).

## The promise

**Parse ambiguity on a covered command fails closed and loud; a missing rule fails open and silent.**

If the guard cannot tell what a covered command will do (a variable where a
path should be, a brace expansion, a quoted string it cannot resolve), it
denies and names what it saw. If no rule covers the command at all, it says
nothing and lets it through. The second half is a limit, not a bug.
Measured, with the payload `{tool_name: Bash, tool_input.command, cwd: ~/project}`:

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

The two `allow` rows marked known gap are documented and deliberate: a guard
for shell text does not read scripts or interpreters. The table is generated
from `fixtures/guards.jsonl` (`fixtures/run.sh --table`), and CI fails if it
drifts.

## The guards

- `no-rm-tree`: recursive `rm` and `find -delete` are denied unless the target is a generated directory (`node_modules`, `dist`, `coverage`, `.pio`), `/tmp` (where Claude Code keeps its scratchpad by default), `~/.local/state/claude-tmpdir` or `~/.claude/worktrees`. Worktrees Claude Code makes under a repo's own `.claude/worktrees/` are not on the list yet. An agent once swept a directory of the user's captures away with `rm -rf examples`.
- `no-git-footguns`: `git add -A`, `commit -a`, `stash pop`, force-push, `checkout .`, `clean -f`, `branch -D` and `reset --hard` are denied. Each throws work away, often in a checkout shared with another session.
- `no-delete-stacked-base`: deleting a remote branch asks GitHub whether an open PR uses it, and denies if so, because GitHub silently closes every PR stacked on a branch deleted outside a merge.
- `ask-first`: a command the repo lists as costly is denied until the user approves that one run. An agent once ran a 46-minute test sweep on a 16-core workstation to check a small change, held the load near 20 throughout, then started it again. See below.

## Ask first

A repo names its expensive commands in `.languette/ask-first.json`:

```json
{"commands": [{"id": "e2e",
  "match": [{"cmd": "npm", "args": ["run", "e2e"]},
            {"cmd": "node", "script": "scripts/e2e.mjs"}],
  "cost": "> 40 minutes, using all CPU cores on a typical desktop",
  "approve_label": "Run e2e"}]}
```

The file is read from the nearest directory at or above the command's
working directory that has one, stopping at the repo root, else from
`$CLAUDE_PROJECT_DIR`. No file, and the guard says nothing. A file that does
not parse, or in which two commands share an `approve_label`, denies every
Bash command until it is fixed, because the guard can no longer tell what the
repo meant to cover.

A matching command is denied with the cost, the cheaper forms if the entry
lists them (`"cheaper"`, free text), and an instruction: ask the user
through `AskUserQuestion`, giving the exact command and why now, with one
option labelled exactly `approve_label`. When the transcript shows the user
picked that option, the next matching command runs, and the approval is spent:
one yes is one run. A command that runs it twice needs two; one in a loop or
`xargs` is denied whatever was approved. Only the user's click counts, never
the question's text. Spent approvals are listed beside the transcript in
`<transcript>.languette-ask`.

Matching uses the same scanner as the other guards, so `timeout 3h npm run
e2e`, `sh -c "..."`, `pnpm exec node ./scripts/e2e.mjs` and `yarn e2e` all count,
while `grep`, `git commit -m`, `cat` and `pkill -f` naming the script do not.
This guard runs on the Python engine (`languette/`); the others are still
shell.

Known gaps: a run inside a script (`./ci.sh`) or behind a variable (`$CMD`) is
not seen.

The built-in allowlists are constants in the scripts (`GENERATED_NAMES` in
`no-rm-tree.sh`). To allow more, set `LANGUETTE_RM_ALLOW` to a colon-separated
list; it adds to the built-in lists and never replaces them, and unset (or
empty) is exactly the behaviour above:

```
export LANGUETTE_RM_ALLOW=build:.next:/srv/agent-area
```

- A bare name (`build`) joins `GENERATED_NAMES`: a directory with that name
  at any depth below the top of `$HOME` or `/`, same as `dist`.
- An absolute path (`/srv/agent-area`) joins the agent-owned roots, beside
  the scratchpad and `~/.claude/worktrees`.
- Entries use letters, digits and `. _ @ + -` only; a path may not hold a
  `.` or `..` segment and may not be `/` or `$HOME`.
- A value that does not parse (an empty entry, a glob, a space, a relative
  path with a slash) warns on every Bash call, through
  `hookSpecificOutput.additionalContext`, and denies only a recursive `rm` or
  `find -delete`, with a message naming `LANGUETTE_RM_ALLOW`. Every other
  command runs, so a typo cannot stop unrelated work, and it cannot open the
  gate either.

Other agent hosts are a roadmap item, not a promise: the
scripts read the Claude Code payload shape.

## Configuration

One boolean per guard, every one on by default:

| Key | Guard |
|---|---|
| `no_git_footguns` | `no-git-footguns` |
| `no_rm_tree` | `no-rm-tree` |
| `no_delete_stacked_base` | `no-delete-stacked-base` |
| `ask_first` | `ask-first` |

Turn one off with `/plugin configure languette@languette`, or at install:

```
claude plugin install languette@languette --config no_rm_tree=false
```

Claude Code hands each key to the hook as `CLAUDE_PLUGIN_OPTION_<KEY>`, and
`hooks/hooks.json` skips a guard only when that variable is exactly `false`.
Unset, empty or any other value runs the guard, so a misconfiguration cannot
open the gate. A guard that is on still fails closed when its script is
missing or crashes.

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
Booleans are the words `true` and `false`, not `1` and `0`. A list is joined
with a bare comma and no escaping, so it cannot be split back apart when an
item holds a comma. A string `"false"` is indistinguishable from a boolean
`false`. A `default` did not reach the environment under `--plugin-dir`; the
installed-plugin path was not measured, which is why the guards treat unset
as on.

## Strong guards

A guard is a function. It takes the command and the payload around it and
returns a verdict: deny with a reason, ask, a warning, or nothing. It runs
nothing, asks no model, and the same inputs give the same verdict every time.
What it reads besides the command is named in its header: the filesystem and
`LANGUETTE_RM_ALLOW` for `no-rm-tree`; the repo's list, the session
transcript and the approvals already spent for `ask-first`; GitHub for
`no-delete-stacked-base`; nothing for `no-git-footguns`. A guard
that cannot decide denies and says what it saw. A guard that crashes is a deny
naming the guard; the runner holds that rule once, so no guard has to.

The guards share one scanner, `languette/scan.py`, which turns the command
into words and nested texts and resolves every ambiguity toward more words
reaching the guard, and one vocabulary for verdicts, `languette/verdict.py`.
A new guard is one module with a `check` function and its scenarios. It adds
no runner, no wrapper and no harness.

The contract is written as scenarios, in Gherkin, under `features/`: a command
and its context in, a verdict out, in the words a person uses to state the
rule.

```gherkin
Scenario: a target the guard cannot resolve is denied on sight
  Given the working directory is "$HOME/project"
  When the agent runs `rm -rf "$DIR"`
  Then the guard denies, naming "variable or command substitution"
```

Every scenario runs against every engine a guard has: the Python module
in-process, and the shell script by subprocess under each awk CI installs.
The engines must agree, and the table under the promise above is generated
from the scenarios tagged for it. Assertions are PyHamcrest matchers that
speak the promise, `denies`, `is_silent`, `warns_about`, so a failure prints
the guard's reason beside what was expected. Above the scenarios sit
properties, checked over generated commands: a guard fails closed on any
exception; a verdict on a text is never looser when that text is nested in
`sh -c`, `eval` or a pipe to a shell; adding a rule never turns a deny into an
allow, and an allowlist name turns a deny into an allow only for the targets
it names.

The scenarios are the seam between the people who set the rules and the code
that enforces them. Whether a scenario is written by hand or derived from a
model of the guard is open. Either way it is what a reviewer reads, and the
code is judged against it.

The hooks need only the standard library, and CI proves it with an import walk
over `languette/`. The tests need `pytest`, `pytest-bdd` and `PyHamcrest`;
the hooks do not.

## Working on it

```
bash hooks/no-rm-tree.test.sh               # the three suites
bash hooks/no-git-footguns.test.sh
bash hooks/no-delete-stacked-base.test.sh
fixtures/run.sh                             # the scanner and guard contract, and the hooks.json wiring
AWK_PATH=/dir/with/an/awk fixtures/run.sh   # the same under another awk
```

CI also checks the shape of `hooks/hooks.json` (`fixtures/run.sh --shape`: a
top-level object whose `hooks.PreToolUse` is an array of entries, each with a
`matcher` and `hooks[]` of `type: "command"` with a `command`), because `claude plugin validate --strict`
passes a garbage one. That is a shape check only, with no model call and no
login. The headless smoke test, which installs the plugin in a scratch project
and confirms a recursive `rm` is really blocked, stays manual: it needs both.

`fixtures/` holds the contract as data: a command in, tokens or a verdict
out. The scanner (`hooks/lib-shell-words.awk`) and the three guards began as
copies of the guards in [mark-brannan/dotfiles](https://github.com/mark-brannan/dotfiles);
this repo is where they are maintained now.

The product name appears in `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and the install lines above; the scripts
name themselves, so a rename touches those and nothing else.
