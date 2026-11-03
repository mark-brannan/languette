"""guard-cross-session-send: features/guard-cross-session-send.feature is the spec. A rule
set (languette/engine.py reads it) whose handlers are code: a session that has read
untrusted content does not relay it to another of the user's sessions unseen. Its calls
carry no command, so every match entry is a test. On SendMessage, the `send-elsewhere`
test finds a target other than "main" and the `send-door` handler judges it by the
session's record and the permission mode. `on` names the handler of the state events:
`session-keep` writes what each records, never objecting. Both are in
languette/untrusted_reads.py."""

RULE_SET = {
    "guard": "guard-cross-session-send",
    "calls": "any",
    "rules": [{"id": "send", "match": [{"test": "send-elsewhere"}], "action": "deny", "handler": "send-door"}],
    "on": {"PostToolUse": "session-keep", "PostToolUseFailure": "session-keep",
           "SubagentStart": "session-keep", "SessionStart": "session-keep"},
}
