"""deny-always: features/deny-always.feature is the spec. A rule set alone
(languette/engine.py reads it): it ships no rule, and denies each command
the user's list or the repo's names, every time."""

RULE_SET = {
    "guard": "deny-always",
    "rules": [],
    "repo": ".languette/deny-always.json",
    "user": "deny-always.json",
}
