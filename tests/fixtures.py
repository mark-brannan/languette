"""The autouse and per-scenario fixtures: the engine, the pinned parser rung,
the write gate and the scenario's Ctx. Moved out of conftest.py unchanged."""

import builtins
import os

import pytest

from harness import Ctx, IN_PROCESS
from languette import run, scan, world

@pytest.fixture(autouse=True)
def engine():
    return None                                # plain tests in test_repo.py have no engine


@pytest.fixture(autouse=True)
def rungs(engine, monkeypatch):
    """Pin the parser ladder to the engine's one rung."""
    if engine not in IN_PROCESS:
        return
    if engine == "shfmt" and not scan.shfmt():
        if os.environ.get("CI"):
            pytest.fail(f"CI runs the shfmt engine: no shfmt >= {scan.SHFMT_MIN} on PATH")
        pytest.skip(f"no shfmt >= {scan.SHFMT_MIN} on PATH")
    monkeypatch.setattr(scan, "RUNGS", IN_PROCESS[engine])



# Needs that write as they read, under one lock or rename (languette.verdict.Need):
# (kind, op), op None for a kind with no ops.
ATOMIC = {("claim", None), ("door", "claim"), ("door", "take"), ("worktree", "arrive")}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_WRITES = "unlink remove rename renames replace mkdir makedirs rmdir removedirs symlink link chmod truncate".split()


@pytest.fixture(autouse=True)
def writes_in_acts(engine, monkeypatch):
    """In-process, a write while run.respond runs raises unless World.act,
    World.keep or an ATOMIC Need makes it, and the scenario fails on it,
    whatever the guard made of the error. Opens are judged by their flags or
    mode; an fd write needs an open first. /dev/null is not a write."""
    if engine not in IN_PROCESS:
        yield
        return
    depth = {"respond": 0, "allowed": 0}
    strays = []

    def gated(name, f, writes=lambda *a, **kw: True):
        def g(*a, **kw):
            if depth["respond"] and not depth["allowed"] and writes(*a, **kw) and a[:1] != (os.devnull,):
                strays.append(f"{name}({a[0]!r})" if a else name)
                raise PermissionError(f"{name}: a write outside an act")
            return f(*a, **kw)
        return g

    def within(key, f, when=lambda *a: True):
        def w(*a, **kw):
            on = when(*a)
            depth[key] += on
            try:
                return f(*a, **kw)
            finally:
                depth[key] -= on
        return w

    def atomic(_self, need):
        return (need.kind, need.args[0] if need.kind in ("door", "worktree") else None) in ATOMIC

    for name in _WRITES:
        monkeypatch.setattr(os, name, gated(f"os.{name}", getattr(os, name)))
    monkeypatch.setattr(os, "open", gated("os.open", os.open, lambda path, flags, *a, **kw: flags & _WRITE_FLAGS))
    monkeypatch.setattr(builtins, "open", gated("open", builtins.open, lambda f, mode="r", *a, **kw:
                                                set(mode) & set("wax+")))
    monkeypatch.setattr(run, "respond", within("respond", run.respond))
    monkeypatch.setattr(world.World, "act", within("allowed", world.World.act))
    monkeypatch.setattr(world.World, "keep", within("allowed", world.World.keep))
    monkeypatch.setattr(world.World, "answer", within("allowed", world.World.answer, atomic))
    yield
    assert not strays, f"writes outside an act: {strays}"



@pytest.fixture
def ctx(engine, request):
    c = Ctx(engine, request.node.nodeid)
    yield c
    c.cleanup()
