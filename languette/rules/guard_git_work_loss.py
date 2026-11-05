"""guard-git-work-loss: features/guard-git-work-loss.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: the git moves that throw work away
(blanket staging, stash pop, drop and clear, a force push, a discard of the tree, branch
-D) are denied; `stow --adopt`, and a push with a lease to a default branch, are asked
about. The walk of the command is the
`work-losses` test, which reads each rule's own switch; whether the tree has anything to
lose, whether it is where an agent works and which branches are the default are facts of
git's, read by the `tree-state` handler (languette/work_losses.py), which gives the
verdict."""

RULE_SET = {
    "guard": "guard-git-work-loss",
    "rules": [{"id": "work-loss", "match": [{"test": "work-losses"}], "action": "deny",
               "handler": "tree-state"}],
}
