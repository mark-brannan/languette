"""Steps for features/install.feature: `python3 -m languette install` run by
subprocess against a fake HOME of its own, with a stub `claude` first on PATH
that records each command it is asked and answers from canned output.
conftest.py imports these, so pytest-bdd finds them."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, equal_to, has_length
from pytest_bdd import given, parsers, then, when

from languette.install import REPO, SOURCE

ROOT = Path(__file__).resolve().parent.parent


class Install:
    def __init__(self):
        # Not under /tmp: guard-recursive-delete allows all of /tmp.
        self.home = Path(tempfile.mkdtemp(prefix="languette-install-home-", dir="/var/tmp"))
        (self.home / "project").mkdir()
        self.aside = Path(tempfile.mkdtemp(prefix="languette-install-"))   # the stub and its log, outside HOME
        self.bin = self.aside / "bin"
        self.bin.mkdir()
        self.log = self.aside / "asked"
        self.claude = True
        self.plugins, self.marketplaces = [], []
        self.add = (0, "")                     # exit code and stderr of `claude plugin marketplace add`
        self.after_add = [{"name": "languette", "source": "github", "repo": REPO}]   # what list shows after an add
        self.out = self.err = self.code = self.before = None

    def snapshot(self):
        return sorted((str(p.relative_to(self.home)), p.stat().st_size) for p in self.home.rglob("*"))

    def stub(self):
        listed, after = self.aside / "marketplaces.json", self.aside / "after-add.json"
        listed.write_text(json.dumps(self.marketplaces))
        after.write_text(json.dumps(self.after_add))
        # An add, even one that answers "already", leaves the list as after_add says.
        answers = {"plugin list --json": (0, json.dumps(self.plugins), "", ""),
                   "plugin marketplace list --json": (0, "", "", f"cat {shlex.quote(str(listed))};"),
                   f"plugin marketplace add {SOURCE}": (self.add[0], "", self.add[1],
                                                        f"cp {shlex.quote(str(after))} {shlex.quote(str(listed))};"),
                   "plugin install languette@languette": (0, "Installed languette", "", "")}
        cases = "".join(f"  {shlex.quote(asked)}) {run} printf '%s' {shlex.quote(out)}; "
                        f"printf '%s' {shlex.quote(err)} >&2; exit {code};;\n"
                        for asked, (code, out, err, run) in answers.items())
        f = self.bin / "claude"
        f.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> {shlex.quote(str(self.log))}\ncase "$*" in\n{cases}'
                     "  *) exit 2;;\nesac\n")
        f.chmod(0o755)

    def run(self, *args):
        if self.claude:
            self.stub()
        self.log.write_text("")
        # Without the real PATH, so the real claude is never found: only the stub's directory and the system's.
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "LANGUETTE_"))}
        env.update(HOME=str(self.home), PATH=f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
                   TMPDIR=str(self.aside), PYTHONPATH=str(ROOT))
        self.before = self.snapshot()
        r = subprocess.run([sys.executable, "-m", "languette", "install", *args], cwd=self.home / "project",
                           env=env, capture_output=True, text=True, timeout=60)
        self.out, self.err, self.code = r.stdout, r.stderr, r.returncode

    def row(self, label):
        rows = [ln for ln in self.out.splitlines() if ln[2:].startswith(label + " ")]
        assert_that(rows, has_length(1), f"one {label!r} row in:\n{self.out}{self.err}")
        return rows[0][0], rows[0][2:][len(label):].strip()

    def cleanup(self):
        for d in (self.home, self.aside):
            shutil.rmtree(d, ignore_errors=True)


def _expand(text):
    return text.replace("{SOURCE}", SOURCE).replace("{REPO}", REPO)


@pytest.fixture
def installer():
    i = Install()
    yield i
    i.cleanup()


@given("a fake HOME and a stub claude")
def _fake_home(installer):
    pass


@given("claude is not on PATH")
def _no_claude(installer):
    installer.claude = False


@given(parsers.re(r'claude lists languette "(?P<version>\w+)" installed at user scope(?P<off>, disabled)?'))
def _listed(installer, version, off):
    installer.plugins.append({"id": "languette@languette", "version": version, "scope": "user", "enabled": not off,
                              "installPath": str(ROOT)})


@given("claude lists the languette marketplace")
def _marketplace(installer):
    installer.marketplaces.append({"name": "languette", "source": "github", "repo": REPO})


@given(parsers.parse('claude lists a languette marketplace from "{repo}"'))
def _foreign_marketplace(installer, repo):
    installer.marketplaces.append({"name": "languette", "source": "github", "repo": repo})


@given(parsers.parse('after an add, claude lists a languette marketplace from "{repo}"'))
def _foreign_after_add(installer, repo):
    installer.after_add = [{"name": "languette", "source": "github", "repo": repo}]


@given(parsers.parse('claude plugin marketplace add fails with "{err}"'))
def _add_fails(installer, err):
    installer.add = (1, err + "\n")


@when("install runs")
def _runs(installer):
    installer.run()


@when(parsers.parse('install runs for "{host}"'))
def _runs_for(installer, host):
    installer.run(host)


@then(parsers.re(r'the install "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) "(?P<text>.*)"'))
def _row(installer, label, mark, text):
    assert_that(installer.row(label), equal_to((mark, _expand(text))))


@then("claude was asked only:")
def _asked(installer, docstring):
    assert_that(installer.log.read_text().splitlines(), equal_to(_expand(docstring).splitlines()))


@then("claude was asked nothing")
def _asked_nothing(installer):
    assert_that(installer.log.read_text(), equal_to(""))


@then(parsers.parse("install exits {code:d}"))
def _exits(installer, code):
    assert_that(installer.code, equal_to(code), installer.out + installer.err)


@then(parsers.parse('install says on stderr "{text}"'))
def _stderr(installer, text):
    assert_that(installer.err, contains_string(text))


@then("the fake HOME is as it was before install")
def _home_untouched(installer):
    assert_that(installer.snapshot(), equal_to(installer.before))


# What conftest.py takes: the fixture and the step fixtures pytest-bdd made above.
__all__ = ["installer"] + [k for k in list(globals()) if k.startswith("pytestbdd_")]
