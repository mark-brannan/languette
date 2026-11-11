"""languette/run.py where a scenario cannot reach: the entry point run bare, as a
hand-installed hook runs it with no hooks.json wrapper to turn a traceback into a
deny, a spend that would deny with no reason, and the terms file a session start writes."""

import json
import os
import subprocess
import sys

import pytest
from paths import ROOT

from languette import terms
from languette.verdict import Act, spend
from languette.world import World

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


def test_the_terms_init_writes_a_private_file_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "terms" / "redacted.tsv"
    World({"HOME": str(tmp_path), terms.KINDS["redacted"][3]: str(path)}, {}).act(Act("terms-init"))
    assert (os.listdir(path.parent), path.stat().st_mode & 0o777) == (["redacted.tsv"], 0o600)
    assert path.read_text(encoding="utf-8").startswith(terms.header("redacted"))
