"""End-to-end smoke test of the parser ladder's promise to a user: if the
preferred parser is not installed, languette falls back to one you have, and a
command that does not parse is still denied, naming the parser that read it.

Each environment is a PATH holding exactly the tools named, nothing else. The
hook run is guard-unparsable's own command string from hooks/hooks.json, under
/bin/sh, as Claude Code would run it. A row the ladder cannot keep yet is a
strict xfail: CI stays green, and goes red the day a fix lands, so the marker
comes off with the fix.

The pip rows take their interpreter from a venv named by an environment
variable (CI's smoke job builds both); unset, they skip locally and fail
under CI.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from languette import scan  # noqa: E402

BAD = "echo 'unclosed"
GOOD = "echo ok"

# id -> (tools besides python3, env var naming the python3 to use, the rung the deny names, xfail reason)
ENVS = {
    "shfmt": (("shfmt", "bash"), None, "shfmt", None),
    "bash -n": (("bash",), None, "bash -n", None),
    "lexer only": ((), None, "(?:awk|lexer)",
                   "with no shfmt and no bash, guard-unparsable has no reader that refuses: the built-in "
                   "lexer's reading denies nothing, so the command passes silently"),
    "bashlex": ((), "LANGUETTE_SMOKE_BASHLEX_PY", "bashlex",
                "the pip rung is an empty slot (#4): bashlex is installed and never asked"),
    "tree-sitter-bash": ((), "LANGUETTE_SMOKE_TREESITTER_PY", "tree-sitter-bash",
                         "the pip rung is an empty slot (#4): tree-sitter-bash is installed and never asked"),
}


def hook_command():
    """guard-unparsable's command string, read from hooks.json, never copied."""
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    found = [h["command"] for entries in hooks.values() for e in entries for h in e.get("hooks", ())
             if "--guard guard-unparsable" in h.get("command", "")]
    assert len(found) == 1, f"expected one guard-unparsable hook in hooks.json, found {len(found)}"
    return found[0]


def python_for(var):
    """The interpreter an environment's python3 runs: this one, or the venv's named by var."""
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
    wrapper.write_text(f'#!/bin/sh\nexec "{python}" "$@"\n')
    wrapper.chmod(0o755)
    for t in tools:
        src = scan.shfmt() if t == "shfmt" else shutil.which(t)
        assert src, f"{t} is not installed here"
        (d / t).symlink_to(src)
    return d


def run_hook(path_dir, home, command):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    env = {"PATH": str(path_dir), "CLAUDE_PLUGIN_ROOT": str(ROOT), "HOME": str(home)}
    r = subprocess.run(["/bin/sh", "-c", hook_command()], input=json.dumps(payload), capture_output=True,
                       text=True, env=env, timeout=20)
    assert r.returncode == 0, f"hook exited {r.returncode}: {r.stderr}"
    return json.loads(r.stdout) if r.stdout.strip() else None


def params():
    for name, (_, _, _, xfail) in ENVS.items():
        marks = [pytest.mark.xfail(strict=True, reason=xfail)] if xfail else []
        yield pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize("env", list(params()))
def test_bad_command_is_denied_naming_its_parser(env, tmp_path):
    tools, var, rung, _ = ENVS[env]
    out = run_hook(make_path(tmp_path, tools, python_for(var)), tmp_path, BAD)
    assert out is not None, "silent: the unparsable command would have run"
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny", hso
    reason = hso["permissionDecisionReason"]
    assert re.search(r"\(" + rung + r"[: ]", reason), f"the deny does not name {rung!r} as its reader: {reason}"


@pytest.mark.parametrize("env", list(ENVS))
def test_good_command_is_silent(env, tmp_path):
    tools, var, _, _ = ENVS[env]
    assert run_hook(make_path(tmp_path, tools, python_for(var)), tmp_path, GOOD) is None
