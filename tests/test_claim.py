"""A click pays for one run: spending is atomic, recorded against the tool call,
and comes back when the transcript shows the call never ran."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from languette import run
from languette.verdict import Need
from languette.world import World

ASK = {"type": "assistant", "message": {"role": "assistant", "content": [{
    "type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion",
    "input": {"questions": [{"question": "Run it?", "options": [{"label": "Run e2e"}]}]}}]}}
YES = {"type": "user", "message": {"role": "user", "content": [{
    "type": "tool_result", "tool_use_id": "toolu_A",
    "content": 'User has answered your questions: "Run it?"="Run e2e". Done.'}]}}


def _transcript(tmp_path, *recs):
    tp = tmp_path / "t.jsonl"
    tp.write_text("".join(json.dumps(r) + "\n" for r in (ASK, YES, *recs)))
    return tp


def _claim(tp, call, wants=None):
    return World({}, {"transcript_path": str(tp), "tool_use_id": call}).answer(Need("claim", wants or {"Run e2e": 1}))


def _result(call, content, is_error=True, tur=None):
    rec = {"type": "user", "message": {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": call, "content": content, "is_error": is_error}]}}
    return {**rec, "toolUseResult": tur} if tur is not None else rec


def test_one_approval_pays_for_one_of_many_parallel_runs(tmp_path):
    tp = _transcript(tmp_path)
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda n: _claim(tp, f"toolu_B{n}")[1], range(64)))
    assert results.count(True) == 1


def test_nothing_is_spent_when_one_label_is_short(tmp_path):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1", {"Run e2e": 1, "Run other": 1}) == ({"Run e2e": ["toolu_A"], "Run other": []}, False)
    assert not (tmp_path / "t.jsonl.languette-ask").read_text()


def test_the_spend_names_the_call(tmp_path):
    _claim(_transcript(tmp_path), "toolu_B1")
    rec = json.loads((tmp_path / "t.jsonl.languette-ask").read_text())
    assert (rec["label"], rec["approval"], rec["call"]) == ("Run e2e", "toolu_A", "toolu_B1")


def test_the_same_call_claims_once(tmp_path):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1")[1] and _claim(tp, "toolu_B1")[1]
    assert not _claim(tp, "toolu_B2")[1]


@pytest.mark.parametrize("result", [
    _result("toolu_B1", "The user doesn't want to proceed with this tool use. The tool use was rejected.",
            tur="User rejected tool use"),
    _result("toolu_B1", "PreToolUse:Bash hook error: `dd` is blocked."),
    _result("toolu_B1", "guard-disks: dd onto /dev/sda overwrites a whole disk."),
    _result("toolu_B1", "Permission for this action was denied by the Claude Code auto mode classifier."),
], ids=["declined", "hook-error", "guard-deny", "classifier"])
def test_a_call_that_never_ran_gives_its_click_back(tmp_path, result):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1")[1]
    with tp.open("a") as f:
        f.write(json.dumps(result) + "\n")
    assert _claim(tp, "toolu_B2")[1]


@pytest.mark.parametrize("result", [
    _result("toolu_B1", "Exit code 1\nnpm ERR! e2e failed"),
    _result("toolu_B1", "ok", is_error=False),
    _result("toolu_B1", "some hook's own words, unrecognised"),
], ids=["failed", "succeeded", "unknown-refusal"])
def test_a_call_that_ran_or_may_have_keeps_its_click(tmp_path, result):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1")[1]
    with tp.open("a") as f:
        f.write(json.dumps(result) + "\n")
    assert not _claim(tp, "toolu_B2")[1]


def test_a_spend_from_before_calls_were_recorded_stays_spent(tmp_path):
    tp = _transcript(tmp_path)
    (tmp_path / "t.jsonl.languette-ask").write_text("toolu_A\n")
    assert not _claim(tp, "toolu_B1")[1]


def test_two_guards_wanting_one_label_for_one_command_need_one_click(tmp_path, monkeypatch):
    tp = _transcript(tmp_path)

    def check(payload, env):
        approved, spent = yield Need("claim", {"Run e2e": 1})
        return None if spent else {"permissionDecision": "deny", "permissionDecisionReason": "no click"}

    guards = tuple(SimpleNamespace(NAME=f"g{i}", check=check) for i in range(2))
    monkeypatch.setattr(run, "GUARDS", (("PreToolUse", re.compile(r"Bash\Z"), guards),))
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm run e2e"},
               "cwd": "/", "transcript_path": str(tp), "tool_use_id": "toolu_B1"}
    assert run.respond(json.dumps(payload), {}) == ""
