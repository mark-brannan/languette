"""guard-scheduled-jobs: features/guard-scheduled-jobs.feature is the spec.

Blocks `crontab -r`, which deletes the whole crontab with no undo: at command
position, behind a wrapper, and with r in a short-option cluster (`-ir`).
Its one rule is a command rule (docs/design/guard-rules.md), matched by scan's
command-rule matcher.

A proof of concept for configurable rules (#226): RULES is the default, and the
rule file languette ships beside it, when present, adds rules of the same
shape. A rule only tightens, so the file never removes a default; a file that
does not load denies every command, naming the file and the fault.
"""

import os
import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import WAY_USER, Need, Refuse, deny

NAME = "guard-scheduled-jobs"

RULES = [{"id": "crontab-wipe", "match": {"cmd": "crontab", "flags": ["r"]}, "action": "deny"}]

RULE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules", NAME + ".json")

_RULE_KEYS = {"id", "match", "action", "why"}
_MATCH_KEYS = {"cmd", "args", "script", "flags"}


def _strs(v, what, each=r".+", say_each="non-empty strings"):
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and re.fullmatch(each, x) for x in v):
        raise Refuse(f"{what} must be a non-empty list of {say_each}")


def _load(path):
    """The file's rules, or Refuse naming the fault."""
    cfg = yield from paths.read_json(path)
    if not isinstance(cfg, dict) or set(cfg) != {"rules"} or not isinstance(cfg["rules"], list):
        raise Refuse('the top level must be {"rules": [...]}')
    seen = {r["id"] for r in RULES}
    for n, r in enumerate(cfg["rules"]):
        where = f"rules[{n}]"
        if not isinstance(r, dict):
            raise Refuse(f"{where} is not an object")
        if set(r) - _RULE_KEYS:
            raise Refuse(f"{where} has keys a rule does not: {', '.join(sorted(set(r) - _RULE_KEYS))}")
        if not isinstance(r.get("id"), str) or not r["id"].strip():
            raise Refuse(f"{where}.id must be a non-empty string")
        if r["id"] in seen:
            raise Refuse(f"{where}.id '{r['id']}' is a duplicate or a default's; a file adds rules, "
                         "it never replaces one")
        seen.add(r["id"])
        if r.get("action") != "deny":
            raise Refuse(f'{where}.action must be "deny"')
        if "why" in r and (not isinstance(r["why"], str) or not r["why"].strip()):
            raise Refuse(f"{where}.why must be a non-empty string")
        m, w = r.get("match"), f"{where}.match"
        if not isinstance(m, dict) or set(m) - _MATCH_KEYS:
            raise Refuse(f"{w} must be an object holding only {', '.join(sorted(_MATCH_KEYS))}")
        if not isinstance(m.get("cmd"), str) or not re.fullmatch(r"[A-Za-z0-9._+-]+", m["cmd"]):
            raise Refuse(f"{w}.cmd must be a bare command name")
        if not {"args", "script", "flags"} & set(m):
            raise Refuse(f"{w} needs args, script or flags, or it would match every {m['cmd']}")
        if "args" in m:
            _strs(m["args"], f"{w}.args")
        if "flags" in m:
            _strs(m["flags"], f"{w}.flags", r"[A-Za-z]", "single option letters")
        if "script" in m and (not isinstance(m["script"], str) or not m["script"].strip("./")):
            raise Refuse(f"{w}.script must be a non-empty path")
    return cfg["rules"]


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
        n, _ = sw.matches(doc, rule["match"], prose=sw.PROSE, launchers=False)
        if not n:
            continue
        if rule in RULES:
            why = say("cron_remove", way_user=WAY_USER)
        else:
            why = say("rule_deny", cmd=rule["match"]["cmd"], id=rule["id"], file=RULE_FILE,
                      why=rule.get("why") or "the rule file lists it", way_user=WAY_USER)
        return deny(say("judged", guard=NAME, why=why))
    return None
