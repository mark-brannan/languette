"""A click pays for one run: a guard only reads it, the runner checks it again
once after the verdict, and the transcript alone says who spent it: the first
later call that wanted its label and did not show it never ran. Nothing is
written beside the transcript."""

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


def _use(call, ts=None):
    """The tool_use Claude Code writes for a Bash call before its hooks run."""
    rec = {"type": "assistant", "message": {"role": "assistant", "content": [{
        "type": "tool_use", "id": call, "name": "Bash", "input": {"command": "npm run e2e"}}]}}
    return {**rec, "timestamp": ts} if ts else rec


def _append(tp, *recs):
    with tp.open("a") as f:
        f.writelines(json.dumps(r) + "\n" for r in recs)


def _world(tp, call, wants=None):
    """A World for `call` whose past calls each want `wants`, as a runner would replay them."""
    w = World({}, {"transcript_path": str(tp), "tool_use_id": call})
    w.wants_of = lambda payload, door: (dict(wants or {"Run e2e": 1}), False)
    return w


def _claim(tp, call, wants=None):
    """(what the guard reads, whether the runner's spend went through)."""
    wants = wants or {"Run e2e": 1}
    w = _world(tp, call)
    return w.answer(Need("approvals", wants)), w.spend("approvals", wants)


def _result(call, content, is_error=True, tur=None):
    rec = {"type": "user", "message": {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": call, "content": content, "is_error": is_error}]}}
    return {**rec, "toolUseResult": tur} if tur is not None else rec


def test_one_approval_pays_for_the_first_of_many_parallel_runs(tmp_path):
    tp = _transcript(tmp_path, *(_use(f"toolu_B{n:02}", f"2026-11-10T09:00:{n:02}.000Z") for n in range(48)))
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda n: _claim(tp, f"toolu_B{n:02}")[1], range(48)))
    assert results == [True] + [False] * 47


def test_subagent_calls_spend_from_their_own_files_in_time_order(tmp_path):
    tp = _transcript(tmp_path, _use("toolu_B2", "2026-11-10T09:00:02.000Z"))
    sub = tmp_path / "t" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x.jsonl").write_text(json.dumps(_use("toolu_B1", "2026-11-10T09:00:01.000Z")) + "\n")
    assert _claim(tp, "toolu_B1")[1]
    assert not _claim(tp, "toolu_B2")[1]


def test_nothing_is_spent_when_one_label_is_short(tmp_path):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1", {"Run e2e": 1, "Run other": 1}) == ({"Run e2e": ["toolu_A"], "Run other": []}, False)


def test_the_transcript_names_the_call_that_spent_it(tmp_path):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    assert _world(tp, "toolu_B2")._replay({"Run e2e"}) == ({"Run e2e": []}, {"toolu_A": "toolu_B1"})


def test_the_same_call_claims_once(tmp_path):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    assert _claim(tp, "toolu_B1")[1] and _claim(tp, "toolu_B1")[1]
    assert not _claim(tp, "toolu_B2")[1]


def test_a_yes_pays_only_for_calls_after_it(tmp_path):
    tp = tmp_path / "t.jsonl"
    tp.write_text("".join(json.dumps(r) + "\n" for r in (_use("toolu_B0"), ASK, YES)))
    assert _claim(tp, "toolu_B1")[1]


@pytest.mark.parametrize("result", [
    _result("toolu_B1", "The user doesn't want to proceed with this tool use. The tool use was rejected.",
            tur="User rejected tool use"),
    _result("toolu_B1", "PreToolUse:Bash hook error: `dd` is blocked."),
    _result("toolu_B1", "guard-disks: dd onto /dev/sda overwrites a whole disk."),
    _result("toolu_B1", "Permission for this action was denied by the Claude Code auto mode classifier."),
], ids=["declined", "hook-error", "guard-deny", "classifier"])
def test_a_call_that_never_ran_gives_its_click_back(tmp_path, result):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    assert _claim(tp, "toolu_B1")[1]
    _append(tp, result)
    assert _claim(tp, "toolu_B2")[1]


@pytest.mark.parametrize("result", [
    None,
    _result("toolu_B1", "Exit code 1\nnpm ERR! e2e failed"),
    _result("toolu_B1", "ok", is_error=False),
    _result("toolu_B1", "some hook's own words, unrecognised"),
], ids=["in-flight", "failed", "succeeded", "unknown-refusal"])
def test_a_call_that_ran_or_may_have_keeps_its_click(tmp_path, result):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    assert _claim(tp, "toolu_B1")[1]
    if result:
        _append(tp, result)
    assert not _claim(tp, "toolu_B2")[1]


