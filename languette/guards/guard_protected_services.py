"""guard-protected-services: features/guard-protected-services.feature is the spec.

Blocks a stop, restart, kill or `disable --now` of a service the user's
machine depends on, made with `systemctl`, the SysV `service`, `invoke-rc.d`,
`rc-service` or `/etc/init.d/<unit>`, `pkill` or `killall`: the
protected_services setting, comma-separated, a trailing `.service` optional,
`*` globs allowed. Unset or empty, it guards nothing: the user fills it. A
pattern matches the unit as written, without its type suffix, or without its
`@instance`. A glob in the unit fails closed, as does a pkill pattern (or a
`killall -r` one) that could select a listed unit's process, an inverted
(`pkill -v`) one, and an operand the scan cannot read. The services a session runs on (ssh, the network) are
guard-host-availability's. Its rules are command rules
(docs/design/guard-rules.md), each naming its program's description in scan,
matched by scan's command-rule matcher; the setting fills their units.
"""

import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, judged

NAME = "guard-protected-services"
OPTION = "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES"


def protected(env):
    """The protected_services patterns; empty when unset."""
    got = [re.sub(r"\.service\Z", "", p) for p in sw.listed(env.get(OPTION))]
    return tuple(got)


def rules(env):
    """The guard's rules, their units the protected_services setting's."""
    unit = {"units": list(protected(env))}
    return [{"id": "protected-stop", "action": "deny",
             "match": {"cmd": "systemctl", "program": "systemctl", "verbs": sw.CTL_STOPS, "unit": unit}},
            {"id": "protected-sysv-stop", "action": "deny",
             "match": {"cmd": list(sw.SYSV_CMDS), "program": "sysv", "verbs": sw.SERVICE_STOPS, "unit": unit}},
            {"id": "protected-kill", "action": "deny", "match": {"cmd": "pkill", "program": "pkill", "unit": unit}},
            {"id": "protected-killall", "action": "deny",
             "match": {"cmd": "killall", "program": "killall", "unit": unit}}]


def judge(doc):
    """The deny reason for the command, or None."""
    for rule in rules(doc.env):
        if rule["action"] != "deny":           # a verdict here is a deny; no other action is read yet
            continue
        verb = sw.match_rule(doc, rule["match"], prose=sw.PROSE)[2]
        if verb:
            return say("protected_stop", verb=verb, way_user=WAY_USER)
    return None


def check(doc):
    return judged(doc, NAME, judge)
