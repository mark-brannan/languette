Languette: your hooks need guards.

![Jacques Callot, Drill with halberds (NGV 32320, public domain)](assets/callot-drill-with-halberds.jpg)

A deterministic check on the actions coding agents take.

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
`hooks/hooks.json` has the three entries to copy; this is one:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "h=\"$HOME/languette/hooks/no-rm-tree.sh\"; { [ -f \"$h\" ] && sh \"$h\"; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"no-rm-tree.sh is missing or crashed. This is a gate and fails closed.\"}}'"}]}]}}
```

Requires `jq` and a POSIX `awk` (the suites run under mawk, gawk and
original-awk); `no-delete-stacked-base` also uses `gh`.

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

The allowlists are constants in the scripts, for now (`GENERATED_NAMES` in
`no-rm-tree.sh`). Other agent hosts are a roadmap item, not a promise: the
scripts read the Claude Code payload shape.

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
out. The scanner (`hooks/lib-shell-words.awk`) and the three guards are
copied from [mark-brannan/dotfiles](https://github.com/mark-brannan/dotfiles)
with house material stripped. `.github/dotfiles-drift/drift.py check` fails,
with the diff, when either side moves; `drift.py regen` rewrites the reviewed
edits after a deliberate change.

The product name appears in `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and the install lines above; the scripts
name themselves, so a rename touches those and nothing else.

MIT licensed.
