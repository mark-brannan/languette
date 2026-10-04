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
- no-checkout-home keeps every directory a cd may leave the shell in as a candidate (scanner drops subshell parens), so cd elsewhere from a session in $HOME then git checkout is denied Undo: resolve cd sequentially (replace the candidate set) and accept the subshell false allow ([#37](https://github.com/mark-brannan/languette/pull/37))
