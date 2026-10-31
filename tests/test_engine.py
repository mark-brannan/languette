"""The rules engine (languette/engine.py) fails closed: a rule set that does not
load raises BadRules naming the fault, and the guard it would be denies every
Bash command with rules_bad. Features cover the rule sets that load."""

import re
import types

import pytest
from hamcrest import assert_that, contains_string, equal_to

from languette import engine, scan
from languette.document import Document

GOOD = {"guard": "guard-x", "rules": [{"id": "r", "match": [{"cmd": "foo"}], "action": "deny", "why": "sudo_root"}]}


def _with_rule(**changes):
    return {**GOOD, "rules": [{**GOOD["rules"][0], **changes}]}


@pytest.mark.parametrize("rule_set, fault", [
    ([], "must be an object"),
    ({"guard": "guard-x"}, "must be an object"),
    ({**GOOD, "extra": 1}, "must be an object"),
    ({**GOOD, "guard": ""}, "guard must be a guard's name"),
    ({**GOOD, "repo": "deny-always.json"}, "repo must be a path under .languette/"),
    (_with_rule(action="ask"), 'rules[0].action must be "deny"'),
    (_with_rule(why="no_such_message"), "rules[0].why must name a message"),
])
def test_a_rule_set_that_does_not_load_names_the_fault(rule_set, fault):
    with pytest.raises(scan.BadRules, match=re.escape(fault)):
        engine.load(rule_set)


def test_a_rule_set_that_loads_gives_its_rules():
    assert_that([r["id"] for r in engine.load(GOOD)], equal_to(["r"]))


def test_a_rule_set_that_does_not_load_denies_every_command():
    module = types.SimpleNamespace(RULE_SET=_with_rule(action="ask"), __name__="languette.rules.guard_x")
    guard = engine.Guard(module)
    doc = Document({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": "/"}, {})
    verdict = guard.check(doc)
    while True:                                # a bad set is judged before any Need is yielded
        try:
            next(verdict)
        except StopIteration as stop:
            verdict = stop.value
            break
    assert_that(verdict["permissionDecision"], equal_to("deny"))
    assert_that(verdict["permissionDecisionReason"], contains_string("languette/rules/guard_x.py is invalid"))
    assert_that(verdict["permissionDecisionReason"], contains_string('rules[0].action must be "deny"'))
