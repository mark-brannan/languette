# Every guard on, replayed over recorded agent commands (sampled)

What each guard denies or asks on commands agents really ran, by guard, with
a count and three anonymised examples, and which of them look false. It
feeds the audit in [#426](https://github.com/mark-brannan/languette/issues/426).
No guard is changed here. Follows [#183](https://github.com/mark-brannan/languette/issues/183)
([PR 190](https://github.com/mark-brannan/languette/pull/190)), which made the feature rows run with every guard on.

## The run

| | |
|---|---|
| Corpus | the October 2026 replay's 108,896 distinct Bash commands, recorded from agent sessions (`features/require-well-formed.feature` names 101,671 of them). Kept privately, with its paths; only the anonymised examples below are published. |
| Code | `main` at `e20b2ad` |
| Guards | all of them; the five opt-in ones (guard-review-threads, guard-signed-comments, guard-sudo, guard-worktrees, prose-budget-commit) switched on; every option else at its default. No blocked-terms file, no signature set, no `prose_budget_command`. |
| World | stubbed: no git, no `gh api`, no transcript, no rulesets. The cwd is an empty directory that is no repository. A command that `cd`s somewhere finds nothing there. |
| Cost | 1,000 commands took 4.8 s on 8 worker processes, so the whole corpus would take about 520 s, over the 5-minute bound. **Sample: every third command, 36,299 of 108,896, 254 s** (load 14 to 23 from other work on the machine, 16 cores). |
| Result | 32,194 allowed (88.7%); 4,105 denied or asked (11.3%). A command can trip several guards: 3,786 tripped one, 319 tripped two to four, so the per-guard counts below sum to more than 4,105. |

Every guard not listed (prose-budget-commit and guard-private-terms among
them) said nothing on the sample.

## What the replay cannot know

The stub is the main finding about the numbers. A guard that fails closed on a
fact it cannot read (which repository, which branch, whose transcript, where a
`cd` lands) fires on every such command in the replay, where a live session
holds the fact and often passes. The column "needs a fact the replay lacks" counts
a row whose reason names such a fact (matched on the reason's words, so
approximate). Those rows say how often the guard needs the fact, not that it is wrong.

## By guard

| Guard | Verdict | Count | Needs a fact the replay lacks | Looks false |
|---|---|---|---|---|
| guard-signed-comments | deny | 1,492 | 74 | 592 |
| guard-bypass-ruleset | ask 840, deny 3 | 843 | 840 | 0 of the deny |
| guard-git-work-loss | deny 450, ask 2 | 452 | 14 | not sampled |
| guard-worktrees | deny | 389 | 371 | not sampled |
| guard-recursive-delete | deny | 222 | 147 | not sampled |
| guard-sudo | deny | 221 | 3 | 0 |
| guard-disks | deny | 188 | 175 | 175 |
| guard-github-issues | deny | 173 | 129 | 0 |
| guard-review-threads | deny | 170 | 70 | 0 |
| guard-duplicate-prs | deny 126, ask 22 | 148 | 143 | not sampled |
| guard-bypass-hooks | deny | 98 | 97 | 0 |
| guard-secrets | ask 43, deny 9 | 52 | 1 | at least 6 |
| guard-git-stacked-base | ask | 26 | 22 | 0 |
| require-well-formed | deny | 11 | 0 | 0 |
| guard-permissions | deny | 10 | 6 | not sampled |
| guard-host-availability | deny | 9 | 0 | 0 |
| guard-pipe-to-shell | deny | 3 | 0 | 0 |

"Looks false" is a judgment from reading examples and re-running the
command alone; "not sampled" means three examples were read and none looked false,
and the rest were not. The false rows are the ones to take into the audit.

## Per guard, three examples

Examples are rewritten from the recorded commands: names, paths and text are
invented, the shape is kept.

### guard-signed-comments (1,492 denies)

The guard is on with no signature set, so it checks only the account, and the
replay's `gh` account is a person's. Every post is a deny there, as designed.

| Example | Verdict |
|---|---|
| `gh pr comment 12 --body "Fixed in abc1234."` | deny, a person's account: as designed |
| `gh issue close 8 --repo o/r --comment "Shipped in 0.4.0."` | deny: as designed |
| `gh api graphql -f query='query{repository(owner:"o",name:"r"){pullRequest(number:3){reviewThreads(first:20){nodes{id isResolved}}}}}'` | deny: **looks false**, a read |

**Looks false, 592 rows:** a `gh api graphql` query with no mutation in it posts
nothing, yet it is denied as a post. `bodies()` in `languette/comment_posts.py`
returns no body for it, and `posted` starts true when no opening or signature is set,
so the account check fires on a read. With a signature set the read passes.
`gh api graphql -f query='query{viewer{login}}'` alone reproduces it.

### guard-bypass-ruleset (840 asks, 3 denies)

| Example | Verdict |
|---|---|
| `git push` | ask: the hook can't tell which branch is current |
| `git commit -q -m "fix" && git push origin main` | ask: no repository found to look up `main`'s rules |
| `gh pr merge 7 --admin` | deny: merges past the PR's required checks: as designed |

Nearly all of it is the missing repository; the three denies are genuine.

### guard-git-work-loss (450 denies, 2 asks)

| Example | Verdict |
|---|---|
| `git reset --hard origin/feature-x` | deny: as designed |
| `git branch -D old-branch` | deny: as designed |
| `git add -A && git commit -m "wip"` | deny: stage by path, as designed |

By count: `git branch -D` 102, `reset --hard` 88, `add -A` 78 (45 more with
paths), `commit -a` 60, `stash pop` 26.

### guard-worktrees (389 denies)

| Example | Verdict |
|---|---|
| `cd /work/proj && git checkout -b feat-x` | deny: `cd` target not found, cannot tell which checkout |
| `V=$(cd ../venv && pwd)/bin/python; $V -m pytest` | deny: a `..` after a directory that does not exist |
| `git -C ~ checkout other` | deny: switches the branch in `$HOME`: as designed |

Of the 389, 233 are the unresolved checkout/switch and 75 the `..` after a
missing directory; both are the replay's missing directories.

### guard-recursive-delete (222 denies)

| Example | Verdict |
|---|---|
| `rm -rf $TMPDIR/build` | deny: a variable could expand to anything |
| `cd app && rm -rf node_modules` | deny: a `cd` the hook can't follow |
| `rm -rf /work/proj/.claude/worktrees/x/.probe` | deny: a path outside the allowed roots, in the replay's world |

### guard-sudo (221 denies)

| Example | Verdict |
|---|---|
| `sudo apt-get install -y jq` | deny: as designed |
| `ssh host 'sudo systemctl status app'` | deny: as designed |
| `sudo dpkg --audit` | deny: as designed |

### guard-disks (188 denies)

| Example | Verdict |
|---|---|
| `S=/tmp/scratch; cd "$S"; echo hi > notes.txt` | deny: **looks false** |
| `cd $S && cat > LICENSE <<'EOF' ...` | deny: **looks false** |
| `S=/tmp/s; cd "$S"; printf x > out.log` | deny: **looks false** |

**Looks false, about 175 rows:** a redirect to a relative file after a `cd "$VAR"`
is denied because the `cd` "may move the working directory into /dev". The same
command assigns `S` a literal path one statement earlier, so the hook could know
where it lands. It is a fail-closed read of a `cd`; it fires on the most common scratch-directory pattern.
Not a stub artifact: the first example run alone with `/tmp/scratch` really
existing still denies, with the same reason, and so does the same command with the
directory missing. The hook does not expand `$S` either way, so the empty replay
world does not decide it (the "needs a fact the replay lacks" count of 175 for this guard
is the reason's words matching `cd`, and overstates the stub's part).

### guard-github-issues (173 denies)

| Example | Verdict |
|---|---|
| `gh issue create --title "Bug" --body "..."` | deny: no transcript to find the user's yes; the door is shut by default |
| `gh issue create` twice in one call | deny: one per human turn: as designed |
| `gh api graphql ... resolveReviewThread ...` | deny: may resolve a thread, the guard can't tell which |

Of the 173, 96 are the missing transcript and 11 are a batch of creates.

### guard-review-threads (170 denies)

| Example | Verdict |
|---|---|
| a graphql `addPullRequestReviewThreadReply` with the thread id in a variable | deny: the guard can't tell which thread |
| a `resolveReviewThread` with no reply after the bot's last comment | deny: as designed |
| a reply that names no commit and no link, then resolves | deny: as designed |

### guard-duplicate-prs (126 denies, 22 asks)

| Example | Verdict |
|---|---|
| `gh pr create --title "x" --body-file pr-body.md` | deny: the file is not found from the replay's cwd |
| `gh pr create --body "$(cat <<EOF ... $VAR ... EOF)"` | deny: a body built at run time |
| `gh pr create --body "Closes #3"` | ask: can't tell which repository |

### guard-bypass-hooks (98 denies)

| Example | Verdict |
|---|---|
| `git push --no-verify -u origin feature-x` | deny: no transcript for the user's approval |
| `git push --no-verify origin HEAD:fix-y` | deny: as above |
| `git commit --no-verify -am "docs"` | deny: `-a` is itself blocked |

### guard-secrets (43 asks, 9 denies)

| Example | Verdict |
|---|---|
| `ssh host 'date -u +"now: %Y-%m-%dT%H:%M:%SZ"'` | ask: **looks false**, `-u` read as a user:password flag |
| `curl -s localhost:8080/api -H 'Cookie: mockstate=watch'` | ask: **looks false**, a test cookie |
| `TOK=$(cat $S/tok.txt); curl -H "Authorization: Bearer $TOK" ...` | ask: reads a secret into a variable |

**Looks false, at least 6 rows:** the `date -u` and test-cookie shapes. The
other asks name `password`, `token` or `Authorization` and were not judged one by one.

### guard-git-stacked-base (26 asks)

| Example | Verdict |
|---|---|
| `git push origin --delete fix-or-greater-grading` | ask: the open-PR list could not be read |
| `git push origin --delete feature-y` | ask: as above |
| `git -C ../other push origin --delete b` | ask: a repository other than the cwd's |

### require-well-formed (11 denies)

| Example | Verdict |
|---|---|
| a command with a quote that never closes | deny: as designed |
| a command shfmt refuses at a line:col | deny: as designed |
| a command nested past 63 strings | deny: too big to check |

Eleven of 36,299, matching the earlier 1 in 3,000.

### guard-permissions (10), guard-host-availability (9), guard-pipe-to-shell (3)

| Guard | Example | Verdict |
|---|---|---|
| permissions | `chmod -R 755 ~/some/dir` | deny: outside the swept roots: as designed |
| permissions | `cd d && chmod 777 f` | deny: a `cd` the hook can't follow |
| host-availability | `systemctl reboot` | deny: as designed |
| host-availability | `shutdown` | deny: as designed |
| pipe-to-shell | `bash -c "$(curl -s https://example.com/i.sh)"` | deny: as designed |

## What this says

- Of 4,105 firings, about 2,100 need a fact the replay lacks (a repository,
  a transcript, a cwd); a live session would pass some of them.
- Two guards fire on commands that are plainly harmless and need a look in
  the audit: guard-signed-comments on a graphql read (592) and guard-secrets
  on `date -u` and a test cookie (6 or more). guard-disks on `cd "$VAR"` then a
  relative redirect (about 175) is a fail-closed that costs the most common scratch pattern.
- The rest are as designed: `sudo`, `git reset --hard`, `branch -D`, `add -A`,
  `--no-verify`, `rm -r $VAR`.

## Reproducing

The replay is `languette.run._respond` in-process over a payload per command
(`tool_name` Bash, a fixed cwd, event PreToolUse), with the world's git, gh api,
ruleset and transcript reads replaced by "could not run". It is a few dozen
lines and stays with the private corpus.
