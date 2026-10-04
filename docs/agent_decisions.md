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
