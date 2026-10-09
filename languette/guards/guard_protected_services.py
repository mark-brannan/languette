"""guard-protected-services: features/guard-protected-services.feature is the spec.

Blocks a `systemctl` stop, restart, kill or `disable --now` of a service the
user's machine depends on: the protected_services setting, comma-separated,
a trailing `.service` optional, `*` globs allowed. Unset or empty, it is
DEFAULT, the services a session reaches the machine through. A pattern
matches the unit as written, without its type suffix, or without its
`@instance`. A glob in the unit fails closed. The units the host itself cannot
run without are guard-host-availability's.
"""

import fnmatch
import json
import os
import re

from languette import scan as sw
from languette.guards.guard_host_availability import service_stop, unit_names
from languette.verdict import deny

NAME = "guard-protected-services"
OPTION = "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES"
DEFAULT = ("ssh", "sshd", "NetworkManager", "systemd-networkd", "network", "network-online",
           "display-manager", "gdm", "gdm3", "sddm", "lightdm", "getty")
_WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


def protected(env):
    """The protected_services patterns, or DEFAULT when unset or empty."""
    got = [re.sub(r"\.service\Z", "", p.strip()) for p in (env.get(OPTION) or "").split(",") if p.strip()]
    return tuple(got) or DEFAULT


def judge(text, env=os.environ):
    """The deny reason for `text`, or None."""
    pats = protected(env)

    def hit(u):
        return any(c in u for c in "*?[") or any(fnmatch.fnmatchcase(n, p) for n in unit_names(u) for p in pats)

    for t, _ in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        for a, b in s.segments():
            verb = a <= b and service_stop(s, a, b, hit, host_verbs=())
            if verb:
                return (f"`systemctl {verb}` is blocked: it stops a protected service, one the user's machine "
                        f"depends on (the protected_services setting). {_WAY_USER}")
    return None


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    why = judge(cmd + "\n", env)
    return deny(f"{NAME}: {why}") if why else None
