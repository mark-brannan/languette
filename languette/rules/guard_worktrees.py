"""guard-worktrees: features/guard-worktrees.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a checkout or switch that would move
$HOME's branch is denied and a dotfile manager's forced apply or teardown is asked about
(checkout-home); a reach into another session's linked worktree, by a Bash word, a file
tool's path or EnterWorktree(path=...), is denied (foreign). Its calls include the file
tools', which carry no command, so its one match entry is a test. The `worktree-reaches`
test reads each control's moves and words from the call alone, with each control's own
switch; where they land, through the command's cd and -C targets, is a fact of git's and
of the session's record, read by the `own-places` handler (languette/worktree_reaches.py),
which gives the verdict."""

RULE_SET = {
    "guard": "guard-worktrees",
    # Off unless the user turns it on.
    "opt_in": "CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES",
    "calls": "any",
    "rules": [{"id": "reach", "match": [{"test": "worktree-reaches"}], "action": "deny",
               "handler": "own-places"}],
}
