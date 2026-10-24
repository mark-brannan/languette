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

from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, judged

NAME = "guard-protected-services"
OPTION = "CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES"


def protected(env):
    """The protected_services patterns; empty when unset."""
    got = [re.sub(r"\.service\Z", "", p) for p in sw.listed(env.get(OPTION))]
    return tuple(got)


def judge(doc):
    """The deny reason for the command, or None."""
    pats = protected(doc.env)
    if not pats:
        return None

    def hit(u):
        return any(c in u for c in "*?[") or any(fnmatch.fnmatchcase(n, p) for n in sw.unit_names(u) for p in pats)

    for t, _ in doc.texts():
        s = doc.scan(t)
        for a, b in s.segments():
            verb = a <= b and sw.service_stop(s, a, b, hit, host_verbs=())
            if verb:
                return say("protected_stop", verb=verb, way_user=WAY_USER)
    return None


def check(doc):
    return judged(doc, NAME, judge)
