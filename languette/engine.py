"""The rules engine (docs/design/guard-rules.md): one engine, and a guard that
is a rule set alone. A rule set is data, held today as a Python dict in
languette/rules/, one module per guard, shaped as the file it will become:

    {"guard": "guard-sudo",
     "rules": [{"id": "root", "match": [{"cmd": "sudo", "at": "command"}],
                "action": "deny", "why": "sudo_root"}],
     "repo": ".languette/deny-always.json"}

`match` is a list of command-rule entries (scan's loader and matcher), any of
which selects the call. An entry may be a stop of a unit: `program` names the
program's description in scan, `verbs` a table of its stop verbs (VERBS), and
`unit` is "listed": the units are the set's `units`, a plugin option holding a
comma-separated list, with the `drop` suffix each unit loses, or fixed `names`;
unset, the entry matches nothing. `host_verbs` names a table of systemctl verbs
that take the host down, which need no unit. An entry may instead be `{"test": name}`, one of the named tests in
languette/primitives.py, whose answer fills the message. `action` is "deny", the one action this
engine reads yet. `why` names the message that explains it, filled with the
command word it matched (`cmd`), the stop it found (`verb`) and `way_user`.
`read`, optional, says how scan reads the call's words, for every entry:
`process_prose` false makes pkill, ps and kin commands, and `launchers` false
stops the look through npx and kin. `file`, optional, names a rule file
shipped beside the rule sets, read when present; its rules add denies, as
`repo`'s do. `repo`, optional, names the file a project keeps, found as
ask-first finds its list, whose rules add denies: the repo tier, which says
nothing else, and whose `why` is the repo's own words. Its rules take an
optional `action`, which must be "deny". `opt_in`, optional, names the plugin
option that must be "true" for the guard to run, as an opt-in guard module's
OPT_IN does.

A rule set that does not load, shipped or the repo's, denies every Bash
command, naming the file and the fault. Guard(module) is a guard as run.py
drives one: a NAME and check(doc).
"""

import os

from languette import paths, primitives
from languette import scan as sw
from languette.messages import MESSAGES, say
from languette.verdict import WAY_USER, Need, Refuse, judged

_SET_KEYS = frozenset({"guard", "rules", "repo", "opt_in", "file", "read", "units"})
_READ_KEYS = frozenset({"process_prose", "launchers"})
# The tables an entry's `verbs` names; the last is the SysV stops of a service the session runs on,
# a smaller table than sysv-stops, as the host's guard has always read it.
VERBS = {"systemctl-stops": sw.CTL_STOPS, "sysv-stops": sw.SERVICE_STOPS,
         "sysv-core-stops": {v: [] for v in ("stop", "restart", "force-reload", "try-restart", "--full-restart")}}
HOST_VERBS = {"systemctl-host": sw.CTL_HOST}     # the tables an entry's `host_verbs` names: they take the host down


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


def _file(r, where):
    if r.get("action") != "deny":
        raise sw.BadRules(f'{where}.action must be "deny"')
    if "why" in r and (not isinstance(r["why"], str) or not r["why"].strip()):
        raise sw.BadRules(f"{where}.why must be a non-empty string")


def _unit(e, where, units):
    """A unit entry names its program and its verb table, and the set lists the units. A test
    entry names a test primitives holds."""
    if "test" in e:
        if e["test"] not in primitives.TESTS:
            raise sw.BadRules(f"{where}.test must name a test languette holds")
        return
    if "unit" not in e:
        if {"program", "verbs", "host_verbs"} & set(e):
            raise sw.BadRules(f"{where}: program, verbs and host_verbs belong to an entry with a unit")
        return
    if e.get("host_verbs", next(iter(HOST_VERBS))) not in HOST_VERBS:
        raise sw.BadRules(f"{where}.host_verbs must name a verb table languette holds")
    if e.get("program") not in sw.PROGRAMS or e.get("verbs", next(iter(VERBS))) not in VERBS:
        raise sw.BadRules(f"{where}.program and .verbs must name a program and a verb table languette holds")
    if e["unit"] != "listed" or not units:
        raise sw.BadRules(f'{where}.unit must be "listed", and the set must say its units')


