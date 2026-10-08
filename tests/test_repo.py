"""Checks on the repo's own files: the hooks.json Claude Code loads, the
plugin's options, the stdlib-only rule for languette/, the README table."""

import ast
import json
import re
import sys
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, empty, equal_to, has_length, is_, is_not

import readme_table
from conftest import hooks_json_commands, hooks_json_prompt_command

ROOT = Path(__file__).resolve().parent.parent
GUARDS = {"guard-git-work-loss", "guard-recursive-delete", "guard-git-stacked-base", "ask-first", "guard-github-issues",
          "guard-private-terms", "prose-budget-commit", "guard-worktrees",
          "guard-bypass-labels", "guard-unparsable", "guard-infra", "guard-bypass-hooks", "guard-bypass-ruleset",
          "guard-permissions", "guard-pipe-to-shell", "guard-disk",
          "guard-host-availability", "guard-scheduled-jobs"}
# Guards that are off unless the user turns them on: their option defaults to false.
OPT_IN = {"guard_worktrees"}
# Options that are not a guard's on/off toggle: name -> type.
OTHER_OPTIONS = {"private_terms_file": "file", "private_repos": "string", "bypass_labels": "string",
                 "record_decisions": "boolean", "record_raw_commands": "boolean"}
# Per-rule switches inside one guard: boolean, on by default.
RULE_OPTIONS = {f"guard_git_work_loss_{r}" for r in ("blanket_staging", "stash", "force_push", "discard", "branch_delete")} | {
    "guard_worktrees_checkout_home", "guard_worktrees_foreign"}
# Guards that also judge file-editing tools and EnterWorktree, so they match more than Bash.
WIDE_MATCHER = {"guard-worktrees": "Bash|Edit|Write|MultiEdit|NotebookEdit|EnterWorktree"}


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


def prompt_hooks_shape(text):
    """One line per way hooks.UserPromptSubmit is not what opens the guard-github-issues
    door: a non-empty array of entries, each with a non-empty `hooks` array of
    `type: "command"` objects, one of which runs guard-github-issues.sh with the
    argument `prompt`. Without that argument the script reads the payload as a
    PreToolUse one, allows it, and the door never opens."""
    try:
        ups = json.loads(text)["hooks"]["UserPromptSubmit"]
    except (ValueError, KeyError, TypeError):
        return ["hooks.UserPromptSubmit is missing"]
    if not isinstance(ups, list) or not ups:
        return ["hooks.UserPromptSubmit is not a non-empty array"]
    bad, door = [], 0
    for i, e in enumerate(ups):
        if not isinstance(e, dict) or not isinstance(e.get("hooks"), list) or not e["hooks"]:
            bad.append(f"UserPromptSubmit[{i}].hooks is not a non-empty array")
            continue
        for j, h in enumerate(e["hooks"]):
            if not isinstance(h, dict) or h.get("type") != "command" \
                    or not isinstance(h.get("command"), str) or not h["command"]:
                bad.append(f'UserPromptSubmit[{i}].hooks[{j}] is not a {{"type": "command", "command": "..."}} object')
            elif re.search(r'guard-github-issues\.sh".*sh "\$h" prompt\b', h["command"]):
                door += 1
    if not door:
        bad.append('no UserPromptSubmit command runs guard-github-issues.sh with the argument "prompt"')
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


def test_hooks_json_wires_exactly_the_guards():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    assert_that([h for e in hj["hooks"]["PreToolUse"] for h in e["hooks"]], has_length(len(GUARDS)))
    assert_that(set(hooks_json_commands()), equal_to(GUARDS))


def test_the_foreign_worktree_guard_matches_the_file_tools_and_enterworktree():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    for guard, want in WIDE_MATCHER.items():
        [e] = [e for e in hj["hooks"]["PreToolUse"] if any(f"/hooks/{guard}.sh" in h["command"] for h in e["hooks"])]
        assert_that(e["matcher"], equal_to(want))


def test_every_guard_has_one_boolean_option_defaulting_to_true_unless_opt_in():
    uc = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["userConfig"]
    assert_that(sorted(uc), equal_to(sorted([g.replace("-", "_") for g in GUARDS] + list(OTHER_OPTIONS) + list(RULE_OPTIONS))))
    for key, opt in uc.items():
        if key in OTHER_OPTIONS:
            assert opt.get("type") == OTHER_OPTIONS[key] and opt.get("required") is False and opt.get("title") \
                and opt.get("description"), f"userConfig.{key}: want a titled, described, optional {OTHER_OPTIONS[key]}"
            continue
        want = key not in OPT_IN
        assert opt.get("type") == "boolean" and opt.get("default") is want and opt.get("title") \
            and opt.get("description"), f"userConfig.{key}: want a titled, described boolean defaulting to {str(want).lower()}"


# The parser ladder's pip parsers (docs/decisions.md, "Runtime dependencies"):
# optional, and imported only by scan.py, which reads on without them.
LADDER = {"languette/scan.py": {"tree_sitter", "tree_sitter_bash", "bashlex"}}


def test_languette_imports_only_the_standard_library():
    bad = [f"{f.relative_to(ROOT)}: {n}" for f in (ROOT / "languette").rglob("*.py")
           for node in ast.walk(ast.parse(f.read_text()))
           for n in ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
           if n.split(".")[0] not in sys.stdlib_module_names | {"languette"}
           | LADDER.get(str(f.relative_to(ROOT)), set())]
    assert_that(bad, empty())


def _generators(tree):
    return {f.name for f in tree.body if isinstance(f, ast.FunctionDef)
            and any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(f))}


