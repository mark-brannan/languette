"""Spending an approval is atomic: parallel hooks cannot both pass on one click."""

import json
from concurrent.futures import ThreadPoolExecutor

from languette.world import World

ASK = {"type": "assistant", "message": {"role": "assistant", "content": [{
    "type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion",
    "input": {"questions": [{"question": "Run it?", "options": [{"label": "Run e2e"}]}]}}]}}
YES = {"type": "user", "message": {"role": "user", "content": [{
    "type": "tool_result", "tool_use_id": "toolu_A",
    "content": 'User has answered your questions: "Run it?"="Run e2e". Done.'}]}}


def test_one_approval_pays_for_one_of_many_parallel_runs(tmp_path):
    tp = tmp_path / "t.jsonl"
    tp.write_text(json.dumps(ASK) + "\n" + json.dumps(YES) + "\n")
    payload = {"transcript_path": str(tp)}
    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda _: World({}, payload).spend({"Run e2e": 1}), range(64)))
    assert results.count(True) == 1
    assert (tmp_path / "t.jsonl.languette-ask").read_text() == "toolu_A\n"


def test_nothing_is_spent_when_one_label_is_short(tmp_path):
    tp = tmp_path / "t.jsonl"
    tp.write_text(json.dumps(ASK) + "\n" + json.dumps(YES) + "\n")
    assert World({}, {"transcript_path": str(tp)}).spend({"Run e2e": 1, "Run other": 1}) is False
    assert not (tmp_path / "t.jsonl.languette-ask").read_text()
