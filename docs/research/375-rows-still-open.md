# What #375's findings still leave

Checked 2026-11-16 against main at `3d55675` (release 0.0.26). Each row of
[#375](https://github.com/mark-brannan/languette/issues/375) was read against the code and
the merged PRs that took rows from it: #373, #374, #376, #377, #371, #372, #390, #394 to #397,
#400 to #403 and #417 (and #378 and #380 before them, which the later bodies cite). Where a
PR body says a row was reproduced on main and is now gone, that is taken from the body; the
rows below were looked at again in the code.

Evidence column: **probed** is a command run against main today; **read** is the source (or a
test) read; **PR** is a merged PR's own measurement. Nothing here is a decision.

## Rows still open

| Theme | Where | What is left | Evidence | Why it stands |
|---|---|---|---|---|
| 1. Unjudged | `run.py`, `tests/test_ladder.py` | under `--guard X`, a command the parser refuses is silent (`echo 'unclosed` under `guard-recursive-delete` prints nothing); the test asserts it | probed | #400 and #402 both say "left alone, as asked": the test dates from when each guard had its own hook entry, and `require-well-formed` carries the deny today |
| 1. Unjudged / 8. Disagree | `branch_deletions.py`, `features/guard-git-stacked-base.feature` | `cd elsewhere && git push --delete` asks GitHub about the session's repo, not the one pushed to; the feature promises an ask for a repository other than the session's, which `git -C` gets and `cd` does not | probed (asks, naming the session's repo) | #402 and #403 "not changed": an ask on every `cd` is a cost to weigh |

## By theme

| Theme | Table rows in #375 (the issue says 77 findings; some rows hold several) | Still open |
|---|---|---|
| 1. Paths that let a call through unjudged | 13 | 2 (the `--guard` silence; `cd` then `push --delete`) |
| 2. False denies and asks | 3 | 0 |
| 3. One reading, many readers | 18 | 0 |
| 4. Wrong layer | 8 | 0 |
| 5. The suite's blind spots | 11, plus 3 shrinks | 0 |
| 6. Smaller robustness | 6 | 0 |
| 7. CI cost | 2 | 0 |
| 8. Document and code disagree | 4 | 1, the same row as the `cd` one in theme 1 |

## Closed, and where

The rest is gone. Each theme's closing PR, so a later reader need not re-check:

- Theme 1: #373 (`--delete` read by prefix and in a cluster), #376 (state-event crash and
  rule-set load), #377 (graphql `--input`, reassigned `$VAR`, rewritten body file), #417
  (`+=`, `read`, `printf -v`, `cat <<EOF > file`), #401 (`issue_writes` and `createIssue`
  in an `--input` file), #402 (`$$'` in the awk rung; `pkill -f` regex bound).
- Theme 2: #374 (`switch -C`, `commit -m checkout`), #417 (`BODY=$(cat <<'EOF'…)` in
  `opened_prs`), #421 (`infra_runs` in a mode that cannot ask).
- Theme 3: #403 (one git call, option prefix, `add_options`, ask-git closures), #401 (a `gh
  api` call writes, graphql, target repo), #417 (where a post's body comes from, absolute body
  paths, text-flag loops), #402 (basename, `operands` beside `getopt`, `UNRESOLVED` and
  `UNREADABLE`, secrets regex screen), #400 (the three target judges, session id to file name),
  #378 (read error to reason, run a program for stdout). I did not recount the text-flag loops
  past the six #417 names.
- Theme 4: #400, #394, #395, #402.
- Theme 5: #397 (crash flag, non-string command, planned rows, `KNOWN_PAYLOAD_READS`, `WALKS`,
  hooks.json and README held, Python floor test in `tests/test_run_fail_closed.py`), #396
  (a home per scenario, only the stubs named, helper shrinks); `NOT_READ_YET` is no longer
  in the tree. The three test drivers now go through `run.drive`.
- Theme 6: #395 (doctor timing sample ships, plugin list once, fallback text from `messages`),
  #400 (stdin once, a spend without `lost=`), #402 (heredoc time). `read_json`, the team
  config and the transcript now read at most `paths.MAX_READ` (the transcript its last
  `MAX_READ` bytes), and an unclosed heredoc ends the walk, so the text is held once.
- Theme 7: #390 (coverage on the uploading leg only); `new-guard-names` runs on pull requests
  only and `shellcheck` has `timeout-minutes: 1`.
- Theme 8: #397 (work-loss feature), #395 (doctor.md), the README list (held by a test).
