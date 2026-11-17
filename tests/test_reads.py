"""What a guard reads is bounded: a file past paths.MAX_READ is refused, or, where the
guard wants only its end, read from there; an unclosed heredoc holds the text once."""

import json
import tracemalloc

import pytest

from harness import answered
from languette import paths
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
    tracemalloc.start()
    try:
        stripped, docs = _heredocs(text)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 50 * len(text)                 # linear: a body per opener held over 3000 times this
    assert docs == [(text[len("cat <<EOF\n"):], False)]   # the first takes the rest, openers and all
    assert stripped == "cat  HEREDOC \n" + text[len("cat <<EOF\n"):]


def test_a_closed_heredoc_after_an_unclosed_one_is_part_of_its_body():
    stripped, docs = _heredocs("cat <<A\nbash <<B\nrm -rf /\nB\n")
    assert docs == [("bash <<B\nrm -rf /\nB\n", False)]
    assert "rm -rf /" in stripped                 # kept as commands
