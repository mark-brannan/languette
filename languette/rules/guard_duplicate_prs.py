"""guard-duplicate-prs: features/guard-duplicate-prs.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a second open PR on an issue an open
PR already references is denied. The `pr-opens` test finds the PRs a call opens and the
bodies they carry, in a command or the MCP tool's input, so every match entry is a test;
the bodies' files and the issues' timelines on GitHub (GitLab's related merge requests)
are facts, read by the
`issue-timelines` handler (languette/opened_prs.py), which gives the verdict and asks when
GitHub cannot tell."""

RULE_SET = {
    "guard": "guard-duplicate-prs",
    "calls": "any",
    "rules": [{"id": "second-pr", "match": [{"test": "pr-opens"}], "action": "deny", "handler": "issue-timelines"}],
}
