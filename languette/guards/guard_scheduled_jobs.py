"""guard-scheduled-jobs: features/guard-scheduled-jobs.feature is the spec.

Blocks `crontab -r`, which deletes the whole crontab with no undo: at command
position, behind a wrapper, and with r in a short-option cluster (`-ir`).
Its one rule is a command rule (docs/design/guard-rules.md), loaded and matched by
scan's command-rule loader and matcher.

A proof of concept for configurable rules (#226): RULES is the default, and the
rule file languette ships beside it, when present, adds rules of the same
shape. A rule only tightens, so the file never removes a default; a file that
does not load denies every command, naming the file and the fault.
"""

import os

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, Need, Refuse, deny

NAME = "guard-scheduled-jobs"

RULES = [{"id": "crontab-wipe", "match": {"cmd": "crontab", "flags": ["r"]}, "action": "deny"}]

RULE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules", NAME + ".json")


def _own(r, where):
    if r.get("action") != "deny":
        raise sw.BadRules(f'{where}.action must be "deny"')
    if "why" in r and (not isinstance(r["why"], str) or not r["why"].strip()):
        raise sw.BadRules(f"{where}.why must be a non-empty string")


def _load(path):
    """The file's rules, or Refuse naming the fault."""
    cfg = yield from paths.read_json(path)
    try:
        return sw.load_rules(cfg, "rules", ("action", "why"), _own, taken={r["id"] for r in RULES})
    except sw.BadRules as e:
        raise Refuse(str(e))


def rules(path):
    """RULES, then the rule file's, gathered: the defaults alone when the file is
    absent, Refuse when it is present and does not load."""
    if not (yield Need("path", "lexists", path)):
        return list(RULES)
    return list(RULES) + (yield from _load(path))


def check(doc):
    if doc.text is None:
        return None
    try:
        found = yield from rules(RULE_FILE)
    except Refuse as e:
        return deny(say("judged", guard=NAME, why=say("rules_bad", file=RULE_FILE, err=e)))
    for rule in found:
        # PROSE, not PROSE_PROCESS, and no launchers: `pkill crontab -r` is denied
        # and `sh -c "npx crontab -r"` passes, as before the shared matcher.
        n = sw.match_rule(doc, rule["match"], prose=sw.PROSE, launchers=False)[0]
        if not n:
            continue
        if rule in RULES:
            why = say("cron_remove", way_user=WAY_USER)
        else:
            why = say("rule_deny", cmd=rule["match"]["cmd"], id=rule["id"], file=RULE_FILE,
                      why=(rule.get("why") or "the rule file lists it").rstrip("."), way_user=WAY_USER)
        return deny(say("judged", guard=NAME, why=why))
    return None
