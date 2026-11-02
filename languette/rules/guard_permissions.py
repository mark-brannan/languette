"""guard-permissions: features/guard-permissions.feature is the spec. A rule set alone
(languette/engine.py reads it): a recursive chown, chgrp or chmod (-R, --recursive, a
short cluster holding R), `chmod 777`, and `find ... -exec chown|chgrp|chmod` are denied
unless every target, resolved against the payload's cwd and then through the filesystem,
is the agent's own: under the scratchpad, an agent worktree or /tmp, or an absolute path
named in LANGUETTE_PERM_ALLOW. Never `/`, $HOME itself, or anything inside a .git. A target
this guard cannot resolve to one allowed path is denied on sight, with a reason naming what
it saw. The walk of the command and the judging of its targets are the `permissions` test;
it gives the verdict itself."""

RULE_SET = {
    "guard": "guard-permissions",
    "rules": [{"id": "permissions", "match": [{"test": "permissions"}], "action": "deny"}],
}
