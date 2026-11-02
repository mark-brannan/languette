"""guard-cross-session-send: features/guard-cross-session-send.feature is the spec. A rule
set (languette/engine.py reads it) whose handlers are code: a session that has read
untrusted content does not relay it to another of the user's sessions unseen. Its calls
carry no command, so every match entry is a test. On SendMessage, the `send-elsewhere`
test finds a target other than "main" and the `send-door` handler judges it by the
session's record and the permission mode. On the state events run.py wires the guard to,
the `session-record` test finds what the event records and the `session-keep` handler
writes it, never objecting. Both are in languette/untrusted_reads.py."""

RULE_SET = {
    "guard": "guard-cross-session-send",
    "calls": "any",
    "rules": [{"id": "send", "match": [{"test": "send-elsewhere"}], "action": "deny", "handler": "send-door"},
              {"id": "record", "match": [{"test": "session-record"}], "action": "deny", "handler": "session-keep"}],
}