def test_every_call_to_a_guard_generator_is_a_yield_from():
    # A call without it hands the caller a generator object, truthy, in place of the
    # answer, and nothing else fails: the ports' likeliest bug (#79).
    files = sorted((ROOT / "languette" / "guards").glob("*.py"))
    trees = {f.stem: ast.parse(f.read_text()) for f in files}
    gens = {m: _generators(t) for m, t in trees.items()}
    bad = []
    for m, tree in trees.items():
        mine = set(gens[m])
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("languette.guards."):
                mine |= {a.asname or a.name for a in node.names if a.name in gens.get(node.module.rsplit(".", 1)[1], ())}
        wrapped = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.YieldFrom)}
        bad += [f"{m}.py:{n.lineno}: {n.func.id}(...)" for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in mine
                and id(n) not in wrapped]
    assert_that(bad, empty())


def test_the_readme_table_is_the_scenarios_table():
    # Regenerate with: python3 tests/readme_table.py
    assert_that(readme_table.in_readme(), equal_to(readme_table.table()))


def test_the_prompt_hook_has_the_shape_that_opens_the_door():
    assert_that(prompt_hooks_shape((ROOT / "hooks/hooks.json").read_text()), empty())
    assert_that(hooks_json_prompt_command(), contains_string('sh "$h" prompt'))


def _prompt_hooks(*hooks):
    return json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": list(hooks)}]}})


_DOOR = 'h="${CLAUDE_PLUGIN_ROOT}/hooks/guard-github-issues.sh"; sh "$h" prompt'


@pytest.mark.parametrize("wrong", [
    '{"hooks": {"PreToolUse": []}}',
    '{"hooks": {"UserPromptSubmit": []}}',
    '{"hooks": {"UserPromptSubmit": [{"hooks": []}]}}',
    _prompt_hooks({"command": _DOOR}),
    _prompt_hooks({"type": "prompt", "command": _DOOR}),
    _prompt_hooks({"type": "command", "command": ""}),
    # The mutation this guards: the `prompt` argument dropped.
    _prompt_hooks({"type": "command", "command": 'h="${CLAUDE_PLUGIN_ROOT}/hooks/guard-github-issues.sh"; sh "$h"'}),
    "not json",
])
def test_the_prompt_shape_check_rejects(wrong):
    assert_that(prompt_hooks_shape(wrong), is_not(empty()))


def _guard_github_issues_matcher():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [e] = [e for e in hj["hooks"]["PreToolUse"] if any("guard-github-issues.sh" in h["command"] for h in e["hooks"])]
    return e["matcher"]


def _mcp_tools_the_guard_handles():
    # From the guard's own `case`, so a tool added there must be matched here.
    suffixes = set(re.findall(r"mcp__\*__(\w+)", (ROOT / "hooks/guard-github-issues.sh").read_text()))
    assert suffixes >= {"create_issue", "transfer_issue", "delete_issue", "issue_write"}
    return sorted(f"{prefix}{s}" for s in suffixes for prefix in ("mcp__github__", "mcp__plugin_github_github__"))


@pytest.mark.parametrize("tool", ["Bash"] + _mcp_tools_the_guard_handles())
def test_the_guard_github_issues_matcher_covers_the_tool(tool):
    assert_that(re.fullmatch(_guard_github_issues_matcher(), tool), is_not(None))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__get_issue", "mcp__github__add_issue_comment"])
def test_the_guard_github_issues_matcher_leaves_other_tools_alone(tool):
    assert_that(re.fullmatch(_guard_github_issues_matcher(), tool), is_(None))


def _guard_private_terms_matcher():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [e] = [e for e in hj["hooks"]["PreToolUse"] if any("guard-private-terms.sh" in h["command"] for h in e["hooks"])]
    return e["matcher"]


def _mcp_tools_the_guard_private_terms_handles():
    # From the guard's own `case`, so a tool added there must be matched here.
    text = (ROOT / "hooks/guard-private-terms.sh").read_text()
    suffixes = set(re.findall(r"mcp__\*__(\w+)", text))
    assert suffixes >= {"create_issue", "add_issue_comment", "create_pull_request", "pull_request_review_write"}
    return sorted(f"{prefix}{s}" for s in suffixes for prefix in ("mcp__github__", "mcp__plugin_github_github__"))


@pytest.mark.parametrize("tool", ["Bash"] + _mcp_tools_the_guard_private_terms_handles())
def test_the_guard_private_terms_matcher_covers_the_tool(tool):
    assert_that(re.fullmatch(_guard_private_terms_matcher(), tool), is_not(None))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__get_issue", "mcp__github__list_pull_requests"])
def test_the_guard_private_terms_matcher_leaves_other_tools_alone(tool):
    assert_that(re.fullmatch(_guard_private_terms_matcher(), tool), is_(None))


def _guard_bypass_labels_matcher():
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [e] = [e for e in hj["hooks"]["PreToolUse"] if any("--guard guard-bypass-labels" in h["command"] for h in e["hooks"])]
    return e["matcher"]


# Any MCP tool may carry a labels field; the guard itself tells writes from reads.
@pytest.mark.parametrize("tool", ["Bash", "mcp__github__update_issue", "mcp__plugin_github_github__issue_write",
                                  "mcp__gitea__edit_issue"])
def test_the_guard_bypass_labels_matcher_covers_the_tool(tool):
    assert_that(re.fullmatch(_guard_bypass_labels_matcher(), tool), is_not(None))


@pytest.mark.parametrize("tool", ["Read", "Write", "Edit"])
def test_the_guard_bypass_labels_matcher_leaves_other_tools_alone(tool):
    assert_that(re.fullmatch(_guard_bypass_labels_matcher(), tool), is_(None))