def load(rule_set):
    """The rule set's rules, checked, or BadRules naming the fault."""
    if not isinstance(rule_set, dict) or set(rule_set) - _SET_KEYS or not {"guard", "rules"} <= set(rule_set):
        raise sw.BadRules("the rule set must be an object holding guard and rules, and optionally repo and opt_in")
    if not isinstance(rule_set["guard"], str) or not rule_set["guard"]:
        raise sw.BadRules("guard must be a guard's name")
    if "repo" in rule_set and (not isinstance(rule_set["repo"], str) or not rule_set["repo"].startswith(".languette/")):
        raise sw.BadRules("repo must be a path under .languette/")
    if "file" in rule_set and (not isinstance(rule_set["file"], str) or "/" in rule_set["file"]):
        raise sw.BadRules("file must be the name of a file beside the rule sets")
    read = rule_set.get("read", {})
    if not isinstance(read, dict) or set(read) - _READ_KEYS or not all(isinstance(v, bool) for v in read.values()):
        raise sw.BadRules("read must be an object holding only process_prose and launchers, each true or false")
    units = rule_set.get("units")
    if "units" in rule_set and (not isinstance(units, dict) or set(units) - {"setting", "drop", "names"}
                                or ("names" in units) == ("setting" in units)
                                or not isinstance(units.get("setting", ""), str)
                                or not isinstance(units.get("names", []), list)):
        raise sw.BadRules("units must be an object holding setting (and optionally drop) or names, a list")
    rules = sw.load_rules({"rules": rule_set["rules"]}, "rules", ("action", "why"), _shipped, many=True,
                          match_keys=sw.SHIPPED_MATCH_KEYS)
    for n, r in enumerate(rules):
        for i, e in enumerate(r["match"]):
            _unit(e, f"rules[{n}].match[{i}]", units)
    return rules


def _resolved(e, env, units):
    """The entry with its unit filled from the set's setting, and its verb table."""
    if "unit" not in e:
        return e
    drop = units.get("drop", "")
    listed = units.get("names") or [x[:-len(drop)] if drop and x.endswith(drop) else x
                                    for x in sw.listed(env.get(units["setting"]))]
    return {**e, "unit": {"units": listed}, "verbs": VERBS.get(e.get("verbs"), {}),
            "host_verbs": HOST_VERBS.get(e.get("host_verbs"), ())}


def _hit(doc, rule, read, units):
    """(the command word of the first of the rule's match entries the call runs, the stop it
    found or None, the fields a test gave for the message), or None. A test entry has no
    command word. A file's rule has one entry, not a list."""
    for e in rule["match"] if isinstance(rule["match"], list) else [rule["match"]]:
        if "test" in e:
            fields = primitives.TESTS[e["test"]](doc)
            if fields is not None:
                return e["test"], None, fields
            continue
        n, _, said = sw.match_rule(doc, _resolved(e, doc.env, units), **read)
        if n:
            return (e["cmd"] if isinstance(e["cmd"], str) else e["cmd"][0]), said, {}
    return None


def _denial(rule, cmd, file):
    return say("rule_deny", cmd=cmd, id=rule["id"], file=file, way_user=WAY_USER,
               why=(rule.get("why") or "the rule file lists it").rstrip("."))


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
        if "file" in self.RULE_SET:
            self.RULE_FILE = os.path.join(os.path.dirname(module.__file__), self.RULE_SET["file"])
        read = self.RULE_SET.get("read", {})
        self._read = {**({} if read.get("process_prose", True) else {"prose": sw.PROSE}),
                      **({} if read.get("launchers", True) else {"launchers": False})}

        def check(doc):
            return judged(doc, self.NAME, self._judge)
        self.check = check

    def _judge(self, doc):
        try:
            rules = load(self.RULE_SET)
        except sw.BadRules as e:
            return say("rules_bad", file=self.FILE, err=e)
        shipped = []
        if "file" in self.RULE_SET:
            try:
                shipped = yield from self.file_rules({r["id"] for r in rules})
            except Refuse as e:
                return say("rules_bad", file=self.RULE_FILE, err=e)
        for rule in rules:
            hit = _hit(doc, rule, self._read, self.RULE_SET.get("units"))
            if hit:
                have = {"cmd": hit[0], "verb": hit[1], "way_user": WAY_USER, **hit[2]}
                return say(rule["why"], **{k: v for k, v in have.items() if "{" + k + "}" in MESSAGES[rule["why"]]})
        for rule in shipped:
            hit = _hit(doc, rule, self._read, self.RULE_SET.get("units"))
            if hit:
                return _denial(rule, hit[0], self.RULE_FILE)
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
            hit = _hit(doc, rule, self._read, self.RULE_SET.get("units"))
            if hit:
                return _denial(rule, hit[0], path)
        return None

    def file_rules(self, taken):
        """The rules of the shipped rule file: none when it is absent, Refuse when it is present
        and does not load. Its rules have one match entry, held as an object."""
        if not (yield Need("path", "lexists", self.RULE_FILE)):
            return []
        return (yield from paths.read_rules(self.RULE_FILE, "rules", ("action", "why"), _file, taken=taken))
