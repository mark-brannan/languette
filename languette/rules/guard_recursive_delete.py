"""guard-recursive-delete: features/guard-recursive-delete.feature is the spec. A rule
set alone (languette/engine.py reads it): a recursive `rm` and `find ... -delete` are
denied unless every target, resolved against the payload's cwd and then through the
filesystem, is the agent's to remove: under the scratchpad, an agent worktree or /tmp,
or a generated directory (GENERATED_NAMES in languette/primitives.py) that is not a
direct child of $HOME or of /. A target this guard cannot resolve to one allowed path is
denied on sight, with a reason naming what it saw. The walk of the command and the
judging of its targets are the `recursive-delete` test; it gives the verdict itself."""

RULE_SET = {
    "guard": "guard-recursive-delete",
    "rules": [{"id": "recursive-delete", "match": [{"test": "recursive-delete"}], "action": "deny"}],
}
