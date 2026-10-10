"""Steps for features/smoke.feature, and its only runner: the name keeps it out
of the default `pytest` run, and CI's smoke job names this file, after building
the pip parsers' venvs."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from languette import scan  # noqa: E402

scenarios("smoke.feature")

# machine -> (tools besides python3, env var naming the python3 to use, what
# that python3 must import).
MACHINES = {
    "shfmt and bash": (("shfmt", "bash"), None, None),
    "no shfmt but bash": (("bash",), None, None),
    "neither shfmt nor bash": ((), None, None),
    "no shfmt but bashlex": ((), "LANGUETTE_SMOKE_BASHLEX_PY", "bashlex"),
    "no shfmt but tree-sitter-bash": ((), "LANGUETTE_SMOKE_TREESITTER_PY", "tree_sitter, tree_sitter_bash"),
}


@pytest.fixture(autouse=True)
def known_gap(request):
    """A @known_gap Examples row is a strict xfail: green while the gap stands, red the day it closes."""
    if request.node.get_closest_marker("known_gap"):
        request.applymarker(pytest.mark.xfail(strict=True, raises=AssertionError,
                                                reason="a @known_gap row in features/smoke.feature"))


def hook_command():
    """require-well-formed's command string, read from hooks.json, never copied."""
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    found = [h["command"] for entries in hooks.values() for e in entries for h in e.get("hooks", ())
             if "--guard require-well-formed" in h.get("command", "")]
    assert len(found) == 1, f"expected one require-well-formed hook in hooks.json, found {len(found)}"
    return found[0]


def python_for(var):
    """The interpreter a machine's python3 runs: this one, or the venv's named by var."""
    if var is None:
        return sys.executable
    path = os.environ.get(var)
    if not path:
        if os.environ.get("CI"):
            pytest.fail(f"CI runs this row: set {var} to a venv's python")
        pytest.skip(f"{var} is unset: no venv to run this row")
    return path


def make_path(tmp_path, tools, python):
    """A directory holding python3 and exactly `tools`. python3 is an exec
    wrapper, not a symlink, so a venv's python still finds its pyvenv.cfg."""
    if "shfmt" in tools and not scan.shfmt():
        if os.environ.get("CI"):
            pytest.fail(f"CI runs this row: no shfmt >= {scan.SHFMT_MIN} on PATH")
        pytest.skip(f"no shfmt >= {scan.SHFMT_MIN} on PATH")
    d = tmp_path / "bin"
    d.mkdir()
    wrapper = d / "python3"
    wrapper.write_text(f'#!/bin/sh\nexec {shlex.quote(str(python))} "$@"\n')
    wrapper.chmod(0o755)
    for t in tools:
        src = scan.shfmt() if t == "shfmt" else shutil.which(t)
        assert src, f"{t} is not installed here"
        (d / t).symlink_to(src)
    return d


class Machine:
    path = home = out = code = None


@pytest.fixture
def machine():
    m = Machine()
    # Not under /tmp: guard-recursive-delete allows all of /tmp, so the doctor's `rm -rf ~` would pass.
    m.home = Path(tempfile.mkdtemp(prefix="languette-smoke-home-", dir="/var/tmp"))
    yield m
    shutil.rmtree(m.home, ignore_errors=True)


@given(parsers.parse("a machine with {name}"))
def given_machine(machine, name, tmp_path):
    """The venv a pip machine names imports its parser through the PATH's
    python3, run as the hook runs it (-I), so its rows are red for the ladder's
    reason only. The deny scenario proves this outside any xfail."""
    assert name in MACHINES, f"test setup: no machine {name!r} in smoke_steps.MACHINES"
    tools, var, imports = MACHINES[name]
    d = make_path(tmp_path, tools, python_for(var))
    if imports:
        r = subprocess.run([str(d / "python3"), "-I", "-c", f"import {imports}"], capture_output=True, text=True,
                           env={"PATH": str(d), "HOME": str(tmp_path)}, timeout=20)
        assert r.returncode == 0, f"{var} cannot import {imports}: {r.stderr}"
    machine.path = d


def stub(machine, name, body):
    f = machine.path / name
    f.write_text(f"#!/bin/sh\n{body}\n")
    f.chmod(0o755)


@given("languette is installed as a plugin")
def given_installed(machine):
    """Claude Code on this machine lists languette at user scope, from this checkout, with the
    options a user who wants every guard sets."""
    entry = {"id": "languette@languette", "version": "cd31356ad5db", "scope": "user", "enabled": True,
             "installPath": str(ROOT)}
    stub(machine, "claude", f'[ "$*" = "plugin list --json" ] || exit 2\nprintf %s {shlex.quote(json.dumps([entry]))}')
    (machine.home / ".claude").mkdir()
    (machine.home / ".claude/settings.json").write_text(
        json.dumps({"pluginConfigs": {"languette@languette": {"options": {"guard_worktrees": True}}}}))


@given(parsers.re(r"gh is (?P<state>signed in|signed out|not installed)"))
def given_gh(machine, state):
    if state != "not installed":
        stub(machine, "gh", f'[ "$1 $2" = "auth status" ] && exit {0 if state == "signed in" else 1}\nexit 2')


@when(parsers.re(r"the agent runs `(?P<command>.*)` there"))
def run_hook(machine, command):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command},
               "cwd": str(machine.home)}
    env = {"PATH": str(machine.path), "CLAUDE_PLUGIN_ROOT": str(ROOT), "HOME": str(machine.home)}
    r = subprocess.run(["/bin/sh", "-c", hook_command()], input=json.dumps(payload), capture_output=True,
                       text=True, env=env, timeout=20)
    assert r.returncode == 0, f"hook exited {r.returncode}: {r.stderr}"
    machine.out = json.loads(r.stdout) if r.stdout.strip() else None


@when("the doctor runs on that machine")
def run_doctor(machine):
    """`languette doctor` in the machine's HOME under the same PATH, and nothing else on it."""
    env = {"PATH": str(machine.path), "HOME": str(machine.home), "PYTHONPATH": str(ROOT)}
    r = subprocess.run([str(machine.path / "python3"), "-m", "languette", "doctor"], capture_output=True, text=True,
                       env=env, cwd=machine.home, timeout=60)
    machine.out, machine.code = r.stdout + r.stderr, r.returncode


@then(parsers.re(r"the hook denies, read by (?P<reader>[^,]+)(?:, at (?P<at>.+))?"))
def denies(machine, reader, at):
    out = machine.out
    assert out is not None, "silent: the unparsable command would have run"
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny", hso
    reason = hso["permissionDecisionReason"]
    assert re.search(r"\(" + re.escape(reader) + r"[: ]", reason), f"the deny does not name {reader!r}: {reason}"
    if at:
        assert f", at {at})" in reason, f"the deny has no column {at!r}: {reason}"


@then("the hook is silent")
def silent(machine):
    assert machine.out is None, machine.out


@then(parsers.re(r'its "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) matching "(?P<pattern>.*)"'))
def row(machine, label, mark, pattern):
    out = machine.out
    rows = [m for m in (re.match(r"(\S+)\s+" + re.escape(label) + r"\s+(.*)$", ln) for ln in out.splitlines()) if m]
    assert len(rows) == 1, f"one {label!r} row in:\n{out}"
    got, text = rows[0].groups()
    assert (got, re.search(pattern, text) is not None) == (mark, True), f"{got} {text}\n{out}"


@then(parsers.parse("the doctor exits {code:d}"))
def exits(machine, code):
    assert machine.code == code, f"exit {machine.code}:\n{machine.out}"
