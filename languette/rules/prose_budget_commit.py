"""prose-budget-commit: features/prose-budget-commit.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: before a `git commit`, the
prose-budget engine runs on what the commit would commit, and a finding is a warning,
never a block. The `prose-commits` test reads the command's commits from its words alone;
the engine on the machine, where the commit runs and what it reaches past the index are
facts, read by the `prose-budget` handler (languette/prose_commits.py), which gives the
warning."""

RULE_SET = {
    "guard": "prose-budget-commit",
    # Off unless the user turns it on: the warning is for repos whose CI runs prose-budget.
    "opt_in": "CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT",
    "rules": [{"id": "commit", "match": [{"test": "prose-commits"}], "action": "deny",
               "handler": "prose-budget"}],
}
