"""Engines and the step vocabulary for features/*.feature.

Every scenario runs once per engine its feature is tagged with: @python runs
languette/ in-process twice, as the "python" engine on the parser ladder's awk
rung and as "shfmt" on its shfmt rung (skipped without a shfmt new enough,
except under CI); @hook runs a hooks/hooks.json command by subprocess, the way
Claude Code runs it (wiring.feature). @shfmt_only narrows a scenario to the
shfmt rung; @no_shfmt drops the shfmt rung, for a row its
parse check denies before any guard reads it. @awk_only narrows a scenario to the
awk rung.

In-process, every scenario runs with every guard on, opt-in guards switched on
unless the scenario sets their option. A feature's name is the guard it names:
that guard gives the row's verdict and every other guard is silent, except one
the row names with an @also_<guard> tag (on the scenario, or on an Examples
block), which must fire too. @family marks a feature named for a family of
guards, not one guard, and @planned one whose verdicts no guard gives yet: no
guard is named, so the silence check is off. @planned on one scenario marks it
expected to fail (xfail, not strict).

Each push runs a tier of that: the shfmt engine only on @big and @shfmt_only
scenarios, and no @planned or @full row. `pytest --full` runs everything,
nightly and on dispatch (.github/workflows/full-sweep.yml).
"""

import os
import shutil
import sys
import tempfile

import pytest

import harness
import pipeline_checks
from doctor_steps import *  # noqa: F401,F403  (features/doctor.feature)
from install_steps import *  # noqa: F401,F403  (features/install.feature)
from fixtures import *  # noqa: F401,F403  (engine, rungs, writes_in_acts, ctx)
from harness import ENGINES, GUARD_NAMES, IN_PROCESS, _REAL_HOME
from pipeline_checks import *  # noqa: F401,F403  (the guard pipeline's promises, on every scenario)
from steps import *  # noqa: F401,F403  (the step vocabulary)


# The suite runs on a small, fixed number of cores (pytest-xdist): this machine
# runs many sessions at once, and a run on every core has taken a host down
# before. The default is min(4, cores); LANGUETTE_TEST_WORKERS sets both the
# default and the ceiling, and an explicit `-n` above the ceiling is clamped to
# it. `-n 0` runs serially (and is how LANGUETTE_PIN_IO=update runs).
_WORKER_CAP = 4


def _worker_ceiling():
    raw = os.environ.get("LANGUETTE_TEST_WORKERS", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else _WORKER_CAP


def pytest_xdist_auto_num_workers(config):
    return min(_worker_ceiling(), os.cpu_count() or 1)


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    # Before xdist's own pytest_cmdline_main turns numprocesses into the list
    # of workers to start (config.option.tx); clamping later changes nothing.
    n = getattr(config.option, "numprocesses", None)
    if isinstance(n, int) and n > _worker_ceiling():
        config.option.numprocesses = _worker_ceiling()
        sys.stderr.write(f"languette: -n {n} clamped to {_worker_ceiling()} workers "
                         "(raise the ceiling with LANGUETTE_TEST_WORKERS)\n")


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    refuse_partial_update(config)
    for g in GUARD_NAMES:
        config.addinivalue_line("markers", f"also_{g}: the row rightly trips {g} too")
    # A throwaway $HOME for the whole run, so no verdict depends on, and no
    # step can touch, the real one; {HOME}/project for a row that names it.
    # The default cwd and the hook process's own directory are elsewhere (see
    # scattered). Not under /tmp: guard-recursive-delete allows all of /tmp,
    # so every target would pass.
    home = tempfile.mkdtemp(prefix="languette-home-", dir="/var/tmp")
    os.mkdir(os.path.join(home, "project"))
    os.environ["HOME"] = home
    harness.ELSEWHERE = tempfile.mkdtemp(prefix="languette-elsewhere-", dir="/var/tmp")


def pytest_unconfigure(config):
    home = os.environ["HOME"]
    if _REAL_HOME is None:
        del os.environ["HOME"]
    else:
        os.environ["HOME"] = _REAL_HOME
    if os.path.basename(home).startswith("languette-home-"):
        shutil.rmtree(home, ignore_errors=True)
    if harness.ELSEWHERE:
        shutil.rmtree(harness.ELSEWHERE, ignore_errors=True)



def pytest_generate_tests(metafunc):
    marks = {m.name for m in metafunc.definition.iter_markers()}
    engines = [e for e in ENGINES if e in marks or (e == "shfmt" and "python" in marks)]
    if "awk_only" in marks:
        engines = ["python"]
    if "shfmt_only" in marks:
        engines = ["shfmt"]
    if "no_shfmt" in marks:
        engines = [e for e in engines if e != "shfmt"]
    if engines:
        metafunc.parametrize("engine", engines)


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true",
                     help="the full sweep: the shfmt engine on every row, @planned and @full rows")


def _full_sweep_only(item):
    if item.get_closest_marker("planned") or item.get_closest_marker("full"):
        return True
    on_shfmt = getattr(item, "callspec", None) and item.callspec.params.get("engine") == "shfmt"
    return bool(on_shfmt) and not (item.get_closest_marker("big") or item.get_closest_marker("shfmt_only"))


def pytest_collection_modifyitems(config, items):
    if not config.getoption("full"):
        dropped = [i for i in items if _full_sweep_only(i)]
        if dropped:
            items[:] = [i for i in items if not _full_sweep_only(i)]
            config.hook.pytest_deselected(items=dropped)
    for item in items:
        if item.get_closest_marker("planned"):
            item.add_marker(pytest.mark.xfail(reason="planned: no guard gives this verdict yet", strict=False))
    pipeline_checks.pytest_collection_modifyitems(items)     # this hook shadows its star-imported one


def pytest_bdd_before_scenario(request, feature, scenario):
    c = request.getfixturevalue("ctx")
    named = feature.name in GUARD_NAMES and not {"planned", "family"} & set(feature.tags)
    c.guard = feature.name if named else None
    c.also = {m.name.removeprefix("also_") for m in request.node.iter_markers() if m.name.startswith("also_")}
    unknown = c.also - set(GUARD_NAMES)
    assert not unknown, f"test setup: @also_ names no guard: {sorted(unknown)}"


def pytest_bdd_after_scenario(request, feature, scenario):
    c = request.getfixturevalue("ctx")
    if c.guard and c.engine in IN_PROCESS:
        quiet = c.also - c.fired
        assert not quiet, f"@also_ names a guard that never fired here: {sorted(quiet)}"
