"""guard-github-issues: features/guard-github-issues.feature is the spec. A rule set
(languette/engine.py reads it) whose handlers are code: one GitHub or GitLab issue create,
transfer or delete per human turn, never two in one call, never one in a loop. The
`issue-writes` test finds the identifier writes a call makes, in a command or an MCP tool's
input, so every match entry is a test; the `issue-door` handler judges them by the turn's
door. `on` names the handlers of the door's other events: the human's turn opens it
(`door-open`), and a write that ran spends it (`door-spend`). All are in
languette/issue_writes.py."""

RULE_SET = {
    "guard": "guard-github-issues",
    "calls": "any",
    "rules": [{"id": "issue-write", "match": [{"test": "issue-writes"}], "action": "deny", "handler": "issue-door"}],
    "on": {"UserPromptSubmit": "door-open", "PostToolUse": "door-spend", "PostToolUseFailure": "door-spend"},
}
