"""run.py fails closed before it can judge anything: on a Python older than 3.11,
and when a guard's module will not import. Each answers with a deny and exits 0."""

import json
import shutil
import subprocess
import sys

from paths import ROOT

PAYLOAD = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
                      "cwd": "/var/tmp", "session_id": "s"})


def _decision(args, tmp_path):
    done = subprocess.run([sys.executable, *args], input=PAYLOAD, capture_output=True, text=True,
                          cwd=tmp_path, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_a_guard_that_fails_to_import_is_a_deny(tmp_path):
    shutil.copytree(ROOT / "languette", tmp_path / "languette", ignore=shutil.ignore_patterns("__pycache__"))
    with open(tmp_path / "languette/rules/guard_sudo.py", "a") as f:
        f.write("\n\nraise RuntimeError('boom')\n")
    assert _decision([str(tmp_path / "languette/run.py")], tmp_path) == "deny"


def test_python_older_than_3_11_is_a_deny(tmp_path):
    script = tmp_path / "old_python.py"
    script.write_text("import runpy, sys\n"
                      "sys.version_info = (3, 10, 0)\n"
                      f"runpy.run_path({str(ROOT / 'languette/run.py')!r}, run_name='__main__')\n")
    assert _decision([str(script)], tmp_path) == "deny"
