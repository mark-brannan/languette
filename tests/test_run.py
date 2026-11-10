"""languette/run.py where a scenario cannot reach: the entry point run bare, as a
hand-installed hook runs it with no hooks.json wrapper to turn a traceback into a
deny, and a spend that would deny with no reason."""

import json
import os
import subprocess
import sys

import pytest
from paths import ROOT

from languette.verdict import spend

HOOK = [sys.executable, "-I", str(ROOT / "languette" / "run.py")]


@pytest.mark.parametrize("stdin", ["[" * 100_000, "not json", "[1]"], ids=["deeply nested", "not json", "not an object"])
def test_an_unreadable_payload_is_a_deny_from_run_py_itself(stdin):
    r = subprocess.run(HOOK, input=stdin, capture_output=True, text=True, timeout=10,
                       env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})
    assert (r.returncode, r.stderr) == (0, "")
    hso = json.loads(r.stdout)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny" and "unreadable hook payload" in hso["permissionDecisionReason"]


def test_a_spend_other_than_approvals_names_its_lost_reason():
    with pytest.raises(ValueError):
        spend("door", "take", "s", "c")
    assert spend("door", "take", "s", "c", lost="why")["lost"] == "why"
    assert "lost" not in spend("approvals", {"x": 1})
