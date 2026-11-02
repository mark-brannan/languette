"""guard-host-availability: features/guard-host-availability.feature is the spec.
A rule set alone (languette/engine.py reads it): the commands that take the
machine down are denied: shutdown, reboot, halt and poweroff, at command position
or as the one-word script of `sh -c`, the fork-bomb shape, and a `systemctl` verb
(or the SysV `service`, `invoke-rc.d`, `rc-service` and `/etc/init.d/<unit>` stop
and restart) that takes the host down or stops a service the user's session runs
on (ssh, login, dbus, the network, the display manager). The user's own `--user`
manager and a remote `-H`/`-M` host are not the host. Any other service is the
agent's to stop, unless the user lists it in guard-protected-services."""

RULE_SET = {
    "guard": "guard-host-availability",
    # The services a session runs on: stopping one cuts the user off the machine. A glob in a
    # unit fails closed.
    "units": {"names": ["ssh", "sshd", "systemd-logind", "dbus", "dbus-broker", "NetworkManager", "systemd-networkd",
                        "networking", "display-manager", "gdm", "gdm3", "sddm", "lightdm", "getty", "user",
                        "session-*", "multi-user", "graphical", "default", "network", "network-online", "basic",
                        "sysinit"]},
    "read": {"process_prose": False},
    "rules": [
        {"id": "power", "match": [{"test": "power-word"}], "action": "deny", "why": "host_power"},
        {"id": "host-ctl", "action": "deny", "why": "host_ctl",
         "match": [{"cmd": "systemctl", "program": "systemctl", "verbs": "systemctl-stops", "host_verbs": "systemctl-host",
                    "unit": "listed"}]},
        {"id": "host-sysv", "action": "deny", "why": "host_sysv",
         "match": [{"cmd": ["service", "invoke-rc.d", "rc-service"], "program": "sysv", "verbs": "sysv-core-stops",
                    "unit": "listed"}]},
        {"id": "fork-bomb", "match": [{"test": "fork-bomb"}], "action": "deny", "why": "host_fork_bomb"},
    ],
}
