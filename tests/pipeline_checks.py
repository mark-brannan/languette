"""The guard pipeline's promises (docs/design/guard-pipeline.md), checked on
every in-process scenario in features/ as it runs, so a new row is covered
with no step of its own. Each run.respond call the scenario makes is watched:

  parsed once   no text is scanned (scan.Scan) twice in a call, and the
                parser ladder reads the command (scan.parse, every rung)
                at most once;
  any order     every guard wired for the call, run again in reverse order
                on one fresh document, comes to the same finding as each one
                the call ran: those get back the answers the world gave them,
                the rest only read the document ahead of them. The verdict is
                the same whatever the order;
  pinned I/O    the Needs that start a program (git, pr-list, run) or reach
                GitHub (gh-api), counted per scenario, match
                tests/io_counts.json, so one more git or network call per
                guard shows up there as a diff. The parser ladder's own runs
                are not counted: whether shfmt is there turns on the
                machine, and "parsed once" covers them.

After a change that means to add or drop such a call, regenerate the pins:

    LANGUETTE_PIN_IO=update python -m pytest tests/test_features.py

A scenario's pin is the same on every engine (the key drops the engine), and
one with no such Need has no entry. The @hook engine runs languette in a
subprocess and is not watched here.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from languette import run, scan
from languette.document import Document

PINS = Path(__file__).resolve().parent / "io_counts.json"
PIN_KINDS = ("git", "gh-api", "pr-list", "run")
_UPDATE = os.environ.get("LANGUETTE_PIN_IO") == "update"
_pinned = json.loads(PINS.read_text()) if PINS.exists() else {}
_seen = {}                                     # key -> {engine: counts}, under update
_collected = set()


def _key(item):
    """The scenario's node id without its engine, so every engine shares one pin."""
    cs = getattr(item, "callspec", None)
    engine = cs.params.get("engine") if cs else None
    if not cs or engine is None:
        return item.nodeid
    rest = [t for t in cs.id.split("-") if t != engine]
    base = item.nodeid[:item.nodeid.index("[")]
    return base + (f"[{'-'.join(rest)}]" if rest else "")


class _Recorded:
    """The runner's world for one guard: every answer it gives, kept in order."""

    def __init__(self, world, log, io):
        self.world, self.log, self.io = world, log, io

    def answer(self, need):
        if need.kind in PIN_KINDS:
            self.io[need.kind] = self.io.get(need.kind, 0) + 1
        try:
            got = self.world.answer(need)
        except Exception as e:  # noqa: BLE001 -- replayed as thrown
            self.log.append((need, None, e))
            raise
        self.log.append((need, got, None))
        return got


class _Replayed:
    """A world that gives one guard back, in order, what the real one gave it."""

    def __init__(self, log, strays):
        self.log, self.strays = list(log), strays

    def answer(self, need):
        if not self.log or self.log[0][0] != need:
            self.strays.append(f"asked {need!r}, where the first run asked {self.log[0][0] if self.log else None!r}")
            raise LookupError("not asked in the first run")
        _, got, err = self.log.pop(0)
        if err is not None:
            raise err
        return got


class _Refused:
    """The world for a guard the first run did not run: no fact can be had."""

    def answer(self, need):
        raise LookupError("not run in the first run")


def _replay(guards, finding):
    """Every guard wired for the call, in reverse order, on one fresh document:
    the ones that ran get back what the world told them, the rest read the
    document ahead of them. (each finding that ran, what went astray)"""
    strays, out = [], {}
    first = guards[0][1]
    doc = Document(first.payload, first.env)
    logs = {g.NAME: log for g, _, log, _ in guards}
    for g in reversed(list(dict.fromkeys(run.wired(doc.event, doc.tool)))):
        world = _Replayed(logs[g.NAME], strays) if g.NAME in logs else _Refused()
        r = finding(SimpleNamespace(NAME=g.NAME, check=g.check), doc, world, [])
        if g.NAME in logs:
            out[g.NAME] = r
    return out, strays


@pytest.fixture(autouse=True)
def pipeline(engine, request, monkeypatch):
    if engine not in ("python", "shfmt"):
        yield
        return
    calls, io = [], {}
    state = {"in": 0, "scans": None, "ladder": None}
    real_finding, real_respond, real_parse, real_scan = run._finding, run.respond, scan.parse, scan.Scan

    class Counted(real_scan):
        def __init__(self, text):
            if state["in"]:
                state["scans"][text] = state["scans"].get(text, 0) + 1
            super().__init__(text)

    def parse(text, words=False):
        if state["in"] and not words:
            state["ladder"].append(text)
        return real_parse(text, words)

    def finding(g, doc, world, acts):
        log = []
        r = real_finding(g, doc, _Recorded(world, log, io), acts)
        calls[-1].append((g, doc, log, r))
        return r

    def respond(stdin_text, env, only=None):
        calls.append([])
        state.update(scans={}, ladder=[])
        state["in"] += 1
        try:
            out = real_respond(stdin_text, env, only)
        finally:
            state["in"] -= 1
        twice = {t: n for t, n in state["scans"].items() if n > 1}
        assert not twice, f"scanned more than once in one call: {twice}"
        assert len(state["ladder"]) <= 1, f"the parser ladder ran {len(state['ladder'])} times in one call"
        guards = calls[-1]
        if guards:
            again, strays = _replay(guards, real_finding)
            assert not strays, f"a guard asked other questions in reverse order: {strays}"
            found = {g.NAME: r for g, _, _, r in guards}
            assert again == found, f"in reverse order the guards found {again}, not {found}"
        return out

    monkeypatch.setattr(scan, "Scan", Counted)
    monkeypatch.setattr(scan, "parse", parse)
    monkeypatch.setattr(run, "_finding", finding)
    monkeypatch.setattr(run, "respond", respond)
    yield
    rep = getattr(request.node, "_pipeline_call", None)
    if rep is None or not rep.passed:
        return
    got = {k: io[k] for k in PIN_KINDS if io.get(k)}
    key = _key(request.node)
    if _UPDATE:
        _seen.setdefault(key, {})[engine] = got
        return
    want = _pinned.get(key, {})
    assert got == want, (f"{key}: programs and GitHub calls {got}, pinned {want} in {PINS.name}. One more git or "
                         "network call per guard shows here; if it is meant, LANGUETTE_PIN_IO=update pytest "
                         "tests/test_features.py")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    rep = (yield).get_result()
    if rep.when == "call":
        item._pipeline_call = rep


def pytest_collection_modifyitems(items):
    _collected.update(_key(i) for i in items)


def pytest_sessionfinish(session):
    if not _UPDATE or not _seen:
        return
    split = {k: v for k, v in _seen.items() if len({json.dumps(c, sort_keys=True) for c in v.values()}) > 1}
    if split:
        raise pytest.UsageError(f"engines disagree on a scenario's I/O, so it cannot be pinned: {split}")
    files = {k.split("::")[0] for k in _seen}
    pins = {k: v for k, v in _pinned.items() if k.split("::")[0] not in files or k in _collected}
    for k, v in _seen.items():
        c = next(iter(v.values()))
        if c:
            pins[k] = c
        else:
            pins.pop(k, None)
    # One scenario per line, so a changed count is a one-line diff.
    PINS.write_text("{\n" + ",\n".join(f" {json.dumps(k)}: {json.dumps(v)}" for k, v in sorted(pins.items())) + "\n}\n")


__all__ = ["pipeline", "pytest_runtest_makereport", "pytest_collection_modifyitems", "pytest_sessionfinish"]