def test_neither_reading_nor_spending_writes_a_file(tmp_path):
    tp = _transcript(tmp_path)
    assert _claim(tp, "toolu_B1") == ({"Run e2e": ["toolu_A"]}, True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["t.jsonl"]


def _asking(label):
    def check(doc):
        _, done = yield from approve({label: 1}, lambda e: f"unreadable: {e}")
        return done[0] if done else deny("no click")
    return check


def _guards(monkeypatch, *checks):
    guards = tuple(SimpleNamespace(NAME=f"g{i}", check=c) for i, c in enumerate(checks))
    monkeypatch.setattr(run, "GUARDS", (("PreToolUse", re.compile(r"Bash\Z"), guards),))


def _respond(tp, monkeypatch, *checks, call="toolu_B1"):
    _guards(monkeypatch, *checks)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "npm run e2e"},
               "cwd": "/", "transcript_path": str(tp), "tool_use_id": call}
    return run.respond(json.dumps(payload), {})


def _spent(tp, *labels):
    """{yes id: call}, as the runner's replay gives them for a call after every one so far."""
    w = World({}, {"transcript_path": str(tp), "tool_use_id": "toolu_after", "cwd": "/"})
    w.wants_of = run._past_wants(w, {})
    return w._replay(labels)[1]


def test_two_guards_wanting_one_label_for_one_command_need_one_click(tmp_path, monkeypatch):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    assert _respond(tp, monkeypatch, _asking("Run e2e"), _asking("Run e2e")) == ""
    assert _spent(tp, "Run e2e") == {"toolu_A": "toolu_B1"}


def test_two_labels_answered_in_one_question_are_one_click(tmp_path, monkeypatch):
    both = {"type": "assistant", "message": {"role": "assistant", "content": [{
        "type": "tool_use", "id": "toolu_C", "name": "AskUserQuestion",
        "input": {"questions": [{"question": "Run it?", "options": [{"label": "Run e2e"}]},
                                {"question": "Skip hooks?", "options": [{"label": "Skip hooks once"}]}]}}]}}
    yes = {"type": "user", "message": {"role": "user", "content": [{
        "type": "tool_result", "tool_use_id": "toolu_C", "content": "answered"}]},
        "toolUseResult": {"answers": {"Run it?": "Run e2e", "Skip hooks?": "Skip hooks once"}}}
    tp = tmp_path / "t.jsonl"
    tp.write_text("".join(json.dumps(r) + "\n" for r in (both, yes, _use("toolu_B1"))))
    assert _respond(tp, monkeypatch, _asking("Run e2e"), _asking("Skip hooks once")) == ""
    assert _spent(tp, "Run e2e", "Skip hooks once") == {"toolu_C": "toolu_B1"}


def test_a_deny_from_another_guard_spends_nothing(tmp_path, monkeypatch):
    tp = _transcript(tmp_path, _use("toolu_B1"))
    out = _respond(tp, monkeypatch, _asking("Run e2e"), lambda doc: deny("guard-disks: not this"))
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    _append(tp, _result("toolu_B1", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]))
    assert _spent(tp, "Run e2e") == {}


def test_a_click_spent_since_the_guard_looked_is_a_deny(tmp_path, monkeypatch):
    tp = _transcript(tmp_path)

    def racer(doc):
        if doc.payload.get("tool_use_id") == "toolu_B1":
            _append(tp, _use("toolu_OTHER"))   # a parallel call, ahead in the transcript, lands after the read
        return None

    out = _respond(tp, monkeypatch, _asking("Run e2e"), racer)
    assert "another call spent the user's approval" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]


def _spending(world, kind="approvals", *args):
    findings = [("g0", {"spend": [[kind, *(args or ({"Run e2e": 1},))]]}, None)]
    return run._spend(world, "PreToolUse", findings, {})


def _broken(kind, *args):
    raise OSError(30, "Read-only file system")


def test_a_spend_that_cannot_be_recorded_is_a_deny():
    out = _spending(SimpleNamespace(spend=_broken))
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"].startswith("languette: cannot spend")
    assert "Read-only file system" in out["permissionDecisionReason"]


def test_a_lost_door_is_denied_with_the_guards_reason():
    findings = [("g0", {"spend": [["door", "claim", "S1", "toolu_B1"]], "lost": "g0: ask for the yes"}, None)]
    out = run._spend(SimpleNamespace(spend=lambda kind, *args: False), "PreToolUse", findings, {})
    assert out == deny("g0: ask for the yes")
