"""What a guard reads is bounded: a file past paths.MAX_READ is refused, or, where the
guard wants only its end, read from there; an unclosed heredoc holds the text once."""

import json
import os
import tracemalloc
import types

import pytest

from harness import answered
from languette import issue_writes, paths, untrusted_reads
from languette.document import Document
from languette.quoting import _heredocs
from languette.verdict import Need, Refuse
from languette.world import World


def test_a_json_file_past_the_cap_is_refused_and_names_why(tmp_path):
    p = tmp_path / "big.json"
    p.write_text(json.dumps({"x": "a" * paths.MAX_READ}))
    with pytest.raises(Refuse, match=f"is over {paths.MAX_READ} bytes"):
        answered(paths.read_json(str(p)), World({}, {}).answer)


def test_a_tail_read_past_the_cap_keeps_the_whole_lines_of_its_end(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("x" * 100 + "\n" + "first\n" + "y" * 40 + "\n" + "last\n")
    read = lambda limit: World({}, {}).answer(Need("read", str(p), limit, True))
    assert read(52) == "first\n" + "y" * 40 + "\n" + "last\n"   # a cut at a line's start keeps it
    assert read(50) == "y" * 40 + "\n" + "last\n"               # a cut mid-line drops that line


def test_a_tail_read_under_the_cap_is_the_whole_file(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("one\ntwo\n")
    assert World({}, {}).answer(Need("read", str(p), paths.MAX_READ, True)) == "one\ntwo\n"


def test_unclosed_heredocs_hold_the_text_once():
    text = "cat <<EOF\n" * 6500                   # about 64 KB
    was = tracemalloc.is_tracing()
    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]    # a tracer already on counts from its own start
    try:
        stripped, docs = _heredocs(text)
        peak = tracemalloc.get_traced_memory()[1] - base
    finally:
        if not was:
            tracemalloc.stop()
    assert peak < 50 * len(text)                 # linear: a body per opener held over 3000 times this
    assert docs == [(text[len("cat <<EOF\n"):], False)]   # the first takes the rest, openers and all
    assert stripped == "cat  HEREDOC \n" + text[len("cat <<EOF\n"):]


def test_nothing_below_an_unclosed_heredoc_is_stripped():
    stripped, docs = _heredocs("cat <<A\nbash <<B\nrm -rf /\nB\n")
    assert docs == [("bash <<B\nrm -rf /\nB\n", False)]
    assert "rm -rf /" in stripped                 # kept as commands


@pytest.mark.parametrize("opener", ["cat <<END-A", "cat <<END.A"])
def test_a_body_the_shell_runs_is_not_hidden_below_an_opener_the_parser_cannot_close(opener):
    # bash closes the first heredoc at its own delimiter and then runs the push: `<<EOF` in $(( )) is a shift.
    # The parser reads the delimiter as END and never closes it, so it must not strip the "body" below.
    closer = opener.split("<<")[1]
    text = opener + "\nhello\n" + closer + "\necho $((1 <<EOF))\ngit push --force origin main\nEOF\n"
    assert "git push --force origin main" in _heredocs(text)[0]


def test_a_second_opener_on_the_last_line_adds_no_argument():
    assert _heredocs("cat <<A <<B\nx\nA")[0] == "cat  HEREDOC   HEREDOC \n"


def test_the_team_config_read_carries_the_cap():
    doc = Document({"session_id": "abcdef012345", "tool_input": {"to": "someone"}}, {"HOME": "/home/u"})
    seen, _ = answered(untrusted_reads.door(doc, None, {"to": "someone"}), lambda need: {})
    assert [n.args[1:] for n in seen if n.kind == "read"] == [(paths.MAX_READ,)]


def test_the_transcript_read_carries_the_cap_and_asks_for_the_tail():
    payload = {"tool_use_id": "t1", "transcript_path": "/p/t.jsonl"}
    seen, _ = answered(issue_writes._door(payload, "s"), lambda need: "t1" if need.kind == "door" else "")
    assert [n.args[1:] for n in seen if n.kind == "read"] == [(paths.MAX_READ, True)]


def test_a_tail_read_of_a_file_that_grew_past_the_cap_after_the_stat_is_not_refused(tmp_path, monkeypatch):
    p = tmp_path / "t.jsonl"
    p.write_text("x" * 100 + "\nlast\n")
    real = os.fstat
    with monkeypatch.context() as m:               # the stat saw 5 bytes; the file has grown since
        m.setattr(os, "fstat", lambda fd: types.SimpleNamespace(st_mode=real(fd).st_mode, st_size=5))
        assert World({}, {}).answer(Need("read", str(p), 20, True)) == "last\n"
