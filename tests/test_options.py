"""Every option in .claude-plugin/plugin.json is tested both ways, and read in
one place.

A switch has a row in features/ that sets it on and one that sets it off, by
name: a scenario that leaves it alone proves nothing about the switch, since
the harness turns opt-in guards on for their own features. An opt-in guard's
off is any value but "true", so unset counts.

Each option's environment name appears once in languette/, the one place it
is read; a second literal is a second reading that can drift from the first.
A guard's own switch is read through run.option(g), so its name appears
nowhere but an opt-in guard's OPT_IN; guard-git-work-loss reads its rules'
switches through one f-string prefix."""

import ast
import json
import re
from pathlib import Path

import pytest
from gherkin.parser import Parser
from gherkin.pickles.compiler import Compiler

from languette import run

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "CLAUDE_PLUGIN_OPTION_"
OPTIONS = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["userConfig"]
SWITCHES = sorted(k for k, v in OPTIONS.items() if v["type"] == "boolean")
SET = re.compile(r'(?P<var>CLAUDE_PLUGIN_OPTION_[A-Z0-9_]+) is (?:"(?P<value>.*)"|unset)\Z')


def _states():
    """Option env name -> the states (True on, False off) some scenario sets it to by name."""
    seen = {}
    for path in sorted((ROOT / "features").glob("*.feature")):
        if path.name == "smoke.feature":       # not in the per-push run (test_features.py)
            continue
        doc = Parser().parse(path.read_text())
        doc["uri"] = path.name
        for pickle in Compiler().compile(doc):
            for step in pickle["steps"]:
                if m := SET.match(step["text"]):
                    seen.setdefault(m["var"], []).append(m["value"])
    return seen


STATES = _states()


@pytest.mark.parametrize("name", SWITCHES)
def test_every_switch_has_an_on_row_and_an_off_row(name):
    var = PREFIX + name.upper()
    default_on = OPTIONS[name]["default"]
    # The gate run._on applies: on unless exactly "false", or for an opt-in on only if exactly "true".
    states = {(v != "false") if default_on else (v == "true") for v in STATES.get(var, [])}
    missing = [s for s in ("on", "off") if (s == "on") not in states]
    assert not missing, f"no scenario in features/ sets {var} {' or '.join(missing)} by name"


def _reads():
    """Env name -> places it appears in languette/, outside docstrings; an f-string
    is listed under its constant prefix followed by '*'."""
    found = {}
    for path in sorted((ROOT / "languette").rglob("*.py")):
        tree = ast.parse(path.read_text())
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                      and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        inside = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            where = f"{path.relative_to(ROOT)}:{getattr(n, 'lineno', '?')}"
            if isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant):
                head = n.values[0].value
                if head.startswith(PREFIX) and head != PREFIX:
                    found.setdefault(head + "*", []).append(where)
            elif (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
                  and id(n) not in inside and re.fullmatch(PREFIX + r"[A-Z0-9_]+", n.value)):
                found.setdefault(n.value, []).append(where)
    return found


READS = _reads()
GUARDS = {run.option(g): g for _, _, gs in run.GUARDS for g in gs}


@pytest.mark.parametrize("name", sorted(OPTIONS))
def test_every_option_is_read_in_one_place(name):
    var = PREFIX + name.upper()
    places = READS.get(var, []) + [p for k, ps in READS.items() if k.endswith("*") and var.startswith(k[:-1])
                                   for p in ps]
    if var in GUARDS:
        # run._on reads it through run.option(g); only an opt-in guard spells it, once, as OPT_IN.
        want = 1 if hasattr(GUARDS[var], "OPT_IN") else 0
        assert len(places) == want, f"{var} is a guard's switch, read by run._on, yet spelled at {places}"
    else:
        assert len(places) == 1, f"{var} should be read in exactly one place in languette/, not {places or 'none'}"
