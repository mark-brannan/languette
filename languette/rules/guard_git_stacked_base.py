"""guard-git-stacked-base: features/guard-git-stacked-base.feature is the spec. A rule
set (languette/engine.py reads it) whose handler is code: deleting a remote branch that
an open pull request names as its base or its head is denied. The walk of the command is
the `branch-deletions` test; the open pull requests are a fact of GitHub's, read by the
`open-prs` handler (languette/branch_deletions.py), which gives the verdict, and asks
when it cannot tell."""

RULE_SET = {
    "guard": "guard-git-stacked-base",
    "rules": [{"id": "stacked-base", "match": [{"test": "branch-deletions"}], "action": "deny",
               "handler": "open-prs"}],
}
