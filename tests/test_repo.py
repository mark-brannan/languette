"""Checks on the repo's own files: the hooks.json Claude Code loads, the
plugin's options, the stdlib-only rule for languette/, the README table."""

import ast
import importlib
import json
import os
import re
import sys
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, empty, equal_to, has_length, is_, is_not

import readme_table
from conftest import hooks_json_commands, hooks_json_prompt_command
from languette import run
from languette.guards import (guard_bypass_labels, guard_duplicate_prs, guard_github_issues, guard_private_terms,
                              guard_protected_services, guard_signed_comments)

ROOT = Path(__file__).resolve().parent.parent
GUARDS = {"guard-git-work-loss", "guard-recursive-delete", "guard-git-stacked-base", "ask-first", "guard-github-issues",
          "guard-private-terms", "prose-budget-commit", "guard-worktrees",
          "guard-bypass-labels", "require-well-formed", "guard-infra", "guard-bypass-hooks", "guard-bypass-ruleset",
          "guard-permissions", "guard-pipe-to-shell", "guard-disks",
          "guard-host-availability", "guard-protected-services", "guard-scheduled-jobs", "guard-cross-session-send",
          "guard-secrets", "guard-review-threads", "guard-signed-comments",
          "guard-duplicate-prs"}
# Guards that are off unless the user turns them on: their option defaults to false.
OPT_IN = {"guard_worktrees", "guard_review_threads", "guard_signed_comments"}
# Options that are not a guard's on/off toggle: name -> type.
OTHER_OPTIONS = {"private_terms_file": "file", "private_repos": "string", "bypass_labels": "string",
                 "protected_services": "string", "prose_budget_command": "string",
                 "signed_comments_opening": "string", "signed_comments_signature": "string",
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
    `type: "command"` objects, one of which runs guard-github-issues. Without it
    the door never opens, and every identifier write is denied."""
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
            elif re.search(r'languette/run\.py"(?! --guard)|languette/run\.py" --guard guard-github-issues\b', h["command"]):
                door += 1
    if not door:
        bad.append("no UserPromptSubmit command runs guard-github-issues")
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


def _pre_matcher():
    """The matcher of the one PreToolUse entry in hooks/hooks.json."""
    [e] = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
    return e["matcher"]


def _reaches(guard, tool):
    """Whether a PreToolUse call to `tool` reaches `guard`: the hooks.json matcher fires
    the one command, and run.py wires the guard for that tool."""
    return bool(re.fullmatch(_pre_matcher(), tool)) and guard in run.wired("PreToolUse", tool)


def test_hooks_json_wires_exactly_the_guards():
    # One entry and one command per event, each running run.py with no --guard, for
    # every event run.py wires a guard on: a guard is reachable only through it.
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
    assert_that(sorted(hj), equal_to(sorted({ev for ev, _, _ in run.GUARDS})))
    for event, entries in hj.items():
        [command] = [h["command"] for e in entries for h in e["hooks"]]
        assert_that(command, contains_string('python3 -I "${CLAUDE_PLUGIN_ROOT}/languette/run.py"'))
        assert_that("--guard" in command, is_(False))
    assert_that(set(hooks_json_commands()), equal_to(GUARDS))
    assert_that({g.NAME for _, _, gs in run.GUARDS for g in gs}, equal_to(GUARDS))


def test_the_all_off_gate_names_every_guard_option():
    # Without python3 the PreToolUse command can read no option but these, and every
    # guard off is silence: a guard missing here fails closed even when all are off.
    [command] = [h["command"] for e in json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
                 for h in e["hooks"]]
    gate = command[:command.index("; } || { ")]
    found = re.findall(r'\[ "\$\{CLAUDE_PLUGIN_OPTION_(\w+)-\}" (= false|!= true) \]', gate)
    assert_that(gate, equal_to("{ " + " && ".join(f'[ "${{CLAUDE_PLUGIN_OPTION_{o}-}}" {t} ]' for o, t in found)))
    assert_that({o.lower(): t.split()[0] for o, t in found}, equal_to(run.gates()))


def test_the_foreign_worktree_guard_matches_the_file_tools_and_enterworktree():
    for guard, want in WIDE_MATCHER.items():
        [g] = [g for _, _, gs in run.GUARDS for g in gs if g.NAME == guard]
        for tool in want.split("|"):
            assert_that(_reaches(g, tool), is_(True))
        for tool in ("Read", "Glob", "SendMessage"):
            assert_that(_reaches(g, tool), is_(False))


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


def test_protected_services_starts_empty():
    uc = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["userConfig"]
    assert_that(guard_protected_services.protected({guard_protected_services.OPTION: uc["protected_services"]["default"]}),
                equal_to(()))


def test_a_command_rules_cmd_picks_the_program_it_matches():
    from languette import scan
    from languette.document import Document

    def hit(cmd, command):
        doc = Document({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/"}, {})
        match = {"cmd": cmd, "verbs": scan.CTL_STOPS, "unit": {"units": ["nginx"]}}
        return scan.ctl_hit(doc, match)

    assert_that(hit("systemctl", "systemctl stop nginx"), equal_to("stop nginx"))
    assert_that(hit("systemctl", "foo stop nginx"), equal_to(None))
    assert_that(hit("foo", "foo stop nginx"), equal_to("stop nginx"))
    assert_that(hit("foo", "systemctl stop nginx"), equal_to(None))


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
    assert_that("--guard" in hooks_json_prompt_command(), is_(False))
    assert_that(run.wired("UserPromptSubmit", None), equal_to([guard_github_issues]))


def _prompt_hooks(*hooks):
    return json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": list(hooks)}]}})


_DOOR = 'python3 -I "${CLAUDE_PLUGIN_ROOT}/languette/run.py" --guard guard-github-issues'


@pytest.mark.parametrize("wrong", [
    '{"hooks": {"PreToolUse": []}}',
    '{"hooks": {"UserPromptSubmit": []}}',
    '{"hooks": {"UserPromptSubmit": [{"hooks": []}]}}',
    _prompt_hooks({"command": _DOOR}),
    _prompt_hooks({"type": "prompt", "command": _DOOR}),
    _prompt_hooks({"type": "command", "command": ""}),
    # The mutation this guards: the prompt hook running some other guard.
    _prompt_hooks({"type": "command", "command": 'python3 -I "${CLAUDE_PLUGIN_ROOT}/languette/run.py" --guard ask-first'}),
    "not json",
])
def test_the_prompt_shape_check_rejects(wrong):
    assert_that(prompt_hooks_shape(wrong), is_not(empty()))


def _mcp_suffixes(tools):
    """The MCP tool-name tails in a guard's TOOLS pattern, `mcp__.*__(?:a|b)`."""
    [alts] = re.findall(r"mcp__\.\*__\(\?:([\w|]+)\)", tools.pattern)
    return set(alts.split("|"))


def _mcp_tools_the_guard_handles():
    # From the guard's own TOOLS, so a tool added there must be matched here.
    suffixes = _mcp_suffixes(guard_github_issues.TOOLS)
    assert suffixes >= {"create_issue", "transfer_issue", "delete_issue", "issue_write"}
    return sorted(f"{prefix}{s}" for s in suffixes for prefix in ("mcp__github__", "mcp__plugin_github_github__"))


@pytest.mark.parametrize("tool", ["Bash"] + _mcp_tools_the_guard_handles())
def test_the_guard_github_issues_matcher_covers_the_tool(tool):
    assert_that(_reaches(guard_github_issues, tool), is_(True))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__get_issue", "mcp__github__add_issue_comment"])
def test_the_guard_github_issues_matcher_leaves_other_tools_alone(tool):
    assert_that(_reaches(guard_github_issues, tool), is_(False))


def _mcp_tools_the_guard_private_terms_handles():
    # From the guard's own TOOLS, so a tool added there must be matched here.
    suffixes = _mcp_suffixes(guard_private_terms.TOOLS)
    assert suffixes >= {"create_issue", "add_issue_comment", "create_pull_request", "pull_request_review_write"}
    return sorted(f"{prefix}{s}" for s in suffixes for prefix in ("mcp__github__", "mcp__plugin_github_github__"))


@pytest.mark.parametrize("tool", ["Bash"] + _mcp_tools_the_guard_private_terms_handles())
def test_the_guard_private_terms_matcher_covers_the_tool(tool):
    assert_that(_reaches(guard_private_terms, tool), is_(True))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__get_issue", "mcp__github__list_pull_requests"])
def test_the_guard_private_terms_matcher_leaves_other_tools_alone(tool):
    assert_that(_reaches(guard_private_terms, tool), is_(False))


# Any MCP tool may carry a labels field; the guard itself tells writes from reads.
@pytest.mark.parametrize("tool", ["Bash", "mcp__github__update_issue", "mcp__plugin_github_github__issue_write",
                                  "mcp__gitea__edit_issue"])
def test_the_guard_bypass_labels_matcher_covers_the_tool(tool):
    assert_that(_reaches(guard_bypass_labels, tool), is_(True))


@pytest.mark.parametrize("tool", ["Read", "Write", "Edit"])
def test_the_guard_bypass_labels_matcher_leaves_other_tools_alone(tool):
    assert_that(_reaches(guard_bypass_labels, tool), is_(False))


@pytest.mark.parametrize("tool", ["Bash"] + sorted(f"{prefix}{s}" for s in _mcp_suffixes(guard_duplicate_prs.TOOLS)
                                                   for prefix in ("mcp__github__", "mcp__plugin_github_github__")))
def test_the_guard_duplicate_pr_matcher_covers_the_tool(tool):
    assert_that(_reaches(guard_duplicate_prs, tool), is_(True))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__update_pull_request", "mcp__github__list_pull_requests"])
def test_the_guard_duplicate_pr_matcher_leaves_other_tools_alone(tool):
    assert_that(_reaches(guard_duplicate_prs, tool), is_(False))


def _mcp_tools_the_guard_signed_comments_handles():
    # From the guard's own TOOLS, so a tool added there must be matched here.
    suffixes = _mcp_suffixes(guard_signed_comments.TOOLS)
    assert suffixes >= {"add_issue_comment", "add_reply_to_pull_request_comment", "add_comment_to_pending_review",
                        "pull_request_review_write", "update_issue_comment"}
    return sorted(f"{prefix}{s}" for s in suffixes for prefix in ("mcp__github__", "mcp__plugin_github_github__"))


@pytest.mark.parametrize("tool", ["Bash"] + _mcp_tools_the_guard_signed_comments_handles())
def test_the_guard_signed_comments_matcher_covers_the_tool(tool):
    assert_that(_reaches(guard_signed_comments, tool), is_(True))


@pytest.mark.parametrize("tool", ["Read", "mcp__github__get_issue", "mcp__github__create_issue"])
def test_the_guard_signed_comments_matcher_leaves_other_tools_alone(tool):
    assert_that(_reaches(guard_signed_comments, tool), is_(False))


def _gathered(gen):
    """Drive a guard's gather generator against the real disk, the way world answers
    the path and read Needs it yields."""
    answer = None
    while True:
        try:
            need = gen.send(answer)
        except StopIteration as stop:
            return stop.value
        op, path = need.args[0], need.args[-1]
        answer = Path(path).read_text() if need.kind == "read" else getattr(os.path, op)(path)


@pytest.mark.parametrize("rule_file", sorted((ROOT / "languette" / "rules").glob("*.json")), ids=lambda p: p.name)
def test_every_shipped_rule_file_loads_and_is_packaged(rule_file):
    # docs/design/guard-rules.md, "Rule sets that do not load": the deny a bad file
    # gives never greets an install.
    guard = importlib.import_module(f"languette.guards.{rule_file.stem.replace('-', '_')}")
    assert_that(Path(guard.RULE_FILE), equal_to(rule_file))
    got = _gathered(guard.rules(str(rule_file)))
    assert_that(got[:len(guard.RULES)], equal_to(guard.RULES))
    assert_that((ROOT / "pyproject.toml").read_text(), contains_string('languette = ["rules/*.json"]'))
