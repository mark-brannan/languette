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

### 20261007t193847z
- A tree-sitter MISSING node gives a column, like an ERROR node Undo: drop 'or n.is_missing' in scan._ts_error ([#75](https://github.com/mark-brannan/languette/pull/75))

### 20261007t193848z
- A tree-sitter crash or failed import adds no column; the refusal stands as its rung wrote it Undo: raise in scan._tree_sitter's except ([#75](https://github.com/mark-brannan/languette/pull/75))

### 20261007t232120z
- tree-sitter's in-process parse has no timeout, unlike shfmt and bash -n; it runs only on text a rung already refused. Measured: 0.4 s for 200,000 commands and 3 ms for 3,000 nested substitutions Undo: pass a progress_callback to parser.parse in scan._tree_sitter that stops it after a deadline ([#75](https://github.com/mark-brannan/languette/pull/75))

### 20261008t000000z
- The column reads `<rung's message>, at L:C per tree-sitter-bash`, after the deciding rung's own words, which keep bash's line Undo: reformat in scan.parse ([#75](https://github.com/mark-brannan/languette/pull/75))
### 20261007t214340z
- Facts the payload and env carry stay plain arguments to check, not Needs; only facts that need I/O are asked for. Undo: add an env Need kind answered in run.py and route guards' env reads through it ([#81](https://github.com/mark-brannan/languette/pull/81))

### 20261007t223657z
- A tool result the click parser does not recognise as a refusal counts as a call that ran, so its click stays spent; only a declined prompt, a hook error, the classifier or a languette guard's deny gives it back. Undo: widen the refusal pattern in languette/world.py, or treat every error other than 'Exit code N' as never ran ([#81](https://github.com/mark-brannan/languette/pull/81))
- A payload without tool_use_id spends its click for good, as before this PR, rather than matching the call by its command in the transcript. Undo: find the call as the latest unanswered Bash tool_use whose command matches the payload's ([#81](https://github.com/mark-brannan/languette/pull/81))

### 20261007t232027z
- Smoke job pins bashlex 0.18, tree-sitter 0.26.0, tree-sitter-bash 0.25.1, the versions measured green Undo: drop the ==version pins in ci.yml's smoke job ([#73](https://github.com/mark-brannan/languette/pull/73))

### 20261008t004250z
- Restore the six deleted shell headers' spec into the Python guards' docstrings, shell mechanics reworded Undo: git revert bca98fb ([#72](https://github.com/mark-brannan/languette/pull/72))
### 20261008t003728z
- Redaction keeps the command and guards' reasons whole and masks only secret-looking values (credential-named variables and flags, URL passwords, token shapes, long random strings); raw mode masks nothing Undo: edit SECRETS in languette/record.py (mark-brannan/languette#82)
- Records live at $XDG_STATE_HOME/languette/decisions.jsonl, rotated at 8 MiB keeping one .1 Undo: change RECORDS/RECORDS_MAX in languette/world.py (mark-brannan/languette#82)
- Two opt-in booleans, record_decisions and record_raw_commands, as plugin options Undo: rename the keys in plugin.json and record.py (mark-brannan/languette#82)

### 20261008t011048z
- gitleaks' finding on the synthetic curl -u fixture is ignored by fingerprint in .gitleaksignore, not removed by rewriting the branch Undo: delete .gitleaksignore (once squash-merged, main never holds the commit it names) (mark-brannan/languette#89)

### 20261008t011533z
- A refspec $NAME is read as the literal export NAME=lit set; declare, typeset and local turn resolution off for the line Undo: widen _Literals in guard_bypass_ruleset.py ([#91](https://github.com/mark-brannan/languette/pull/91))
- NAME=lit; git push (a ; not &&) is trusted though a readonly NAME inherited from the shell would make the set fail; shell-set names are excluded Undo: require && between the set and the push ([#91](https://github.com/mark-brannan/languette/pull/91))
- A . in command position or any shell keyword on the line turns literal resolution off, stricter than needed Undo: narrow _RESERVED in guard_bypass_ruleset.py ([#91](https://github.com/mark-brannan/languette/pull/91))

### 20261008t014318z
- A parser killed by a signal denies instead of falling to the next rung (kill -9 moved out of the crash test) Undo: drop the returncode < 0 check in scan._run ([#93](https://github.com/mark-brannan/languette/pull/93))
- An OSError other than FileNotFoundError running a parser denies Undo: catch OSError with FileNotFoundError in scan._run ([#93](https://github.com/mark-brannan/languette/pull/93))

### 20261008t021218z
- The nesting limit is 10,000 weight (~450 ms of shfmt at 0.25 CPU, 4x under its 2 s timeout); the length limit is 64 KB Undo: raise WEIGHT_MAX in scan.py ([#93](https://github.com/mark-brannan/languette/pull/93))
- A nested text over the limit raises through Scan like RunFailed, never falls to awk Undo: let Scan catch TooBig and fall to awk ([#93](https://github.com/mark-brannan/languette/pull/93))
### 20261008t012656z
- Any bashlex error that carries a position gives the column, not only an open pair or an early end; a bashlex grammar gap (`[[ ]]`, a quoted heredoc delimiter) can then point at a spot other than the rung's fault Undo: in scan._bashlex, return None unless the error is a MatchedPairError or 'unexpected EOF' ([#77](https://github.com/mark-brannan/languette/pull/77))
- A bashlex crash, failed import, or error with no position adds no column; the refusal stands as its rung wrote it Undo: raise in scan._bashlex's except ([#77](https://github.com/mark-brannan/languette/pull/77))
- bashlex's in-process parse has no timeout; it runs only on text a rung refused and tree-sitter left without a column. Measured, bashlex 0.18: 0.9 s for 20,000 commands (180 KB), 0 s for 3,000 nested substitutions (no column) Undo: run bashlex in a subprocess with a deadline, as bash -n runs ([#77](https://github.com/mark-brannan/languette/pull/77))

### 20261008t034107z
- guard-secrets: a context-only hit asks and a shape hit denies; the verdict layer can remap once #76 settles Undo: in guard_secrets.check, return deny for contexts too ([#97](https://github.com/mark-brannan/languette/pull/97))
- guard-secrets: short options other than -u (-p and the rest) are not read as credentials; too many other meanings Undo: add the option to secrets._OPTS ([#97](https://github.com/mark-brannan/languette/pull/97))
- secrets.redact masks the value, not the key: GITHUB_TOKEN=**** Undo: widen the Finding span to the whole word ([#97](https://github.com/mark-brannan/languette/pull/97))
- guard-secrets: -u user:pass and --user user:pass are read as a credential; other short options still are not Undo: drop the _USER_OPTS branch in secrets._context ([#97](https://github.com/mark-brannan/languette/pull/97))
- guard-secrets: a project pattern's regex is capped at 512 characters and may not reuse a shipped rule id; no backtracking bound beyond the hook's timeout Undo: drop the MAX_REGEX and _SHIPPED checks in guard_secrets._load ([#97](https://github.com/mark-brannan/languette/pull/97))
### 20261008t024021z
- A failed parser run (RunFailed: timeout, signal, OS) gets no pip-parser column; the column belongs to a refusal of the text, and a retry message with one reads as a syntax fault Undo: drop the isinstance(e, RunFailed) test in scan.parse ([#93](https://github.com/mark-brannan/languette/pull/93))

### 20261008t053753z
- A project secret pattern that nests one unbounded repeat inside another is refused, read from the stdlib regex parser (re._parser, sre_parse before 3.11); a time budget was not added, Solace's choice. Undo: delete _nested_repeat and its check in guard_secrets._load ([#97](https://github.com/mark-brannan/languette/pull/97))
### 20261008t034001z
- guard-git-work-loss, guard-git-stacked-base and guard-worktrees are ported in today's runner shape (a check that yields Needs), not epic #76's pure functions Undo: rework under #76 ([#96](https://github.com/mark-brannan/languette/pull/96))
- guard-git-stacked-base keeps `timeout 20 gh pr list` and asks when neither timeout nor gtimeout is installed, as its feature file says Undo: bound gh in World's subprocess call alone and drop the timeout rows from guard-git-stacked-base.feature ([#96](https://github.com/mark-brannan/languette/pull/96))
- guard-worktrees reads and writes its per-session record, globs for the scratchpad and stats claim-stamp.sh directly, not through World Undo: move them behind Needs under #76 ([#96](https://github.com/mark-brannan/languette/pull/96)) -- undone in #96 itself: they are World's `worktree` and `which` facts; the write still happens before the verdict, which is #76's
- checkout-home resolves a relative cd or -C that follows an earlier cd and judges where it lands; the shell denied it as unresolvable Undo: deny when the base is lost, as the shell did ([#96](https://github.com/mark-brannan/languette/pull/96))
- the fail-open paths claude-review found on #96 (a --config-env or --attr-source value read as the subcommand; an unresolvable --git-dir allowed; checkout-home with git absent allows; foreign with no cwd or no $HOME allows) stay as the shell has them: parity is W2's bar Undo: close each with a feature row, in its own PR ([#96](https://github.com/mark-brannan/languette/pull/96))

### 20261008t054436z
- README lists guard-secrets and guard-cross-session-send before #94 and #97 merge, and records the verdict log as a paragraph under Configuration to stay inside the 325-line cap Undo: drop the two bullets and two Reads rows if either PR closes; give the record a heading once a cap-raise lands ([#101](https://github.com/mark-brannan/languette/pull/101))
### 20261008t035451z
- W4 moves each deleted shell script's rationale into its feature file's description (ruling 1791421640d08e92b2 open) Undo: revert PR 100 ([#100](https://github.com/mark-brannan/languette/pull/100))
- the test harness keeps a subprocess engine for the hooks.json wiring scenarios, renamed shell to hook, and drops the four no-jq-or-awk scenarios Undo: revert PR 100 ([#100](https://github.com/mark-brannan/languette/pull/100))

### 20261008t053443z
- the two bash suites (guard-private-terms, guard-worktrees) stay, moved to tests/ and pointed at languette/run.py: about 200 of their ~306 cases have no feature scenario yet, and all but the obsolete no-awk case pass on the Python guards Undo: delete tests/*.test.sh and their CI steps once features/ holds the cases ([#100](https://github.com/mark-brannan/languette/pull/100))

### 20261008t184222z
- guard-github-issues, guard-private-terms and prose-budget-commit are ported in today's runner shape (a check that yields Needs), not epic #76's pure functions Undo: rework under #76 ([#98](https://github.com/mark-brannan/languette/pull/98))
- prose-budget-commit's engine is the command the prose_budget_command option names (empty: prose-budget on PATH); the Python guard no longer reads PROSE_BUDGET Undo: revert ([#98](https://github.com/mark-brannan/languette/pull/98))
- prose-budget-commit denies on engine exit 2, a bad budgets config (ruling 179108882424d36c8d open) Undo: change rc == 2 in prose_budget_commit.py ([#98](https://github.com/mark-brannan/languette/pull/98))
- guard-github-issues reads the hook event from the payload's hook_event_name, not a prompt/post argument Undo: add an --event argument to run.py ([#98](https://github.com/mark-brannan/languette/pull/98))
- three differences from the shell: an unreadable or directory --body-file denies; an engine past 50 s counts as a crash (no-op); with python3 absent all three deny on their PreToolUse matcher Undo: restore each shell behaviour with a feature row ([#98](https://github.com/mark-brannan/languette/pull/98))
- the PR 98 review's three findings (whole-command HOME rewrite, allow skipping the permission prompt, engine failures as no-ops) stay as the shell has them: parity is W3's bar Undo: close each with a feature row, in its own PR ([#98](https://github.com/mark-brannan/languette/pull/98))
### 20261008t184358z
- guard-secrets: a credential key=value inside a word (after =, ?, &, ;, comma, { or a space) is read as context, its value ending at the next &, comma, ;, } or space Undo: drop the _INNER loop in secrets._context ([#97](https://github.com/mark-brannan/languette/pull/97))

### 20261009t023954z
- purity check walks languette modules the guards import, not only guards and verdict Undo: drop _pure()'s import walk ([#111](https://github.com/mark-brannan/languette/pull/111))

### 20261009t023957z
- HEAD's purity escapes kept as a shrink-only KNOWN list so the PR stays test-only Undo: delete KNOWN once they are Needs ([#111](https://github.com/mark-brannan/languette/pull/111))

### 20261009t024221z
- The purity check also walks the languette modules the guards import, beyond the design doc's guards and the verdict Undo: drop _pure()'s import walk ([#111](https://github.com/mark-brannan/languette/pull/111))

### 20261009t024224z
- HEAD's purity escapes are a shrink-only KNOWN list in the test, not fixed in the test-only PR Undo: delete KNOWN once each escape is a Need ([#111](https://github.com/mark-brannan/languette/pull/111))

### 20261009t024227z
- scan.py's shfmt run is a listed known escape, not an exemption Undo: exempt it in the test ([#111](https://github.com/mark-brannan/languette/pull/111))

### 20261009t040047z
- Door open and spend became acts too, though the brief named four primitives; only claim and take were held back Undo: yield Need door again and restore _door's two ops ([#115](https://github.com/mark-brannan/languette/pull/115))

### 20261009t040049z
- Acts run after every verdict, deny included: a deny skipping worktree-keep would lose a session's first-call adoption Undo: skip world.act in respond() on a deny ([#115](https://github.com/mark-brannan/languette/pull/115))

### 20261009t040051z
- The writes_in_acts fixture gates OS write calls during respond, not only World's act methods Undo: wrap only the ACTS methods ([#115](https://github.com/mark-brannan/languette/pull/115))

### 20261009t041509z
- guard-host-availability keeps only the units nobody stops but to chaos-test the host (dbus, logind, a login session, the run-level targets); ssh, the network, the display manager and getty move to guard-protected-services as its default list Undo: move names between _CORE in guard_host_availability.py and DEFAULT in guard_protected_services.py, with their feature rows ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t041510z
- a protected_services value the user sets replaces the default list, as bypass_labels does, so a power user can drop sshd without turning the guard off Undo: in protected(), return DEFAULT plus the set patterns, and flip the feature row 'a set list replaces the defaults' ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t043310z
- guard-protected-services: ssh, the network, the display manager and getty move from guard-host-availability to the new guard's default list; dbus, logind, login sessions and run-level targets stay Undo: move names between _CORE and DEFAULT with their feature rows ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t043312z
- protected_services: a set list replaces the default list, as bypass_labels does, not adds to it Undo: protected() returns DEFAULT plus the set patterns ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t055700z
- guard-protected-services: ssh, sshd, NetworkManager, systemd-networkd, the network targets, the display managers and getty move from guard-host-availability to the new guard's default list; dbus, logind, login sessions and run-level targets stay Undo: move names between _CORE and DEFAULT with their feature rows ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t055703z
- protected_services: a set list replaces the default list, as bypass_labels does, instead of adding to it as issue #113 said Undo: protected() returns DEFAULT plus the set patterns ([#116](https://github.com/mark-brannan/languette/pull/116))

### 20261009t070910z
- guard-review-threads denies when GitHub cannot be read, where guard-git-stacked-base and guard-bypass-ruleset ask: a thread left open costs a click, one closed unread hides a finding Undo: return ask() instead of deny() in check()'s unreadable branch and its scenario ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070913z
- guard-review-threads counts a sha only when its 7 to 40 hex characters hold a digit and a letter, so a number or a word like 'effaced' is not a commit Undo: drop the two lookaheads in SHA and the two scenario rows ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070917z
- guard-review-threads also counts an author GitHub's GraphQL types as Bot, since GraphQL gives bot logins without the [bot] suffix Undo: drop the __typename test in _bot and its row ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070920z
- guard-review-threads reads a thread's last 100 comments; a longer thread's earlier comments go unread Undo: page comments backwards in _thread ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070923z
- guard-review-threads does not see a resolve whose query it cannot read (a variable, @file); the gap is named in the feature Undo: deny any gh api graphql call whose query is unreadable and that names a PRRT_ id ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070926z
- guard-review-threads' deny names a ruling, decision record or issue as the record, not cards or hand-over lines, since the repo's CLAUDE.md names nothing from the host's own workflow Undo: edit DO in guard_review_threads.py ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070929z
- README gets guard-review-threads only in the Reads table: The guards section is at its 232-word cap and a bullet needs the cap raised in its own PR Undo: raise the cap in its own PR, then add the bullet ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t070933z
- guard-review-threads reads GitHub through the existing run Need, not a new gather kind Undo: add a gh-graphql read kind to world.KINDS and yield it from _thread ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t071255z
- guard-review-threads denies a graphql call whose query it cannot read (a run-time word, query=@file, --input with no heredoc) when it names a PRRT_ id or the command names a resolve; a file-read query naming no thread passes. Supersedes the unseen-query gap above Undo: drop the hidden clause in _resolves and its rows ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t071321z
- guard-signed-comments defaults to on, like every guard but guard-worktrees Undo: default false in .claude-plugin/plugin.json and add guard_signed_comments to OPT_IN in tests/test_repo.py ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071328z
- guard-signed-comments gates Bash only; the GitHub MCP comment and review tools are not gated yet Undo: give the guard a TOOLS pattern and an MCP branch, as guard-private-terms has ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071336z
- guard-signed-comments gates comment edits too: a non-GET gh api on a comments path and the three graphql update mutations Undo: drop updateIssueComment, updatePullRequestReviewComment and updatePullRequestReview from _MUTATION and gate only POST on a comments path ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071344z
- guard-signed-comments checks the signature's eight hex for shape only, so a subagent may sign with its agent id Undo: compare the eight hex to the payload's session_id[:8] ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071350z
- guard-signed-comments denies a relative --body-file after a cd in the same command rather than replaying the cd Undo: replay the cd with guard-private-terms' _Replay ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071358z
- guard-signed-comments passes an empty body (gh refuses an empty comment; an approve with --body "" posts no text) and trailing whitespace on the signature line Undo: drop the body.strip() skip and the rstrip() in check ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071405z
- guard-signed-comments is silent on a graphql query it cannot read, which is not known to post, as guard-private-terms reads it Undo: deny an unreadable query in bodies() ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071412z
- README trims 'for one kind of' and 'the other guards' and joins the ask-first bullet so the new guard's line fits the section and line caps Undo: restore the three README lines and raise the caps in docs/budgets.json in a PR of its own ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t071702z
- guard-review-threads denies every gh api graphql call whose query is out of sight (run-time, @file, --input with no heredoc), even a read; a run-time value in another field does not count. Supersedes the narrower rule above Undo: restore the names-a-thread condition on the hidden clause in _resolves ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t072014z
- guard-signed-comments denies an unreadable graphql query only when a body field or an --input payload travels with it; alone it stays silent (supersedes the earlier silent-on-unreadable call) Undo: deny every unreadable graphql query in bodies() ([#119](https://github.com/mark-brannan/languette/pull/119#discussion_r4227666481))

### 20261009t072022z
- guard-signed-comments gates discussion comments too (addDiscussionComment, updateDiscussionComment), past the brief's list Undo: drop addDiscussionComment and updateDiscussionComment from _MUTATION ([#119](https://github.com/mark-brannan/languette/pull/119#discussion_r4227669039))

### 20261009t073153z
- guard-signed-comments checks the signature's eight hex against the payload's session_id[:8] when the payload carries a hex one, shape only otherwise (supersedes the shape-only call): the CI review bot signed its re-review of #119 with this PR's example hex, not its own Undo: go back to shape only: drop the hexid comparison in check() ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t073202z
- guard-signed-comments denies an unreadable graphql query when any field besides query, or an --input payload, travels with it (supersedes the body-field-only call): -f text=... bound to body:$text posted unsigned; a read query with variables and an unreadable query is now denied too Undo: deny only when a body or [body] field or an --input travels with the unreadable query ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t073952z
- README keeps its existing guard-list wording as on main and omits guard-signed-comments' bullet, since even its bare name puts the section over the 232-word cap (supersedes the README-trims call); the reads table keeps its row Undo: raise the 'The guards' section cap to 236 in its own PR, then add the bullet ': unsigned agent comments' ([#119](https://github.com/mark-brannan/languette/pull/119#discussion_r4227758381)) ([#119](https://github.com/mark-brannan/languette/pull/119))

### 20261009t080848z
- guard-review-threads asks, not denies, when GitHub cannot be read or names no such thread, matching guard-git-stacked-base and guard-bypass-ruleset; the design doc is silent on it. Supersedes the deny entry above Undo: return deny() instead of ask() in check()'s GitHub-unreadable branch and its scenario ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t080900z
- guard-review-threads counts any 7 to 40 hex characters as a commit, all digits included (a short sha is all digits about 1 time in 27); the guard checks a record is named, not that it exists. Supersedes the digit-and-letter entry above Undo: restore the two lookaheads in SHA and move the 1234567 row back to the deny outline ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t080904z
- guard-review-threads lets a graphql query that opens with { or query pass whatever run-time values fill it (GraphQL runs no mutation from it without operationName), reads a file a -F field or --input names through gather when gh runs alone, and looks for the mutation only in the query; reads denied over 30 days of transcripts fall from 121 to at most 42 of 2603 graphql calls. Supersedes the deny-every-out-of-sight-query entry above Undo: make every run-time query and every @file or --input file unreadable again in _calls ([#118](https://github.com/mark-brannan/languette/pull/118))

### 20261009t093543z
- guard-bypass-labels' file read uses the existing read kind, extended with a byte cap, a non-blocking open and a regular-file check, not a new kind Undo: add a separate read kind and restore read to a plain open ([#114](https://github.com/mark-brannan/languette/issues/114)) (no PR, branch claude/pickup-1791538208011dbc62-7f6ea6)

### 20261009t093545z
- guard-recursive-delete drops its private physical and roots list for paths.physical and paths.own_roots Undo: restore the private copies, converted to Needs ([#114](https://github.com/mark-brannan/languette/issues/114)) (no PR, branch claude/pickup-1791538208011dbc62-7f6ea6)

### 20261009t191154z
- approved guard names: the Concept and Under the umbrella wording is the agent's, drawn from the README and the rename draft Undo: edit the row ([#130](https://github.com/mark-brannan/languette/pull/130))

### 20261009t192906z
- new-guard-names: CI job, not pre-commit; table read from the PR base, found by its heading anywhere under docs/; a renamed NAME counts as new Undo: drop or edit the new-guard-names job in ci.yml ([#132](https://github.com/mark-brannan/languette/pull/132))

### 20261009t205348z
- require-well-formed's Concept and Under the umbrella wording in docs/approved-guard-names.md is the agent's Undo: edit the row (no PR, branch claude/base-case-guard-names)

### 20261009t210003z
- approved guard names: after ask-first and deny-always, the guard- names sort alphabetically, not grouped by domain Undo: regroup the rows by domain ([#130](https://github.com/mark-brannan/languette/pull/130))

### 20261009t211657z
- README install: planned platform blocks point at the epic #102, not per-rung issues, until those exist Undo: repoint each (planned: …) marker at its own issue ([#102](https://github.com/mark-brannan/languette/issues/102)) (no PR, branch claude/languette-epic-scope-48cff1)

### 20261009t220047z
- run.py: a --guard name no registered guard has is a deny, not a silent pass, so a hook entry left on a renamed guard fails closed Undo: drop the unknown-name check in _respond and its test ([#140](https://github.com/mark-brannan/languette/pull/140))

### 20261009t220935z
- smoke: only the doctor's shell parser row is asserted per environment; the Claude Code row is ✗ in an empty HOME and ignored Undo: assert more rows in test_doctor_names_the_parser_in_use ([#142](https://github.com/mark-brannan/languette/pull/142))

### 20261009t220938z
- smoke: the bashlex and tree-sitter-bash doctor rows are strict xfails, since the doctor does not name a pip parser; no doctor change here Undo: name the pip parser in the doctor's row and drop the two DOCTOR xfail reasons ([#142](https://github.com/mark-brannan/languette/pull/142))

### 20261009t230316z
- smoke.feature: the lexer row checks the deny names awk literally, dropping the (?:awk|lexer) tolerance Undo: make the reader cell match awk or lexer ([#146](https://github.com/mark-brannan/languette/pull/146))

### 20261010t021210z
- doctor PR keeps the smoke suite's direct per-parser require-well-formed call alongside the doctor's parse check row (that call checks which parser read the command, and that echo ok passes silently) Undo: cut the smoke scenario 'require-well-formed denies an unclosed quote and allows echo ok' and assert the parse check row per machine instead ([#151](https://github.com/mark-brannan/languette/pull/151))

### 20261010t043139z
- publish.yml triggers on release published, not tag push Undo: change the on: block ([#154](https://github.com/mark-brannan/languette/pull/154))

### 20261010t044548z
- publish.yml is dispatched on a release tag only, matching the shared release workflow; a release trigger too would race it Undo: add a release: published trigger to the on: block ([#154](https://github.com/mark-brannan/languette/pull/154))
