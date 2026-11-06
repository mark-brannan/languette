"""guard-bypass-ruleset: features/guard-bypass-ruleset.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a push that lands on the remote's
default branch, where GitHub says that branch requires a pull request (on GitLab, a
protected branch no role may push to), and `gh pr merge --admin` are denied. The walk of
the command is the `ruleset-pushes` test; where a push lands and the forge's rules for
that branch are facts of git's and the forge's, read by the
`branch-rules` handler (languette/pushes.py), which keeps a "requires a pull request"
answer in a cache, gives the verdict, and asks when it cannot tell."""

RULE_SET = {
    "guard": "guard-bypass-ruleset",
    "rules": [{"id": "default-branch", "match": [{"test": "ruleset-pushes"}], "action": "deny",
               "handler": "branch-rules"}],
}
