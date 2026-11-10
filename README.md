**Languette**: sharp hooks need strong guards.

*A deterministic check against risky actions by coding agents.*

![Jacques Callot, Drill with halberds (NGV 32320, public domain)](assets/callot-drill-with-halberds.jpg)

Before a coding agent runs a shell command, a languette guard reads it and
answers: *allow*, *ask*, or **deny**.

Nothing external decides: no web services, nothing cloud-based, and no ML or AI models.
The critical execution path is [deterministic](https://en.wikipedia.org/wiki/Deterministic_algorithm), and uses ["pure functions"](https://en.wikipedia.org/wiki/Pure_function) where possible.

### Who is this for?

**You!** *...assuming you are a real human being.* A big AI
vendor's safeguards are its product decision, changed on a whim.  We don't have to trust them blindly.
Languette is a guard you can read, test, and understand for yourself: **trust,
but verify**. Any vendor that wants to adopt it is welcome to, under the
terms of the AGPL.

### What's with the name?

*Languette* is French for "little tongue". On a halberd the languette (or 'langet')
is the strip of iron that runs down the shaft from the head, so a stray blow can't cut through
the pole. These guards are that strip: protecting your work, strengthening your tools, and holding back specific agentic hazards that could ruin your day.

It's also a play on words: Shell is a little language, and languette listens for the
few words in a shell command that can do damage. When it hears one, it tells the errant agent
"hold your tongue!"

> *"The wise speak only of what they know, Gríma son of Gálmód. A witless worm have you become. Therefore be silent, and keep your forked tongue behind your teeth. I have not passed through fire and death to bandy crooked words with a serving-man till the lightning falls."*
— **Gandalf**, in J.R.R. Tolkien's *The Two Towers*, Book 3, Chapter 6

## Install

The guards run as `PreToolUse` hooks in Claude Code today, on shell commands,
`gh` and GitHub MCP calls, and messages to other sessions; other agent hosts
are planned ([#5](https://github.com/mark-brannan/languette/issues/5)).

It is in beta: versions are patch-only; configuration keys stay but may gain
aliases ([#153](https://github.com/mark-brannan/languette/issues/153)).

### Claude Code

```
/plugin marketplace add mark-brannan/languette#release
/plugin install languette@languette
```

It needs `python3` 3.11 or newer, standard library only. `shfmt` (the parser it trusts
most) and `gh` (for the guards that ask GitHub) are optional. Without
`python3`, every Bash call is denied: the guards fail closed.
With no GitHub lookup, a Bash call waits a median 166-219 ms (p90 up to 318 ms) for the
guards: one hook process, on 16 cores of WSL2 under load. A lookup adds a network round trip.

### macOS

```
brew install mark-brannan/tap/languette
languette install && languette doctor
```

### Linux and WSL

```
sudo apt install python3 pipx shfmt gh
pipx ensurepath
pipx install languette
```

Open a new shell so `~/.local/bin` is on your PATH, then:

```
languette install && languette doctor
```

### Windows without WSL

Languette protects Claude Code inside WSL: run `wsl --install`, then the
Claude Code block above. An agent running natively in PowerShell is not protected.

### Devcontainer, Codespace and CI

Copy [`devcontainer/src/languette`](devcontainer/src/languette) to
`.devcontainer/languette`. This line installs Claude Code and languette:

```json
"features": { "./languette": {} }
```

A registry and a CI Action are planned
([#102](https://github.com/mark-brannan/languette/issues/102)). Claude Code
[cloud sessions](https://code.claude.com/docs/en/cloud-environments) build no
dev container.

### If you cannot run the installer

Clone the repo and add one entry per guard to `settings.json`, shaped like
the one below. Replace `$HOME/languette` with the path to your clone, and
keep the wrapper. The wrapper is what makes a missing or
crashing guard a deny: without it, a missing script is a non-blocking error
to Claude Code, and every command goes through. One entry, for Bash calls;
`hooks/hooks.json` lists the other tools and events the plugin wires:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
  "command": "h=\"$HOME/languette/languette/run.py\"; { [ -f \"$h\" ] && python3 -I \"$h\" --guard guard-recursive-delete; } || printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"languette/run.py (guard-recursive-delete) is missing or crashed, or python3 is not on PATH. This is a gate and fails closed.\"}}'"}]}]}}
```

### Removing it

`languette uninstall` removes what `languette install` wrote, after asking, through Claude Code's own command.

### Try it: `languette scan` (experimental)

It reads a shell command on stdin and prints the words each guard would judge:

```
$ echo 'rm -rf build && sh -c "git push --force"' | languette scan | jq -c '.segments[] | [.nested, [.words[].text]]'
[false,["rm","-rf","build"]]
[false,["sh","-c","git push --force"]]
[true,["git","push","--force"]]
```

From a checkout without installing, swap `languette scan` for `python3 -m languette scan`:

```
$ echo 'rm -rf build && sh -c "git push --force"' | python3 -m languette scan | jq -c '.segments[] | [.nested, [.words[].text]]'
```

## The guards

Each guard checks for one kind of hazard; [Configuration](#configuration)
turns one off:

- [`ask-first`](#ask-first): a command the repo lists as costly, until you approve that one run
- [`deny-always`](#deny-always): a command the repo forbids, every time
- [`guard-sudo`](features/guard-sudo.feature): opt-in; `sudo`, `su`, `doas`, `pkexec`, `run0`, `sudoedit`, `dzdo`
- [`require-well-formed`](features/require-well-formed.feature): a Bash command that doesn't parse; the other guards skip it
- [`guard-disks`](features/guard-disks.feature): `dd`, `mkfs`, `wipefs`, `shred` onto disks
- [`guard-github-issues`](features/guard-github-issues.feature): a second issue create, transfer or delete in one human turn, or any in a loop
- [`guard-host-availability`](features/guard-host-availability.feature): shutdown, reboot, fork bomb, `systemctl stop sshd`
- [`guard-infra`](features/guard-infra.feature): `terraform destroy`, `kubectl delete` and other destroys, until you approve that one run
- [`guard-permissions`](features/guard-permissions.feature): `chmod 777`, recursive `chmod`, `chown`, `chgrp` outside agent-owned or `LANGUETTE_PERM_ALLOW` paths
- [`guard-pipe-to-shell`](features/guard-pipe-to-shell.feature): `curl u | sh`, `sh <(curl ..)`, `eval "$(wget ..)"`
- [`guard-private-terms`](#settings-for-guard-private-terms): a blocked term posted to a public repo; your redacted terms replaced first
- [`guard-recursive-delete`](#allowing-more-for-guard-recursive-delete): a recursive `rm` or `find -delete` outside a generated or agent-owned directory
- [`guard-scheduled-jobs`](features/guard-scheduled-jobs.feature): `crontab -r`
- [`guard-secrets`](features/guard-secrets.feature): a pasted credential
- [`guard-worktrees`](features/guard-worktrees.feature): opt-in; a branch switch when `$HOME` is a worktree, or a reach into another session's worktree
- [`guard-bypass-hooks`](features/guard-bypass-hooks.feature): `--no-verify` and `git -c core.hooksPath=`, until you approve that one run
- [`guard-bypass-labels`](features/guard-bypass-labels.feature): a session applying a label the `bypass_labels` setting names (none by default)
- [`guard-bypass-ruleset`](features/guard-bypass-ruleset.feature): a push direct to main, past a pull-request rule your credentials can bypass
- [`guard-cross-session-send`](features/guard-cross-session-send.feature): a message to another session: an ask; in bypass mode, a deny after a network read
- [`guard-git-stacked-base`](features/guard-git-stacked-base.feature): deleting a remote branch an open PR is based on (GitHub silently closes the PR)
- [`guard-duplicate-prs`](features/guard-duplicate-prs.feature): a second open PR on one issue
- [`guard-git-work-loss`](features/guard-git-work-loss.feature): `add -A`, `stash pop`, force-push, `reset --hard` and other moves that throw work away
- [`guard-protected-services`](features/guard-protected-services.feature): `systemctl stop postgresql`, for the services the `protected_services` setting names
- [`guard-review-threads`](features/guard-review-threads.feature): opt-in; resolving a bot's review thread with no reply naming a commit or a link
- [`guard-signed-comments`](features/guard-signed-comments.feature): opt-in; a comment not from a bot's account, or without the signature you set
- [`prose-budget-commit`](features/prose-budget-commit.feature): opt-in; a `git commit` whose staged prose runs over the repo's word budgets
- `guard-databases` (planned)
- `guard-protected-paths` (planned)

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

With `shfmt` 3.6 or later on `PATH`, the `require-well-formed` guard denies a
command that doesn't parse. Without `shfmt`, it falls back to `bash -n`, then
to its own lexer.
In a replay of 101,671 agent commands, about 1 in 3,000 didn't parse, and
each [would have broken](features/require-well-formed.feature).
Bash runs a broken command in part, the lines before the error or prose in
backticks as a command; the deny stops all of it, so the agent looks again.
A command over 64 KB, or nested too deeply to parse quickly, is denied unread.

## Not a sandbox

Languette is an accident guard, not a sandbox: it judges the commands it is shown, and confines nothing. A sandbox confines, and judges nothing: `rm -rf src` in your project passes. Run both; unattended or on untrusted text, sandbox first.

| What a guard cannot see | The layer that can |
|---|---|
| What a script, `python3 -c` or any other program does once it runs | A [sandbox](https://code.claude.com/docs/en/sandboxing): it confines the process, whatever runs |
| A secret file the agent opens with its Read tool, then repeats | Permission deny rules; better, no secrets on the disk it works on |
| Data leaving by `curl`, a package install or an allowed host | A short list of allowed domains; a container with its own egress rules |
| A session rewriting the hooks and settings that guard it | A sandbox denies shell writes to them; the rest is open ([#384](https://github.com/mark-brannan/languette/issues/384)) |

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

A match may also name `"flags"`, single option letters the command must carry
(`{"cmd": "rm", "flags": ["r"]}` matches `rm -rf x`).

Matching sees through wrappers: `timeout 3h npm run e2e`, `sh -c "..."`,
`pnpm exec node ./scripts/e2e.mjs` and `yarn e2e` all count, while `grep`,
`git commit -m`, `cat` and `pkill -f` that merely name the script do not. A
run hidden inside a script (`./ci.sh`) or behind a variable (`$CMD`) is not
seen.

The guard reads the nearest `.languette/ask-first.json` at or above the
command's working directory, stopping at the repo root, else the one in
`$CLAUDE_PROJECT_DIR`. With no file, it stays silent. A file that doesn't
parse, that has a key besides `id`, `match`, `cost`, `approve_label` and
`cheaper`, or that gives two commands the same `id` or `approve_label`,
denies every command until it is fixed, because the guard can no longer tell what the repo
meant. Spent approvals are kept beside the session transcript, in
`<transcript>.languette-ask`.

In an unattended session, an ask is a deny
(planned: [#164](https://github.com/mark-brannan/languette/issues/164)).

## Deny always

A repo lists the commands it forbids in `.languette/deny-always.json`:

```json
{"rules": [{"id": "prod-db",
  "match": [{"cmd": "psql", "args": ["prod"]}],
  "why": "production is reached through the release job, never by hand"}]}
```

Matches, lookup and a broken file work as for ask-first; `{"cmd":
"terraform"}` alone forbids the whole program.

## Configuration

Every guard is on by default except `guard-worktrees`,
`guard-review-threads`, `guard-signed-comments`, `guard-sudo` and
`prose-budget-commit`, which are opt-in. Turn one off (or those on) with
`/plugin configure languette@languette`,
or at install, by its name with underscores:

```
claude plugin install languette@languette --config guard_recursive_delete=false
```

Changing an option later, outside the installer, is `languette config` (planned; [design](docs/design/config.md)).

A guard is skipped only when its setting is exactly `false`. Unset, empty or
anything else runs it, so a misconfiguration cannot open the gate.
An opt-in guard is the reverse: it runs only when its setting is exactly
`true`, so a misconfiguration leaves it off. The two controls of
`guard-worktrees`, `guard_worktrees_checkout_home` and
`guard_worktrees_foreign`, are each on unless set to `false`.

### One setting per `guard-git-work-loss` rule

`guard_git_work_loss=false` skips all six rules. To keep five, turn off one:

| Setting | Rule it switches off |
| --- | --- |
| `guard_git_work_loss_blanket_staging` | `add -A`, `add .`, `commit -a` |
| `guard_git_work_loss_stash` | `stash pop`, `stash clear`, a bare `stash drop` |
| `guard_git_work_loss_force_push` | a bare force push; a force push to or delete of main |
| `guard_git_work_loss_discard` | `reset --hard`, `checkout .`, `restore .`, `clean -f` |
| `guard_git_work_loss_branch_delete` | `branch -D`, `branch --delete --force` |
| `guard_git_work_loss_adopt` | `stow --adopt` (asks) |

### Allowing more for `guard-recursive-delete`

Built in: the generated directories `node_modules`, `dist`, `coverage` and
`.pio`, and the agent's own places: `/tmp`, the host's temporary directory
(`$CLAUDE_CODE_TMPDIR`, else `$TMPDIR`) and the host's worktree directory,
`<project>/.claude/worktrees`, for the project the host names
(`$CLAUDE_PROJECT_DIR`) and the one a worktree session stands in.

To allow more, set `LANGUETTE_RM_ALLOW` to a colon-separated list. It adds to
the built-in lists and never replaces them; unset or empty changes nothing.

```
export LANGUETTE_RM_ALLOW=build:.next:/srv/agent-area
```

- A bare name (`build`) is treated like `dist`: a directory with that name, below the top level of `$HOME` or `/`.
- An absolute path (`/srv/agent-area`) is treated like the scratchpad: a place the agent owns.
- Entries use letters, digits and `. _ @ + -` only. A path has no `.` or `..` segment, and is never `/` or `$HOME`.

If the value doesn't parse, every Bash call carries a warning, and only a
recursive `rm` or `find -delete` is denied. A typo can't stop unrelated work,
and it can't open the gate either.

### Settings for `guard-private-terms`

| Setting | Holds |
|---|---|
| `blocked_terms_file` | terms that deny the whole post: the term, a tab, a message for the agent |
| `redacted_terms_file` | terms replaced before the post leaves: the term, a tab, the replacement |
| `private_repos` | repos whose posts are never scanned, comma-separated: `you/notes,you/scratch` |

One tab-separated format, `#` comments, case-insensitive, `re:` for a regular
expression; unset, the files are `blocked-terms.tsv` and `redacted-terms.tsv`
in `~/.config/languette/`. A path set but not
loading denies public posts until fixed; `languette doctor` says which line.
Only the file's entries count; `languette doctor --init-redacted-terms` writes the
[default entries](languette/rules/redacted-terms.tsv) into it; [`features/fixtures/private-terms/`](features/fixtures/private-terms/)
shows a comment beside what leaves.

### Other settings

`bypass_labels` lists the labels `guard-bypass-labels` keeps for humans,
comma-separated, for example `churn-ok,mixed-loops-ok`; empty, the default,
guards no label.

`review_thread_logins` lists the logins, besides the gh login, whose reply
lets `guard-review-threads` pass a thread's resolve, comma-separated, for
example `you,your-app`; empty, the default, counts the gh login alone.

`guard-signed-comments` is experimental. On, it denies any comment not posted
from a bot's account (a GitHub App's, its login ending in `[bot]`), and any
through a GitHub MCP tool, whose account it cannot read. It checks a signature
only for the settings you give it: `signed_comments_opening` and
`signed_comments_signature` are empty by default, and empty checks nothing.

`record_decisions`, off by default, keeps every verdict, with its command and
secrets masked, in `$XDG_STATE_HOME/languette/decisions.jsonl`, readable only by you.

## Privacy and support

Guards that need GitHub's answer ask through your own `gh`. Session state
stays in local files. Decisions are recorded only if you turn on
`record_decisions`.

Questions and bugs: [GitHub issues](https://github.com/mark-brannan/languette/issues).

## Strong guards

A guard is a pure function of the command and the facts it asked for; it
asks no model and runs nothing, and the runner fetches the facts ([the
design](docs/design/guard-pipeline.md)). The verdict is **deny** with the
reason, **ask**, a **warning**, or **nothing** (*allow*). What a guard asks
for beyond the command, it declares:

| Guard | Reads |
|---|---|
| `guard-git-work-loss` | git: whether the tree is clean, a linked worktree or in the scratchpad; guard-worktrees' record |
| `require-well-formed` | a shell parser; nothing runs the command |
| `guard-recursive-delete` | the filesystem, and `LANGUETTE_RM_ALLOW` |
| `ask-first` | the repo's list, the session transcript, the approvals spent |
| `guard-bypass-hooks` | the transcript, and the approvals spent |
| `guard-secrets` | the repo's `.languette/secrets.json`, when it has one |
| `guard-infra` | the transcript, the approvals spent |
| `guard-git-stacked-base` | GitHub, through `gh` |
| `guard-duplicate-prs` | the issue's timeline on GitHub, through `gh`, a `--body-file` it posts, and the checkout's `git remote` |
| `guard-review-threads` | the files a graphql call reads; each thread it resolves, and the gh login, from GitHub through `gh` |
| `guard-bypass-ruleset` | git, for where a push lands, and GitHub's rules for the default branch, through `gh`, cached an hour |
| `guard-github-issues` | the payload's `session_id`, the transcript, and a door file in `$TMPDIR` |
| `guard-private-terms` | the terms file, the files a post reads, and the checkout's `git remote` |
| `guard-signed-comments` | the files a comment's body is read from, its two settings, and the gh login, from GitHub through `gh` |
| `guard-bypass-labels` | the `bypass_labels` setting, and a file `gh api --input` names |
| `guard-cross-session-send` | the payload's `session_id` and `permission_mode`, a record per session in `$TMPDIR`, and the agent-team config |
| `guard-worktrees` | `$HOME`; git, for the repo's top level and where each path lands; a record per session in `$TMPDIR` |
| `prose-budget-commit` | the staged diff, and the working-tree files a commit names, through `prose-budget` |

A guard that crashes is a deny naming the guard; the runner holds that rule,
so no guard has to.

The contract is written as "[gherkin](https://en.wikipedia.org/wiki/Cucumber_(software)#Gherkin_language)" scenarios, in the words a person uses to state the
rule. They're still completely deterministic tests, just easy for non-technical folks to read.

```gherkin
Scenario: a target the guard cannot resolve is denied on sight
  Given the working directory is "$HOME/project"
  When the agent runs `rm -rf "$DIR"`
  Then the guard denies, naming "variable or command substitution"
```

## Working on it

```
git clone https://github.com/mark-brannan/languette && cd languette
sudo apt install shfmt shellcheck
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python3 -m pytest                       # as each push runs it; --full runs every row
python3 tests/readme_table.py           # regenerate the table
shellcheck --severity=warning tests/stubs/*   # as CI runs it
python3 -m languette doctor             # run this checkout without installing it
pipx install --force git+https://github.com/mark-brannan/languette@main
pipx install --force languette          # revert to last official release
```

Running the tests needs pytest, pytest-bdd, pytest-xdist and PyHamcrest; the hooks do not.

The suite runs on at most 4 workers; `LANGUETTE_TEST_WORKERS=N` sets the cap, `-n 0` runs serially.

The same run checks the shape of `hooks/hooks.json`, because
`claude plugin validate --strict` passes a malformed one. The headless smoke
test, which installs the plugin in a scratch project and confirms a recursive
`rm` is really blocked, stays manual: it needs a model call and a login.

`features/` holds the contract as scenarios: a command in, tokens or a
verdict out.

## License

Markdown files are [CC BY-SA 4.0](LICENSE-CC-BY-SA); everything else is
[AGPL-3.0-or-later](LICENSE), except where a file carries its own notice.
Copyright 2026 Mark Brannan. Credit "Mark Brannan" and link this repository.
