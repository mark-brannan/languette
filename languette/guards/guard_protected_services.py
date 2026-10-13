"""guard-protected-services: features/guard-protected-services.feature is the spec.

Blocks a `systemctl` stop, restart, kill or `disable --now` of a service the
user's machine depends on: the protected_services setting, comma-separated,
a trailing `.service` optional, `*` globs allowed. Unset or empty, it guards
nothing: the user fills it. A pattern matches the unit as written, without its
type suffix, or without its `@instance`. A glob in the unit fails closed. The
services a session runs on (ssh, the network) are guard-host-availability's.
"""

import fnmatch
import re

from languette.guards.guard_host_availability import service_stop, unit_names
from languette.verdict import WAY_USER, bash_command, deny

NAME = "guard-protected-services"
OPTION = "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES"


def protected(env):
    """The protected_services patterns; empty when unset."""
    got = [re.sub(r"\.service\Z", "", p.strip()) for p in (env.get(OPTION) or "").split(",") if p.strip()]
    return tuple(got)


def judge(doc):
    """The deny reason for the command, or None."""
    pats = protected(doc.env)
    if not pats:
        return None

    def hit(u):
        return any(c in u for c in "*?[") or any(fnmatch.fnmatchcase(n, p) for n in unit_names(u) for p in pats)

    for t, _ in doc.texts():
        s = doc.scan(t)
        for a, b in s.segments():
            verb = a <= b and service_stop(s, a, b, hit, host_verbs=())
            if verb:
                return (f"`systemctl {verb}` is blocked: it stops a protected service, one the user's machine "
                        f"depends on (the protected_services setting). {WAY_USER}")
    return None


def check(doc):
    if bash_command(doc) is None:
        return None
    why = judge(doc)
    return deny(f"{NAME}: {why}") if why else None
