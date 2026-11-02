"""guard-bypass-labels: features/guard-bypass-labels.feature is the spec. A rule set alone
(languette/engine.py reads it): a label named in the bypass_labels option is a human's to
apply. A label that waives a CI gate is the user's to apply unless the option names it, so
a session may not apply a named label, in any repo. The option is the label list, empty by
default: with no label named the guard allows every call. The labels a call applies are
read from gh's flags, gh api and an MCP tool's fields (languette/labels.py); the walk and
the verdict are the `bypass-labels` test, which gives the verdict itself. `calls` says it
judges a call with no command too, an MCP tool's."""

RULE_SET = {
    "guard": "guard-bypass-labels",
    "calls": "any",
    "rules": [{"id": "bypass-labels", "match": [{"test": "bypass-labels"}], "action": "deny"}],
}
