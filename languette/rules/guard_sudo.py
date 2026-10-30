"""guard-sudo: features/guard-sudo.feature is the spec. A rule set alone
(languette/engine.py reads it): acting as root is denied wherever it runs."""

RULE_SET = {
    "guard": "guard-sudo",
    # Off unless the user turns it on: on by default it would deny the sudo calls agents make today.
    "opt_in": "CLAUDE_PLUGIN_OPTION_GUARD_SUDO",
    "rules": [{"id": "root",
               "match": [{"cmd": "sudo", "at": "command"}, {"cmd": "su", "at": "command"},
                         {"cmd": "doas", "at": "command"}, {"cmd": "pkexec", "at": "command"}],
               "action": "deny",
               "why": "sudo_root"}],
}
