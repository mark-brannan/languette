"""The rules engine (docs/design/guard-rules.md): one engine, and a guard that
is a rule set alone. A rule set is data, held today as a Python dict in
languette/rules/, one module per guard, shaped as the file it will become:

    {"guard": "guard-sudo",
     "rules": [{"id": "root", "match": [{"cmd": "sudo", "at": "command"}],
                "action": "deny", "why": "sudo_root"}],
     "repo": ".languette/deny-always.json"}

`match` is a list of command-rule entries (scan's loader and matcher), any of
which selects the call. `action` is "deny", the one action this engine reads
yet. `why` names the message that explains it, filled with the command word
it matched (`cmd`) and `way_user`. `repo`, optional, names the file a
project keeps, found as ask-first finds its list, whose rules add denies:
the repo tier, which says nothing else, and whose `why` is the repo's own
words. Its rules take an optional `action`, which must be "deny". `opt_in`,
optional, names the plugin option that must be "true" for the guard to run,
as an opt-in guard module's OPT_IN does.

A rule set that does not load, shipped or the repo's, denies every Bash
command, naming the file and the fault. Guard(module) is a guard as run.py
drives one: a NAME and check(doc).
"""

from languette import paths
from languette import scan as sw
from languette.messages import MESSAGES, say
from languette.verdict import WAY_USER, Refuse, judged

_SET_KEYS = frozenset({"guard", "rules", "repo", "opt_in"})


def _shipped(r, where):
    if r.get("action") != "deny":
        raise sw.BadRules(f'{where}.action must be "deny"')
    if r.get("why") not in MESSAGES:
        raise sw.BadRules(f"{where}.why must name a message in languette/messages.py")


def _repo(r, where):
    if r.get("action", "deny") != "deny":
        raise sw.BadRules(f'{where}.action must be "deny": a repo\'s list only adds denies')
    if not isinstance(r.get("why"), str) or not r["why"].strip():
        raise sw.BadRules(f"{where}.why must be a non-empty string")


def load(rule_set):
    """The rule set's rules, checked, or BadRules naming the fault."""
    if not isinstance(rule_set, dict) or set(rule_set) - _SET_KEYS or not {"guard", "rules"} <= set(rule_set):
        raise sw.BadRules("the rule set must be an object holding guard and rules, and optionally repo and opt_in")
    if not isinstance(rule_set["guard"], str) or not rule_set["guard"]:
        raise sw.BadRules("guard must be a guard's name")
    if "repo" in rule_set and (not isinstance(rule_set["repo"], str) or not rule_set["repo"].startswith(".languette/")):
        raise sw.BadRules("repo must be a path under .languette/")
    return sw.load_rules({"rules": rule_set["rules"]}, "rules", ("action", "why"), _shipped, many=True,
                         match_keys=sw.ENGINE_MATCH_KEYS)


def _hit(doc, rule):
    """The command word of the first of the rule's match entries the call runs, or None."""
    return next((e["cmd"] for e in rule["match"] if sw.match_rule(doc, e)[0]), None)


class Guard:
    """The guard a rule set module's RULE_SET is. Its judging code is this
    module's, so __file__ names it, and check(doc) takes the call alone, as a
    guard module's does."""

    def __init__(self, module):
        self.RULE_SET = module.RULE_SET
        self.NAME = self.RULE_SET["guard"]
        self.FILE = "languette/" + module.__name__.split(".", 1)[1].replace(".", "/") + ".py"
        self.__file__ = __file__
        if "opt_in" in self.RULE_SET:
            self.OPT_IN = self.RULE_SET["opt_in"]

        def check(doc):
            return judged(doc, self.NAME, self._judge)
        self.check = check

    def _judge(self, doc):
        try:
            rules = load(self.RULE_SET)
        except sw.BadRules as e:
            return say("rules_bad", file=self.FILE, err=e)
        for rule in rules:
            cmd = _hit(doc, rule)
            if cmd:
                return say(rule["why"], cmd=cmd, way_user=WAY_USER)
        if "repo" not in self.RULE_SET:
            return None
        path, usable = yield from paths.project_config(doc.payload, doc.env, self.RULE_SET["repo"])
        if path is None:
            return None if usable else say("rules_cannot_look", cwd=doc.payload.get("cwd") or "(none)")
        try:
            found = yield from paths.read_rules(path, "rules", ("action", "why"), _repo, many=True,
                                                taken={r["id"] for r in rules}, match_keys=sw.ENGINE_MATCH_KEYS)
        except Refuse as e:
            return say("rules_bad", file=path, err=e)
        for rule in found:
            cmd = _hit(doc, rule)
            if cmd:
                return say("rule_deny", cmd=cmd, id=rule["id"], file=path, why=rule["why"].rstrip("."),
                           way_user=WAY_USER)
        return None
