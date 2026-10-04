"""Checks on the repo's own files: the hooks.json Claude Code loads, the
plugin's options, the stdlib-only rule for languette/, the README table."""

import ast
import json
import sys
from pathlib import Path

import pytest
from hamcrest import assert_that, empty, equal_to, has_length, is_not

import readme_table
from conftest import hooks_json_commands

ROOT = Path(__file__).resolve().parent.parent
GUARDS = {"no-git-footguns", "no-rm-tree", "no-delete-stacked-base", "ask-first"}


def hooks_shape(text):
    """One line per way `text` is not what Claude Code loads from a plugin's
    hooks/hooks.json: a top-level object whose `hooks` holds `PreToolUse`, an
    array of entries, each with a string `matcher` and a non-empty `hooks`
    array of objects with `type: "command"` and a string `command`. Without
    that type, or with `type: "prompt"`, the command is never run.
    `claude plugin validate --strict` accepts a garbage hooks.json, so this is
    the only thing that notices. A shape check only: what Claude Code does
    with the file is the headless smoke test's job, still run by hand."""
    try:
        hj = json.loads(text)
    except ValueError as e:
        return [f"not JSON ({e})"]
    kind = lambda v: type(v).__name__
    if not isinstance(hj, dict):
        return [f"top level is {kind(hj)}, want an object"]
    if not isinstance(hj.get("hooks"), dict):
        return ['"hooks" is not an object (a top-level "PreToolUse" is not where Claude Code looks)']
    pre = hj["hooks"].get("PreToolUse")
    if not isinstance(pre, list):
        return [f"hooks.PreToolUse is {kind(pre)}, want an array"]
    if not pre:
        return ["hooks.PreToolUse is empty"]
    bad = []
    for i, e in enumerate(pre):
        if not isinstance(e, dict):
            bad.append(f"PreToolUse[{i}] is {kind(e)}, want an object")
        elif not isinstance(e.get("matcher"), str):
            bad.append(f"PreToolUse[{i}].matcher is not a string")
        elif not isinstance(e.get("hooks"), list) or not e["hooks"]:
            bad.append(f"PreToolUse[{i}].hooks is not a non-empty array")
        else:
            for j, h in enumerate(e["hooks"]):
                where = f"PreToolUse[{i}].hooks[{j}]"
                if not isinstance(h, dict):
                    bad.append(f"{where} is {kind(h)}, want an object")
                elif h.get("type") != "command":
                    bad.append(f'{where}.type is {json.dumps(h.get("type"))}, want "command"')
                elif not isinstance(h.get("command"), str) or not h["command"]:
                    bad.append(f"{where}.command is not a non-empty string")
    return bad


def test_hooks_json_has_the_shape_claude_code_loads():
    assert_that(hooks_shape((ROOT / "hooks/hooks.json").read_text()), empty())


# What #8 found `claude plugin validate --strict` passing.
@pytest.mark.parametrize("wrong", [
    '{"PreToolUse": 5}',
    "[]",
    '{"hooks": {"PreToolUse": []}}',
    '{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}}',
    '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}',
    '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "x"}]}]}}',
    '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "prompt", "command": "x"}]}]}}',
    '{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": ""}]}]}}',
    "not json",
])
def test_the_shape_check_rejects(wrong):
    assert_that(hooks_shape(wrong), is_not(empty()))


def test_hooks_json_wires_exactly_the_four_guards():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    assert_that([h for e in hj["hooks"]["PreToolUse"] for h in e["hooks"]], has_length(4))
    assert_that(set(hooks_json_commands()), equal_to(GUARDS))


def test_every_guard_has_one_boolean_option_defaulting_to_true():
    uc = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["userConfig"]
    assert_that(sorted(uc), equal_to(sorted(g.replace("-", "_") for g in GUARDS)))
    for key, opt in uc.items():
        assert opt.get("type") == "boolean" and opt.get("default") is True and opt.get("title") \
            and opt.get("description"), f"userConfig.{key}: want a titled, described boolean defaulting to true"


def test_languette_imports_only_the_standard_library():
    bad = [f"{f.relative_to(ROOT)}: {n}" for f in (ROOT / "languette").rglob("*.py")
           for node in ast.walk(ast.parse(f.read_text()))
           for n in ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
           if n.split(".")[0] not in sys.stdlib_module_names | {"languette"}]
    assert_that(bad, empty())


def test_the_readme_table_is_the_scenarios_table():
    # Regenerate with: python3 tests/readme_table.py
    assert_that(readme_table.in_readme(), equal_to(readme_table.table()))
