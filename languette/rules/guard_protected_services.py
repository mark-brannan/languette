"""guard-protected-services: features/guard-protected-services.feature is the spec.
A rule set alone (languette/engine.py reads it): a stop, restart, kill or
`disable --now` of a service the user's machine depends on, made with
`systemctl`, the SysV `service`, `invoke-rc.d`, `rc-service` or
`/etc/init.d/<unit>`, `pkill` or `killall`, is denied. The units are the
protected_services setting, comma-separated, a trailing `.service` optional,
`*` globs allowed; unset or empty, the guard denies nothing. A pattern matches
the unit as written, without its type suffix, or without its `@instance`. A glob
in the unit fails closed, as does a pkill pattern (or a `killall -r` one) that
could select a listed unit's process, an inverted (`pkill -v`) one, and an
operand the scan cannot read. The services a session runs on (ssh, the network)
are guard-host-availability's."""

RULE_SET = {
    "guard": "guard-protected-services",
    "read": {"process_prose": False},          # pkill and killall are commands here
    "units": {"setting": "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES", "drop": ".service"},
    "rules": [
        {"id": "protected-stop", "action": "deny", "why": "protected_stop",
         "match": [{"cmd": "systemctl", "program": "systemctl", "verbs": "systemctl-stops", "unit": "listed"}]},
        {"id": "protected-sysv-stop", "action": "deny", "why": "protected_stop",
         "match": [{"cmd": ["service", "invoke-rc.d", "rc-service"], "program": "sysv", "verbs": "sysv-stops", "unit": "listed"}]},
        {"id": "protected-kill", "action": "deny", "why": "protected_stop",
         "match": [{"cmd": "pkill", "program": "pkill", "unit": "listed"}]},
        {"id": "protected-killall", "action": "deny", "why": "protected_stop",
         "match": [{"cmd": "killall", "program": "killall", "unit": "listed"}]},
    ],
}
