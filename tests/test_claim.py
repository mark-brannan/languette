"""A click pays for one run: a guard only reads it, the runner spends it once
after the verdict, atomically, recorded against the tool call, and it comes
back when the transcript shows the call never ran."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from languette import run
from languette.verdict import Need, approve, deny
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
    """(what the guard reads, whether the runner's spend went through)."""
    w = World({}, {"transcript_path": str(tp), "tool_use_id": call})
    wants = wants or {"Run e2e": 1}
    return w.answer(Need("approvals", wants)), w.spend("approvals", wants)


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


def test_reading_the_approvals_writes_nothing(tmp_path):
    tp = _transcript(tmp_path)
    w = World({}, {"transcript_path": str(tp), "tool_use_id": "toolu_B1"})
    assert w.answer(Need("approvals", {"Run e2e": 1})) == {"Run e2e": ["toolu_A"]}
    assert not (tmp_path / "t.jsonl.languette-ask").exists()


def _asking(label):
    def check(doc):
        _, done = yield from approve({label: 1}, lambda e: f"unreadable: {e}")
        return done[0] if done else deny("no click")
    return check


def _respond(tp, monkeypatch, *checks, call="toolu_B1"):
    guards = tuple(SimpleNamespace(NAME=f"g{i}", check=c) for i, c in enumerate(checks))
    monkeypatch.setattr(run, "GUARDS", (("PreToolUse", re.compile(r"Bash\Z"), guards),))
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm run e2e"},
               "cwd": "/", "transcript_path": str(tp), "tool_use_id": call}
    return run.respond(json.dumps(payload), {})


def _spent(tmp_path):
    f = tmp_path / "t.jsonl.languette-ask"
    return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []


def test_two_guards_wanting_one_label_for_one_command_need_one_click(tmp_path, monkeypatch):
    tp = _transcript(tmp_path)
    assert _respond(tp, monkeypatch, _asking("Run e2e"), _asking("Run e2e")) == ""
    assert [r["approval"] for r in _spent(tmp_path)] == ["toolu_A"]


def test_two_labels_answered_in_one_question_are_one_click(tmp_path, monkeypatch):
    both = {"type": "assistant", "message": {"role": "assistant", "content": [{
        "type": "tool_use", "id": "toolu_C", "name": "AskUserQuestion",
        "input": {"questions": [{"question": "Run it?", "options": [{"label": "Run e2e"}]},
                                {"question": "Skip hooks?", "options": [{"label": "Skip hooks once"}]}]}}]}}
    yes = {"type": "user", "message": {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": "toolu_C", "content": "answered"}]},
        "toolUseResult": {"answers": {"Run it?": "Run e2e", "Skip hooks?": "Skip hooks once"}}}
    tp = tmp_path / "t.jsonl"
    tp.write_text(json.dumps(both) + "\n" + json.dumps(yes) + "\n")
    assert _respond(tp, monkeypatch, _asking("Run e2e"), _asking("Skip hooks once")) == ""
    assert sorted((r["label"], r["approval"], r["call"]) for r in _spent(tmp_path)) == [
        ("Run e2e", "toolu_C", "toolu_B1"), ("Skip hooks once", "toolu_C", "toolu_B1")]


def test_a_deny_from_another_guard_spends_nothing(tmp_path, monkeypatch):
    tp = _transcript(tmp_path)
    out = _respond(tp, monkeypatch, _asking("Run e2e"), lambda doc: deny("not this"))
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _spent(tmp_path) == []


def test_a_click_spent_since_the_guard_looked_is_a_deny(tmp_path, monkeypatch):
    tp = _transcript(tmp_path)

    def racer(doc):
        _claim(tp, "toolu_OTHER")              # a parallel call spends the click between read and spend
        return None

    out = _respond(tp, monkeypatch, _asking("Run e2e"), racer)
    assert "another call spent the user's approval" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
