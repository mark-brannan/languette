# Agent decisions

Append-only. Each entry is a call an agent made in pencil: a default it took
under the one-way-door test, with its undo. Written by `agent-decision`; the
heading is the UTC stamp, so `agent_decisions.md#<stamp>` links one entry.

### 20261004t044000z
- prose-budget-commit denies on engine exit 2 (bad budgets config or engine without --staged), failing closed Undo: change '2) deny' to 'exit 0' in hooks/prose-budget-commit.sh ([#36](https://github.com/mark-brannan/languette/pull/36))
- prose-budget-commit keeps the upstream deny line 'Do not ask the user; this is settled.' Undo: edit the deny string in hooks/prose-budget-commit.sh and its scenario ([#36](https://github.com/mark-brannan/languette/pull/36))
- README replaces the config key/guard table with 'by its name with underscores' Undo: revert README hunk from 1e196c1 ([#36](https://github.com/mark-brannan/languette/pull/36))
- prose-budget-commit ships with the --staged gap (pathspec commit, add && commit in one call) documented, not closed Undo: detect pathspec/chained add in segment() and run the engine on those files ([#36](https://github.com/mark-brannan/languette/pull/36))

### 20261004t051544z
- no-checkout-home judges git from where the last cd landed (a cd replaces the directory), so `(cd x); git checkout y` from $HOME is a known false allow; Solace chose this over keeping the session cwd as a candidate after transcripts showed 82 of 102 checkouts from $HOME begin with a cd and 0 use a cd subshell. Undo: keep every cd target and the session cwd as candidates ([#37](https://github.com/mark-brannan/languette/pull/37))

### 20261004t062709z
- README no-git-footguns bullet reads 'and other moves' not 'and the other moves', so the approved text fits the 110-character one-line rule Undo: restore 'the' in the no-git-footguns bullet; the line is then 114 characters rendered ([#38](https://github.com/mark-brannan/languette/pull/38))
- public-issue-guard keeps its hooks.json matcher unchanged after the label denial moved out, since every tool it names also posts text Undo: narrow the PreToolUse matcher in hooks/hooks.json to the tools that post text ([#38](https://github.com/mark-brannan/languette/pull/38))
- README Configuration names no-foreign-worktree as the second opt-in guard, a correction of a sentence this PR made false, under the rule that adds nothing else to the README Undo: revert 2e4d55e ([#39](https://github.com/mark-brannan/languette/pull/39))

### 20261004t082010z
- The engine moved from languette#42 into #41 (spec+engine), #42 became wiring only; the stack branches were fast-forwarded, so the local branch claude/no-bypass-labels-wt is stale: reset it to origin before any mergify stack push Undo: revert the commit; nothing built on it ([#41](https://github.com/mark-brannan/languette/pull/41))
- An MCP tool is a write unless its name says list/get/search/read; any field whose name says label is read, one that says ID is refused (no-bypass-labels) Undo: revert the commit; nothing built on it ([#41](https://github.com/mark-brannan/languette/pull/41))

### 20261004t082011z
- gh alias set with a bypass label in its expansion denies; gh alias import is refused unread (no-bypass-labels) Undo: revert the commit; nothing built on it ([#41](https://github.com/mark-brannan/languette/pull/41))

### 20261004t083037z
- no-bypass-labels trusts a file it reads (--input, -F @file) only when nothing but gh, cd/pushd/popd/true/: and shells running quoted text is in the call Undo: drop _alone; one function ([#41](https://github.com/mark-brannan/languette/pull/41))
- An MCP tool reads only when its name leads with list/get/search/read and no later word is a write word (add, set, update, or, and, then, ...) Undo: match the read verb anywhere again; one function ([#41](https://github.com/mark-brannan/languette/pull/41))
- In an MCP tool whose name says label, every string field is read as a candidate label name Undo: drop the any_string branch in _mcp ([#41](https://github.com/mark-brannan/languette/pull/41))
- gh api --input is read on every path; a non-JSON payload denies only on a known label path, while stdin with no heredoc denies on any path Undo: restore the LABEL_PATH gate on --input ([#41](https://github.com/mark-brannan/languette/pull/41))

### 20261004t084420z
- MCP read-tool detection stays a denylist of write words after the read verb, widened (modify, change, tag, attach, delete, ...), rather than an allowlist of read-tool names Undo: an allowlist of whole read-tool names instead ([#41](https://github.com/mark-brannan/languette/pull/41))
- true, : and cd may share a call with a file-reading gh even with a redirect, since they can only truncate the file; pushd and popd may not, since they print the stack Undo: refuse any redirect in the call instead ([#41](https://github.com/mark-brannan/languette/pull/41))

### 20261004t114814z
- no-perm-sweep, no-pipe-to-shell and no-disk-wreck each ship in both engines (awk hook and Python guard), run from one scenario file Undo: delete the Python guard and drop @python from the feature; the hook keeps working ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261004t114823z
- LANGUETTE_PERM_ALLOW takes absolute paths only, no bare names (no-perm-sweep) Undo: accept names as no-rm-tree does; one case in parse_allow in the hook and the guard ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261004t114824z
- chmod 777 is judged like a sweep (allowed inside the agent's areas) rather than denied everywhere (no-perm-sweep) Undo: drop the allowlist step for the world-writable case; one branch in perm() ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261004t114825z
- a recursive target inside any .git is denied even in an agent's area (no-perm-sweep) Undo: drop the .git component check in target() ([#55](https://github.com/mark-brannan/languette/pull/55))
- shutdown, reboot, halt and poweroff match at command position, so sudo -u root reboot is a known false allow (no-disk-wreck) Undo: match the words anywhere in a segment and accept false denies on npm run halt ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261004t192745z
- env -C, sudo -D and sudo -R (a chroot) count as a cd in every spelling getopt takes (attached, clustered, a long-option prefix); only the options of the wrapper itself are read, and one the guard does not know errs toward denying a relative path (no-perm-sweep, no-disk-wreck) Undo: match the detached -C, -D and --chdir spellings only; one regex in paths.chdir_wrapper and chdirw() in the two hooks ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261007t041411z
- no-ruleset-bypass denies a push to a PR-only default branch rather than asking; the user's bypass stays in their own terminal Undo: deny( -> ask( in _judge ([#64](https://github.com/mark-brannan/languette/pull/64))
- no-ruleset-bypass also denies gh pr merge --admin, the same bypass through another door Undo: drop _admin_merge ([#64](https://github.com/mark-brannan/languette/pull/64))
- no-ruleset-bypass asks GitHub only for the remote's default branch, so feature pushes stay offline Undo: hits = dsts in _judge ([#64](https://github.com/mark-brannan/languette/pull/64))
- no-ruleset-bypass reads GitHub's 403 'upgrade to Pro' as no rules, so free private repos push freely Undo: drop the upgrade branch in _requires_pr ([#64](https://github.com/mark-brannan/languette/pull/64))
### 20261004t192604z
- no-iac-destroy is one toggle (no_iac_destroy) covering the destroys and the unattended applies (apply -auto-approve, pulumi up --yes, cdk deploy --require-approval never) alike Undo: split the three apply rules behind their own option in hooks.json and plugin.json ([#54](https://github.com/mark-brannan/languette/pull/54))

### 20261007t063804z
- no-ruleset-bypass watches main and master beside the remote's HEAD, since that HEAD is a local ref the agent can move Undo: defaults = [the remote HEAD's branch] alone in _judge ([#64](https://github.com/mark-brannan/languette/pull/64))
- no-ruleset-bypass asks after a cd the shell may undo before the push (subshell, group, pipe, ||) or a popd, rather than trusting the cd Undo: drop _UNDOES_CD and the popd clause in _walk ([#64](https://github.com/mark-brannan/languette/pull/64))
### 20261007t011723z
- A text that only might be shell (a nested string, the heredoc-stripped text) that shfmt refuses is read by the awk rung; only the command itself is denied Undo: make Scan raise Unparseable for every text ([#62](https://github.com/mark-brannan/languette/pull/62))
- The shfmt rung keeps the token contract by running the awk lexer over the AST's pieces; the four awk-shaped rows are not re-baselined Undo: map the AST directly and re-baseline those rows ([#62](https://github.com/mark-brannan/languette/pull/62))
- shfmt reads as bash (-ln=bash) Undo: change the flag in _shfmt_tree ([#62](https://github.com/mark-brannan/languette/pull/62))
- The awk rung in run.py is scan.py's port of lib-shell-words.awk, not a subprocess awk Undo: shell out to awk in the awk rung ([#62](https://github.com/mark-brannan/languette/pull/62))

### 20261007t011724z
- Branched from main while #52 is open, Depends-On: #52 holding the merge Undo: rebase onto #52's head ([#62](https://github.com/mark-brannan/languette/pull/62))
### 20261004t192604z
- no-iac-destroy is one toggle (no_iac_destroy) covering the destroys and the unattended applies (apply -auto-approve, pulumi up --yes, cdk deploy --require-approval never) alike Undo: split the three apply rules behind their own option in hooks.json and plugin.json ([#54](https://github.com/mark-brannan/languette/pull/54))

### 20261007t095052z
- With parse_check=false, the other Python guards read an unparseable Bash command on the awk rung instead of skipping it (the bot's fix); the alternative was denying it outright as before the split Undo: revert e6196ea ([#65](https://github.com/mark-brannan/languette/pull/65))

### 20261007t105057z
- The #55 guards take the curia's names, so the entries above that name them read under the old ones: no-perm-sweep is guard-permissions, no-pipe-to-shell is guard-pipe-to-shell, and no-disk-wreck splits three ways in both engines: guard-disk (dd, mkfs, wipefs, shred, a write onto a device, the cd-into-/dev tracking), guard-host-availability (shutdown, reboot, halt, poweroff, the fork bomb) and guard-scheduled-jobs (crontab -r). Their hooks.json entries run run.py, as guard-recursive-delete's does Undo: git revert the rename-and-split commit on #55 ([#55](https://github.com/mark-brannan/languette/pull/55))

### 20261007t114536z
- The three stub guards are listed in the README's guard list, marked (planned), not in a line under Development. Undo: move the bullet back to the line under Development ([#69](https://github.com/mark-brannan/languette/pull/69))

### 20261007t193515z
- bash -n sits below the pip slot and above awk on the parser ladder; the ruling names shfmt, pip, awk, and bash -n was not on it Undo: reorder scan.RUNGS ([#74](https://github.com/mark-brannan/languette/pull/74))
- The awk rung refuses only a quote left open at the end, read by the lexer's own rules after heredoc bodies are stripped Undo: drop _awk's raise in scan.py ([#74](https://github.com/mark-brannan/languette/pull/74))
### 20261007t214340z
- Facts the payload and env carry stay plain arguments to check, not Needs; only facts that need I/O are asked for. Undo: add an env Need kind answered in run.py and route guards' env reads through it ([#81](https://github.com/mark-brannan/languette/pull/81))

### 20261007t223657z
- A tool result the click parser does not recognise as a refusal counts as a call that ran, so its click stays spent; only a declined prompt, a hook error, the classifier or a languette guard's deny gives it back. Undo: widen the refusal pattern in languette/world.py, or treat every error other than 'Exit code N' as never ran ([#81](https://github.com/mark-brannan/languette/pull/81))
- A payload without tool_use_id spends its click for good, as before this PR, rather than matching the call by its command in the transcript. Undo: find the call as the latest unanswered Bash tool_use whose command matches the payload's ([#81](https://github.com/mark-brannan/languette/pull/81))

### 20261007t232027z
- Smoke job pins bashlex 0.18, tree-sitter 0.26.0, tree-sitter-bash 0.25.1, the versions measured green Undo: drop the ==version pins in ci.yml's smoke job ([#73](https://github.com/mark-brannan/languette/pull/73))

### 20261008t003728z
- Redaction keeps the command and guards' reasons whole and masks only secret-looking values (credential-named variables and flags, URL passwords, token shapes, long random strings); raw mode masks nothing Undo: edit SECRETS in languette/record.py (mark-brannan/languette#82)
- Records live at $XDG_STATE_HOME/languette/decisions.jsonl, rotated at 8 MiB keeping one .1 Undo: change RECORDS/RECORDS_MAX in languette/world.py (mark-brannan/languette#82)
- Two opt-in booleans, record_decisions and record_raw_commands, as plugin options Undo: rename the keys in plugin.json and record.py (mark-brannan/languette#82)

### 20261008t011048z
- gitleaks' finding on the synthetic curl -u fixture is ignored by fingerprint in .gitleaksignore, not removed by rewriting the branch Undo: delete .gitleaksignore (once squash-merged, main never holds the commit it names) (mark-brannan/languette#89)
