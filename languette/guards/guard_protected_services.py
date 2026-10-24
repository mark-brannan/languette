"""guard-protected-services: features/guard-protected-services.feature is the spec.

Blocks a `systemctl` stop, restart, kill or `disable --now` of a service the
user's machine depends on: the protected_services setting, comma-separated,
a trailing `.service` optional, `*` globs allowed. Unset or empty, it guards
nothing: the user fills it. A pattern matches the unit as written, without its
type suffix, or without its `@instance`. A glob in the unit fails closed. The
services a session runs on (ssh, the network) are guard-host-availability's.
Its rules are command rules (docs/design/guard-rules.md) on systemctl, service,
pkill and killall, matched by scan's ctl_hit; the setting fills their units.
"""

import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, judged

NAME = "guard-protected-services"
OPTION = "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES"


def protected(env):
    """The protected_services patterns; empty when unset."""
    got = [re.sub(r"\.service\Z", "", p.strip()) for p in (env.get(OPTION) or "").split(",") if p.strip()]
    return tuple(got)


def rules(env):
    """The guard's one rule, its units the protected_services setting's."""
    unit = {"units": list(protected(env))}
    return [{"id": "protected-stop", "action": "deny",
             "match": {"cmd": "systemctl", "verbs": sw.CTL_STOPS, "unit": unit}},
            {"id": "protected-service-stop", "action": "deny",
             "match": {"cmd": "service", "verbs": {"stop": [], "restart": []}, "unit": unit}},
            {"id": "protected-kill", "action": "deny", "match": {"cmd": "pkill", "unit": unit}},
            {"id": "protected-killall", "action": "deny", "match": {"cmd": "killall", "unit": unit}}]


def judge(doc):
    """The deny reason for the command, or None."""
    for rule in rules(doc.env):
        if rule["action"] != "deny":           # a verdict here is a deny; no other action is read yet
            continue
        verb = sw.ctl_hit(doc, rule["match"])
        if verb:
            return say("protected_stop", verb=f"{rule['match']['cmd']} {verb}", way_user=WAY_USER)
    return None


def check(doc):
    return judged(doc, NAME, judge)
