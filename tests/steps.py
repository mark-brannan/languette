"""The step vocabulary for features/*.feature. Moved out of conftest.py
unchanged; conftest.py imports it, so pytest-bdd finds the steps."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from hamcrest import assert_that, equal_to
from pytest_bdd import given, parsers, then, when

from harness import *  # noqa: F401,F403
from harness import (ROOT, EVENTS, GUARD_NAMES, OPT_INS, SCRUB, Ctx, _respond_all, hooks_json_event_command,
                     scattered)
from matchers import Verdict, asks, denies, is_silent, warns_about
from languette import run, scan, verdict, world

# --- Given ---------------------------------------------------------------

@given(parsers.parse('the working directory is "{path}"'))
@when(parsers.parse('the working directory is "{path}"'))
def _cwd(ctx, path):
    ctx.cwd = path


@given("the payload carries no session id")
@when("the payload carries no session id")
def _no_session(ctx):
    ctx.session = None


@given(parsers.parse('the call comes from subagent "{agent}"'))
@when(parsers.parse('the call comes from subagent "{agent}"'))
def _from_subagent(ctx, agent):
    ctx.agent = agent


@given("the call comes from the session itself")
@when("the call comes from the session itself")
def _from_session(ctx):
    ctx.agent = None


@given(parsers.parse('the session is "{session}"'))
@when(parsers.parse('the session is "{session}"'))
def _session(ctx, session):
    ctx.session = session


@given("a project directory")
def _project(ctx):
    ctx.proj = Path(ctx.mkdtemp())
    (ctx.proj / "sub").mkdir()
    subprocess.run(["git", "init", "-q", str(ctx.proj)], check=True)
    (ctx.proj / "t.jsonl").touch()             # a session has a transcript, if an empty one


@given("the project directory is not a git repository")
def _not_a_repo(ctx):
    shutil.rmtree(ctx.proj / ".git")


@given("the project's git index is corrupt")
def _corrupt_index(ctx):
    (ctx.proj / ".git/index").write_text("not an index\n")


@given(parsers.parse('the file "{rel}" holds:'))
def _file(ctx, rel, docstring):
    # A path under {HOME} or {TMP} is absolute once expanded; any other is the project's.
    assert ctx.proj or Path(ctx.expand(rel)).is_absolute(), f"{rel!r} needs a project"
    f = Path(ctx.proj or "/", ctx.expand(rel))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(ctx.expand(docstring))


@given(parsers.parse('the file "{rel}" is committed'))
def _file_committed(ctx, rel):
    subprocess.run(["git", "-C", str(ctx.proj), "add", "--", rel], check=True)
    subprocess.run(["git", "-C", str(ctx.proj), "-c", "user.email=a@a", "-c", "user.name=a",
                     "commit", "-q", "-m", "x", "--", rel], check=True)


@given("the private terms file holds:")
def _terms(ctx, docstring):
    f = Path(ctx.mkdtemp()) / "private-terms.txt"
    f.write_text(ctx.expand(docstring) + "\n")
    ctx.env["CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE"] = str(f)


@given("the transcript holds:")
def _transcript(ctx, docstring):
    (ctx.proj / "t.jsonl").write_text(docstring + "\n")


@given("the transcript is missing")
def _no_transcript(ctx):
    (ctx.proj / "t.jsonl").unlink()


@given("the approvals already spent are:")
def _spent(ctx, docstring):
    (ctx.proj / "t.jsonl.languette-ask").write_text(docstring + "\n")


@given(parsers.re(r'(?P<var>[A-Z][A-Z0-9_]*) is "(?P<value>.*)"'))
def _setenv(ctx, var, value):
    ctx.env[var] = value


@given("every guard's option is off")
def _all_off(ctx):
    # An ordinary guard's option exactly "false"; an opt-in guard's unset, its default.
    for g in {g for _, _, gs in run.GUARDS for g in gs}:
        ctx.env[run.option(g)] = None if hasattr(g, "OPT_IN") else "false"


@given("no engine is configured")
def _no_engine(ctx):
    ctx.env["CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMAND"] = None


@given(parsers.re(r"(?P<var>[A-Z][A-Z0-9_]*) is unset"))
def _unsetenv(ctx, var):
    ctx.env[var] = None
    if var == "CLAUDE_PROJECT_DIR":
        ctx.project_env = False


def _guard_module(guard):
    return __import__(f"languette.guards.{guard.replace('-', '_')}", fromlist=["RULE_FILE"])


@given(parsers.parse('the rule file of "{guard}" is absent'))
def _rule_file_absent(ctx, guard, monkeypatch):
    monkeypatch.setattr(_guard_module(guard), "RULE_FILE", str(Path(ctx.mkdtemp()) / f"{guard}.json"))


@given(parsers.parse('the rule file of "{guard}" holds:'))
def _rule_file(ctx, guard, monkeypatch, docstring):
    f = Path(ctx.mkdtemp()) / f"{guard}.json"
    f.write_text(docstring + "\n")
    monkeypatch.setattr(_guard_module(guard), "RULE_FILE", str(f))


@given(parsers.parse('the rule file of "{guard}" nests {depth:d} brackets deep'))
def _rule_file_deep(ctx, guard, depth, monkeypatch):
    f = Path(ctx.mkdtemp()) / f"{guard}.json"
    f.write_text("[" * depth)
    monkeypatch.setattr(_guard_module(guard), "RULE_FILE", str(f))


@given(parsers.parse('the directory "{path}"'))
def _mkdir(ctx, path):
    Path(ctx.expand(path)).mkdir(parents=True, exist_ok=True)


@given(parsers.parse('a git repository at "{path}"'))
def _git_init(ctx, path):
    d = Path(ctx.expand(path))
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True)


@given(parsers.parse('a yadm-style repository at "{path}" whose work tree is "{wt}"'))
def _yadm_repo(ctx, path, wt):
    d = Path(ctx.expand(path))
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(d)], check=True)
    for k, v in (("core.bare", "false"), ("core.worktree", ctx.expand(wt))):
        subprocess.run(["git", "--git-dir", str(d), "config", k, v], check=True)


@given(parsers.parse('a linked worktree "{path}" of the repository at "{repo}"'))
def _linked_worktree(ctx, path, repo):
    r, d = ctx.expand(repo), ctx.expand(path)
    ident = ["-c", "user.email=t@e", "-c", "user.name=t"]
    if subprocess.run(["git", "-C", r, "rev-parse", "-q", "--verify", "HEAD"], capture_output=True).returncode:
        subprocess.run(["git", "-C", r, *ident, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    Path(d).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", r, "worktree", "add", "-q", "-b", Path(d).name, d], check=True)


@given(parsers.parse('the symlink "{path}" to "{target}"'))
def _symlink(ctx, path, target):
    Path(ctx.expand(path)).symlink_to(ctx.expand(target))


@given("the claude plugin's door file is already present")
def _claude_door_present(ctx):
    Path(ctx.doordir(), f"claude-issue-door.{ctx.session}").write_text("")


@then("the claude plugin's door file is still present")
def _claude_door_still(ctx):
    assert Path(ctx.doordir(), f"claude-issue-door.{ctx.session}").exists()


@given(parsers.parse('the door file is a symlink to "{target}"'))
def _door_symlink(ctx, target):
    victim = Path(ctx.expand(target))
    victim.write_text("keep")
    Path(ctx.doordir(), f"languette-guard-github-issues.{ctx.session}").symlink_to(victim)


@then(parsers.parse('the door file is a plain file and "{target}" still holds "{content}"'))
def _door_replaced(ctx, target, content):
    door = Path(ctx.doordir(), f"languette-guard-github-issues.{ctx.session}")
    assert not door.is_symlink(), "door file is still a symlink"
    assert Path(ctx.expand(target)).read_text() == content


@given('the stubs "gh" and "timeout" are first on PATH')
def _stubs(ctx):
    ctx.stubs, ctx.stub_log = True, ctx.mkdtemp()


@given('the stub "gh" is first on PATH, for a Python guard')
def _gh_stub_python(ctx):
    # The Python engine's guards get only the scenario's env, so PATH and the
    # stub log travel there rather than through the shell engine's subprocess.
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    ctx.env["PATH"] = str(ROOT / "tests/stubs") + os.pathsep + os.environ["PATH"]
    ctx.env["LANGUETTE_STUB_LOG"] = ctx.stub_log


@given(parsers.parse('review thread "{tid}" holds:'))
def _review_thread(ctx, tid, datatable):
    # What the gh stub answers for this thread id, as GitHub's GraphQL shapes
    # it: an author column, an optional type (User unless it says Bot), a body.
    # A blank author is a deleted account, which GitHub gives no author.
    head, *rows = datatable
    if "GH_THREADS" not in ctx.env:
        ctx.env["GH_THREADS"] = ctx.mkdtemp()
    nodes = []
    for n, row in enumerate(rows):
        r = dict(zip(head, row))
        author = {"login": r["author"], "__typename": r.get("type") or "User"} if r["author"] else None
        nodes.append({"author": author, "body": r["body"], "createdAt": f"2026-10-08T00:00:{n:02d}Z"})
    Path(ctx.env["GH_THREADS"], f"{tid}.json").write_text(json.dumps({"comments": {"nodes": nodes}}))


@given(parsers.parse('a clone of "{url}" at "{path}" on branch "{branch}"'))
def _clone(ctx, url, path, branch):
    d = ctx.expand(path)
    git = ["git", "-C", d, "-c", "user.email=t@e", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run([*git, "remote", "add", "origin", url], check=True)
    if branch != "main":
        subprocess.run([*git, "checkout", "-q", "-b", branch], check=True)
    for b in {"main", branch}:
        subprocess.run([*git, "update-ref", f"refs/remotes/origin/{b}", "HEAD"], check=True)
        subprocess.run([*git, "config", f"branch.{b}.remote", "origin"], check=True)
        subprocess.run([*git, "config", f"branch.{b}.merge", f"refs/heads/{b}"], check=True)
    subprocess.run([*git, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"], check=True)


@given(parsers.parse('the remote HEAD of "{path}" points at "{branch}"'))
def _remote_head(ctx, path, branch):
    d = ctx.expand(path)
    subprocess.run(["git", "-C", d, "update-ref", f"refs/remotes/origin/{branch}", "HEAD"], check=True)
    subprocess.run(["git", "-C", d, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{branch}"],
                   check=True)


def _engine(ctx, command):
    # The prose_budget_command option names the engine.
    ctx.env["CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMAND"] = command


@given('the stub "prose-budget" is the engine')
def _prose_budget_stub(ctx):
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    _engine(ctx, str(ROOT / "tests/stubs/prose-budget"))


@given('the stub "prose-budget" is the engine, at a relative path')
def _prose_budget_stub_relative(ctx):
    assert ctx.proj, "test setup: a relative engine path needs a project directory"
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    dest = ctx.proj / "prose-budget"
    shutil.copy(ROOT / "tests/stubs/prose-budget", dest)
    dest.chmod(0o755)
    _engine(ctx, "./prose-budget")


@given('the stub "prose-budget" is the engine, by bare name on PATH')
def _prose_budget_stub_bare(ctx):
    ctx.stubs, ctx.stub_log = True, ctx.stub_log or ctx.mkdtemp()
    _engine(ctx, "prose-budget")


@given(parsers.re(r'PATH holds only "(?P<tools>[^"]*)"(?P<gh> and the stub "gh")?'))
def _bare_path(ctx, tools, gh):
    ctx.bare = ctx.mkdtemp()
    for t in tools.split():
        p = shutil.which(t)
        assert p, f"test setup: no {t} on PATH"
        os.symlink(p, os.path.join(ctx.bare, t))
    if gh:
        ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
        os.symlink(ROOT / "tests/stubs/gh", os.path.join(ctx.bare, "gh"))


@given(parsers.parse('the hook is the hooks.json command for "{guard}"'))
def _hooks_json(ctx, guard):
    ctx.hook, ctx.wired = hooks_json_commands()[guard], guard


@given(parsers.parse('the hook is the hooks.json {event} command for "{guard}"'))
def _hooks_json_event(ctx, event, guard):
    ctx.hook = hooks_json_event_command(event)


@when(parsers.parse('Claude Code fires {event} for tool "{tool}"'))
def _fires(ctx, event, tool):
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": event, "session_id": ctx.session, "tool_name": tool,
                                  "tool_input": {}, "tool_response": "..."})))


@then("the cross-session state file is gone")
def _send_state_gone(ctx):
    assert not _send_state_file(ctx).exists()


@then(parsers.parse('the cross-session state file names "{tool}"'))
def _send_state_names(ctx, tool):
    assert json.loads(_send_state_file(ctx).read_text())["read"] == tool


@given(parsers.parse('the plugin\'s script for "{guard}" crashes'))
def _crash(ctx, guard):
    root = Path(ctx.mkdtemp())
    assert "languette/run.py" in hooks_json_commands()[guard]
    (root / "languette").mkdir()
    (root / "languette/run.py").write_text("raise SystemExit(3)\n")
    ctx.env["CLAUDE_PLUGIN_ROOT"] = str(root)


@given(parsers.parse('the plugin\'s script for "{guard}" prints a deny'))
def _load_deny(ctx, guard):
    """run.py's own answer when a guard will not import: a deny, exit 0, before it
    knows the event, so a state hook must read any output as a failure."""
    root = Path(ctx.mkdtemp())
    assert "languette/run.py" in hooks_json_commands()[guard]
    (root / "languette").mkdir()
    (root / "languette/run.py").write_text(
        "print('{\"hookSpecificOutput\": {\"permissionDecision\": \"deny\"}}')\n")
    ctx.env["CLAUDE_PLUGIN_ROOT"] = str(root)


@given(parsers.parse('the plugin\'s script for "{guard}" fails after reading its payload'))
def _fails_mid_run(ctx, guard):
    """The real run.py, whose verdict step raises: a state event then reaches its own
    failure path (_state_failed), not the hooks.json sh fallback."""
    root = Path(ctx.mkdtemp())
    assert "languette/run.py" in hooks_json_commands()[guard]
    shutil.copytree(ROOT / "languette", root / "languette", ignore=shutil.ignore_patterns("__pycache__"))
    with open(root / "languette/verdict.py", "a") as f:
        f.write("\n\ndef verdict(event, findings):\n    raise RuntimeError('boom')\n")
    ctx.env["CLAUDE_PLUGIN_ROOT"] = str(root)



# --- When ----------------------------------------------------------------

# Greedy to the last backtick, so a command may hold backticks of its own.
def _ran(ctx):
    """Claude Code fires PostToolUse only for a call that ran: when this guard
    let it through, spend the door as the post hook would. The verdict the
    scenario judges stays the PreToolUse one."""
    if ctx.guard == "guard-cross-session-send" and not ctx.hook:
        _post(ctx, "PostToolUse")
    if ctx.guard != "guard-github-issues" or ctx.hook or ctx.verdict.decision == "deny":
        return
    pre, ctx.arg = ctx.verdict, "post"
    ctx.run(ctx.stdin)
    ctx.arg, ctx.verdict = None, pre


def _post(ctx, event):
    """The call ran: fire `event` on its payload, keeping the PreToolUse verdict."""
    pre, p = ctx.verdict, json.loads(ctx.stdin)
    ctx.run(json.dumps({**p, "hook_event_name": event, "tool_response": "..."}))
    assert ctx.verdict.stdout == "", f"{event} hook printed {ctx.verdict.stdout!r}"
    ctx.verdict = pre


@when(parsers.re(r"the agent runs `(?P<command>.*)`, its post hook carrying no working directory", flags=re.S))
def _runs_post_no_cwd(ctx, command):
    ctx.run(ctx.payload(command))
    pre, p = ctx.verdict, json.loads(ctx.stdin)
    del p["cwd"]
    ctx.run(json.dumps({**p, "hook_event_name": "PostToolUse", "tool_response": "..."}))
    ctx.verdict = pre


@when(parsers.re(r"the agent runs `(?P<command>.*)`, which fails", flags=re.S))
def _runs_failing(ctx, command):
    ctx.run(ctx.payload(command))
    _post(ctx, "PostToolUseFailure")


@when(parsers.re(r"the agent runs `(?P<command>.*)`", flags=re.S))
def _runs(ctx, command):
    ctx.run(ctx.payload(command))
    _ran(ctx)


@when(parsers.re(r"the agent nests `(?P<template>.*)` (?P<n>\d+) deep"))
def _nests(ctx, template, n):
    # Each {} becomes the template again, n times over; the last ones are x.
    command = template
    for _ in range(int(n) - 1):
        command = command.replace("{}", template)
    ctx.run(ctx.payload(command.replace("{}", "x")))


@when(parsers.re(r"the agent runs `(?P<head>.*)`, `(?P<filler>.*)` (?P<n>\d+) times, then `(?P<tail>.*)`"))
def _repeats(ctx, head, filler, n, tail):
    ctx.run(ctx.payload(" ".join([head] + [filler] * int(n) + [tail])))


def _transcript(ctx):
    if not ctx.proj:
        ctx.proj = Path(ctx.mkdtemp())
    (ctx.proj / "t.jsonl").touch()


@when(parsers.re(r"another guard denies `(?P<command>.*)`", flags=re.S))
def _denied_elsewhere(ctx, command):
    # This guard's PreToolUse ran, the call did not: Claude Code records the
    # deny as its result, and fires no PostToolUse.
    _transcript(ctx)
    ctx.run(ctx.payload(command))
    _record_result(ctx, "guard-private-terms: denied")


@when("that call ran, but its post hook never did")
def _ran_unspent(ctx):
    _record_result(ctx, "https://github.com/o/r/issues/9", is_error=False)


@then(parsers.parse('"{target}" still holds "{content}"'))
def _still_holds(ctx, target, content):
    assert Path(ctx.expand(target)).read_text() == content


@then("the decision record is empty")
def _no_record(ctx):
    assert not (Path(ctx.expand("{TMP}")) / "state/languette/decisions.jsonl").exists()


@then(parsers.re(r"the decision record holds the command `(?P<command>.*)`"))
def _recorded_command(ctx, command):
    lines = (Path(ctx.expand("{TMP}")) / "state/languette/decisions.jsonl").read_text().splitlines()
    assert len(lines) == 1, lines
    assert json.loads(lines[0])["command"] == json.loads(command)


@when(parsers.re(r"the agent starts `(?P<command>.*)`", flags=re.S))
def _starts(ctx, command):
    # PreToolUse ran and the call is still running: no result, no PostToolUse.
    _transcript(ctx)
    ctx.run(ctx.payload(command))


@when("the agent runs:")
def _runs_doc(ctx, docstring):
    ctx.run(ctx.payload(docstring))


@when("the agent runs it again")
def _rerun(ctx):
    p = json.loads(ctx.stdin)
    if "tool_use_id" in p:
        ctx.calls += 1
        p["tool_use_id"] = f"toolu_call{ctx.calls}"
    ctx.run(json.dumps(p))


def _record_result(ctx, content, is_error=True, **extra):
    call = json.loads(ctx.stdin)["tool_use_id"]
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call, "content": content, "is_error": is_error}]}, **extra}
    with (ctx.proj / "t.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


@when(parsers.parse('Claude Code records that call\'s result as "{content}"'))
def _call_result(ctx, content):
    _record_result(ctx, content)


@when("the user declines that call")
def _call_declined(ctx):
    _record_result(ctx, "The user doesn't want to proceed with this tool use. The tool use was rejected.",
                   toolUseResult="User rejected tool use")


@when("the human speaks, opening the door")
def _open_door(ctx):
    ctx.arg = "prompt"
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "UserPromptSubmit", "session_id": ctx.session,
                                    "prompt": "yes, file it"})))
    ctx.arg = None


@when("the human speaks, through the hooks.json prompt hook")
def _open_door_via_hooks_json(ctx):
    # The UserPromptSubmit command exactly as hooks.json writes it, run the way
    # Claude Code runs it; the PreToolUse hook is restored for the next step.
    pretool, ctx.hook = ctx.hook, hooks_json_prompt_command()
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "UserPromptSubmit", "session_id": ctx.session,
                                    "prompt": "yes, file it"})))
    ctx.hook = pretool


@when(parsers.re(r'the agent calls MCP tool "(?P<tool>[^"]+)" with input `(?P<inp>.*)`', flags=re.S))
def _mcp_call(ctx, tool, inp):
    ctx.run(json.dumps(ctx.as_sent({"session_id": ctx.session, "tool_name": tool, "tool_input": json.loads(ctx.expand(inp))})))
    _ran(ctx)


@when(parsers.re(r'the agent calls tool "(?P<tool>[^"]+)" with input `(?P<inp>.*)`', flags=re.S))
def _tool_call(ctx, tool, inp):
    ctx.run(json.dumps(ctx.as_sent({"session_id": ctx.session, "tool_name": tool,
                                  "tool_input": json.loads(ctx.expand(inp)), "cwd": ctx.expand(ctx.cwd)})))
    _ran(ctx)


@given(parsers.parse('the permission mode is "{mode}"'))
@when(parsers.parse('the permission mode is "{mode}"'))
def _mode(ctx, mode):
    ctx.mode = mode


@given("the payload carries no permission mode")
def _no_mode(ctx):
    ctx.mode = None


@when("the human speaks")
def _speaks(ctx):
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "UserPromptSubmit", "session_id": ctx.session,
                                  "prompt": "go on"})))
    assert ctx.verdict.stdout == "", f"UserPromptSubmit printed {ctx.verdict.stdout!r}"


@given(parsers.parse('the session starts from "{source}"'))
@when(parsers.parse('the session starts from "{source}"'))
def _session_starts(ctx, source):
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "SessionStart", "session_id": ctx.session, "source": source})))
    assert ctx.verdict.stdout == "", f"SessionStart printed {ctx.verdict.stdout!r}"


@when(parsers.parse('the agent spawns a subagent named "{name}", given id "{agent}"'))
def _spawns(ctx, name, agent):
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "PostToolUse", "session_id": ctx.session, "tool_name": "Agent",
                                  "tool_input": {"name": name, "prompt": "p", "description": "d"},
                                  "tool_response": {"status": "async_launched", "agentId": agent}})))
    assert ctx.verdict.stdout == "", f"PostToolUse printed {ctx.verdict.stdout!r}"


@given(parsers.parse('the session\'s team config lists "{name}"'))
def _team(ctx, name):
    d = Path(os.environ["HOME"], ".claude", "teams", f"session-{ctx.session[:8]}")
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps({"members": [{"name": "team-lead", "agentType": "team-lead"},
                                                           {"name": name, "agentId": f"{name}@x"}]}))
    ctx.cleanups.append(lambda: shutil.rmtree(d, ignore_errors=True))


@when(parsers.parse('subagent "{agent}" starts'))
def _subagent_starts(ctx, agent):
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "SubagentStart", "session_id": ctx.session,
                                  "agent_id": agent, "agent_type": "general-purpose"})))
    assert ctx.verdict.stdout == "", f"SubagentStart printed {ctx.verdict.stdout!r}"


def _send(ctx, to, message, **extra):
    ctx.calls += 1
    ctx.run(json.dumps(ctx.as_sent({"hook_event_name": "PreToolUse", "session_id": ctx.session, "tool_name": "SendMessage",
                                  "tool_input": {"to": to, "message": message},
                                  "tool_use_id": f"toolu_call{ctx.calls}", **extra})))


@when(parsers.re(r'the agent sends "(?P<to>[^"]*)" the message `(?P<message>.*)`', flags=re.S))
def _sends(ctx, to, message):
    _send(ctx, to, message.replace("\\n", "\n"))


@when(parsers.re(r'subagent "(?P<agent>[^"]+)" sends "(?P<to>[^"]*)" the message `(?P<message>.*)`', flags=re.S))
def _subagent_sends(ctx, agent, to, message):
    _send(ctx, to, message, agent_id=agent)


def _send_state_file(ctx):
    return Path(ctx.doordir(), f"languette-guard-cross-session-send.{ctx.session}")


@given(parsers.parse("the cross-session state file holds `{text}`"))
@when(parsers.parse("the cross-session state file holds `{text}`"))
def _send_state(ctx, text):
    _send_state_file(ctx).write_text(text)


@when("the cross-session state file is open to others")
def _send_state_open(ctx):
    _send_state_file(ctx).chmod(0o666)


@given(parsers.parse('the cross-session state file is a symlink to "{target}"'))
def _send_state_link(ctx, target):
    victim = Path(ctx.expand(target))
    victim.write_text("keep")
    _send_state_file(ctx).unlink(missing_ok=True)
    _send_state_file(ctx).symlink_to(victim)


@when("the payload is:")
def _raw(ctx, docstring):
    ctx.run(docstring)


@when(parsers.re(r"the scanner reads `(?P<command>.*)`", flags=re.S))
def _scan(ctx, command):
    ctx.scanned = command


@when("the scanner reads:")
def _scan_doc(ctx, docstring):
    ctx.scanned = docstring


@when(parsers.re(r"the scanner reads the JSON string (?P<js>\".*\")"))
def _scan_json(ctx, js):
    ctx.scanned = json.loads(js)


def _languette_scan(ctx, args, command):
    """features/scan.feature: the command line an outside hook runs."""
    argv = [sys.executable, "-I", str(ROOT / "languette" / "__main__.py"), *shlex.split(args)]
    r = subprocess.run(argv, input=command, cwd=ctx.process_dir, capture_output=True, text=True, timeout=10)
    ctx.out, ctx.err, ctx.code = r.stdout, r.stderr, r.returncode


@when(parsers.re(r"`languette (?P<args>scan[^`]*)` reads `(?P<command>.*)`", flags=re.S))
def _languette_scan_line(ctx, args, command):
    _languette_scan(ctx, args, command)


@when(parsers.re(r"`languette (?P<args>scan[^`]*)` reads:"))
def _languette_scan_doc(ctx, args, docstring):
    _languette_scan(ctx, args, docstring)


@when(parsers.re(r"`languette (?P<args>scan[^`]*)` reads a command one byte over the length limit"))
def _languette_scan_big(ctx, args):
    _languette_scan(ctx, args, "x" * (scan.LENGTH_MAX + 1))


@then("it prints:")
def _prints(ctx, docstring):
    assert ctx.code == 0, f"exit {ctx.code}, stderr {ctx.err!r}"
    assert json.loads(ctx.out) == json.loads(docstring)


@then("it prints no segments")
def _prints_no_segments(ctx):
    assert ctx.code == 0, f"exit {ctx.code}, stderr {ctx.err!r}"
    assert json.loads(ctx.out)["segments"] == []


@then(parsers.re(r'it prints nothing and exits (?P<code>\d+), naming "(?P<text>.*)"'))
def _prints_nothing_exits(ctx, code, text):
    assert (ctx.out, ctx.code) == ("", int(code)), f"exit {ctx.code}, stdout {ctx.out!r}"
    assert text in ctx.err, ctx.err


def scanned(ctx, mode):
    if mode == "tokens":
        s = scan.Scan(ctx.scanned)
        assert s.rung == IN_PROCESS[ctx.engine][0], f"the {s.rung} rung read it"
        return s.tokens()
    return [("1:" if nested else "0:") + t for t, nested in scan.texts_of_command(ctx.scanned + "\n")]


# --- Then ----------------------------------------------------------------

def _from_the_wired_guard(ctx):
    """A wiring row's verdict is its own guard's, or the hook's fail-closed deny: the one
    hooks.json command runs every guard, so another's finding could stand in for a guard
    that never ran. The same call through the command narrowed to that guard must agree."""
    if not ctx.wired or "fails closed" in (ctx.verdict.reason or ""):
        return
    run_py = 'python3 -I "${CLAUDE_PLUGIN_ROOT}/languette/run.py"'
    assert ctx.hook.count(run_py) == 1, ctx.hook
    hook, whole = ctx.hook, ctx.verdict
    ctx.hook = hook.replace(run_py, f"{run_py} --guard {ctx.wired}")
    try:
        ctx.run(ctx.stdin)
        alone = ctx.verdict
    finally:
        ctx.hook, ctx.verdict = hook, whole
    assert (alone.decision, alone.reason) == (whole.decision, whole.reason), \
        f"want {ctx.wired}'s own verdict ({alone.decision}: {alone.reason}), got {whole.decision}: {whole.reason}"


@then("the guard denies")
def _denies(ctx):
    assert_that(ctx.verdict, denies())
    _from_the_wired_guard(ctx)


@then(parsers.re(r'the guard denies, naming "(?P<text>.*)"'))
def _denies_naming(ctx, text):
    assert_that(ctx.verdict, denies(naming=ctx.expand(text)))


@then(parsers.re(r'the guard denies, not naming "(?P<text>.*)"'))
def _denies_not_naming(ctx, text):
    assert_that(ctx.verdict, denies())
    assert ctx.expand(text) not in ctx.verdict.reason, f"the reason names {text!r}: {ctx.verdict.reason}"


@then(parsers.re(r'the guard asks, naming "(?P<text>.*)"'))
def _asks_naming(ctx, text):
    assert_that(ctx.verdict, asks(naming=ctx.expand(text)))


@then("the guard asks")
def _asks(ctx):
    assert_that(ctx.verdict, asks())
    _from_the_wired_guard(ctx)


@then("the guard is silent")
def _silent(ctx):
    assert_that(ctx.verdict, is_silent())


@then(parsers.re(r'the guard warns about "(?P<text>.*)"'))
def _warns(ctx, text):
    assert_that(ctx.verdict, warns_about(text))


@then(parsers.re(r'the guard allows, rewriting the command to "(?P<text>.*)"'))
def _rewrites(ctx, text):
    assert ctx.verdict.decision == "allow", ctx.verdict.show()
    got = ctx.verdict.out.get("updatedInput", {}).get("command")
    assert got == ctx.expand(text), f"rewritten to {got!r}, want {ctx.expand(text)!r}"


@then(parsers.re(r'the guard allows, rewriting the input field "(?P<key>[a-z_]+)" to "(?P<text>.*)"'))
def _rewrites_field(ctx, key, text):
    assert ctx.verdict.decision == "allow", ctx.verdict.show()
    got = ctx.verdict.out.get("updatedInput", {}).get(key)
    assert got == ctx.expand(text), f"{key} rewritten to {got!r}, want {ctx.expand(text)!r}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was called with "(?P<text>.*)"'))
def _called_with(ctx, name, text):
    calls = ctx.stub_calls(name)
    assert any(text in c for c in calls), f"{name} was never called with {text!r}; calls: {calls}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was not called with "(?P<text>.*)"'))
def _not_called_with(ctx, name, text):
    calls = ctx.stub_calls(name)
    assert not any(text in c for c in calls), f"{name} was called with {text!r}; calls: {calls}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was not called'))
def _not_called(ctx, name):
    assert_that(ctx.stub_calls(name), equal_to([]))


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was called (?P<n>\d+) times'))
def _called_n(ctx, name, n):
    assert_that(len(ctx.stub_calls(name)), equal_to(int(n)))


@then(parsers.re(r"its (?P<mode>tokens|texts) are (?P<want>\[.*\])"))
def _scanned(ctx, mode, want):
    assert_that(scanned(ctx, mode), equal_to(json.loads(want)))

