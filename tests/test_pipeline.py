"""The document every guard reads (languette/document.py). Its promises on
every scenario in features/ (parsed once, any order, pinned I/O) are checked
as each one runs: tests/pipeline_checks.py."""

import json
import os

import pytest

from languette import scan
from languette.document import Document
from pipeline_checks import PIN_KINDS, PINS


def doc(command):
    return Document({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/"}, {})


def test_a_document_is_read_only():
    d = doc("ls")
    for name in ("command", "payload", "anything"):
        with pytest.raises(AttributeError):
            setattr(d, name, "x")
    with pytest.raises(AttributeError):
        del d.command
    assert isinstance(d.texts(), tuple)


def test_each_text_is_scanned_once_whoever_asks(monkeypatch):
    made = []
    real = scan.Scan
    monkeypatch.setattr(scan, "Scan", lambda text: made.append(text) or real(text))
    d = doc('sh -c "rm -rf x" | tee y')
    for _ in range(3):
        for t, _nested in d.texts():
            assert d.scan(t) is d.scan(t)
        d.texts(scan.PROSE | {"pkill"})
    assert sorted(made) == sorted(set(made)) and len(made) == 2


def test_trailing_newlines_read_as_one():
    assert doc("ls\n\n\n").texts() == doc("ls").texts()
    assert doc("ls\n").stripped() == "ls\n"
    # A continuation that ends the command is read as the shell runs it: one
    # word, no empty line after it. Before the document, a guard that added a
    # newline to the command read a trailing separator too.
    d = doc("foo \\\n")
    assert d.texts() == doc("foo \\\n\n").texts()
    s = d.scan(d.texts()[0][0])
    assert s.w == ["foo"] and list(s.segments()) == [(0, 0)]


@pytest.mark.parametrize("command", ["echo 'open", "x" * (scan.LENGTH_MAX + 1)])
def test_a_refusal_is_kept(monkeypatch, command):
    d = doc(command)
    e = d.refusal
    assert isinstance(e, scan.Unparseable)
    monkeypatch.setattr(scan, "parse", lambda *a, **kw: pytest.fail("the ladder ran again"))
    assert d.refusal is e


def test_a_crash_is_kept_and_raised_on_every_read(monkeypatch):
    runs = []

    def boom(text, words=False):
        runs.append(text)
        raise RuntimeError("boom")
    monkeypatch.setattr(scan, "parse", boom)
    d = doc("echo hi")
    for _ in range(2):
        with pytest.raises(RuntimeError, match="boom"):
            d.refusal
    assert runs == ["echo hi"]


def test_no_bash_command_reads_as_well_formed():
    d = Document({"tool_name": "Edit", "tool_input": {"file_path": "/x"}, "cwd": "/"}, {})
    assert d.command is None and d.refusal is None


def test_the_pins_are_counts_of_programs_and_github_calls():
    pins = json.loads(PINS.read_text())
    assert list(pins) == sorted(pins)
    bad = {k: v for k, v in pins.items()
           if not v or any(kind not in PIN_KINDS or not isinstance(n, int) or n < 1 for kind, n in v.items())}
    assert not bad, f"{bad}: rewrite with LANGUETTE_PIN_IO=update"
    assert all(k.startswith("tests/test_features.py::") for k in pins), os.linesep.join(pins)
