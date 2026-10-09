"""Steps for features/doctor.feature: `python3 -m languette doctor` run by
subprocess against a fake HOME of its own, with `claude` and `gh` stubbed
first on PATH and this repo as the plugin's install path. conftest.py
imports these, so pytest-bdd finds them."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, equal_to, has_length, is_not
from pytest_bdd import given, parsers, then, when

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = "languette@languette"


class Doctor:
    def __init__(self):
        # Not under /tmp: guard-recursive-delete allows all of /tmp, so `rm -rf ~` would pass.
        self.home = Path(tempfile.mkdtemp(prefix="languette-doctor-home-", dir="/var/tmp"))
        (self.home / "project/sub").mkdir(parents=True)
        (self.home / ".claude/plugins").mkdir(parents=True)
        self.aside = Path(tempfile.mkdtemp(prefix="languette-doctor-"))   # stubs and copies, outside HOME
        self.bin = self.aside / "bin"
        self.bin.mkdir()
        self.installs = []
        self.claude_ok = True
        self.gh_ok = True
        self.overrides = {}                    # path -> text, written over what the install steps wrote
        self.out = self.err = self.code = None
        self.before = None

    def expand(self, s):
        return s.replace("{HOME}", str(self.home)).replace("~/", f"{self.home}/")

    def settings(self):
        p = self.home / ".claude/settings.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def write_settings(self, s):
        (self.home / ".claude/settings.json").write_text(json.dumps(s))

    def snapshot(self):
        return sorted((str(p.relative_to(self.home)), p.stat().st_size) for p in self.home.rglob("*"))

    def stub(self, name, body):
        f = self.bin / name
        f.write_text(f"#!/bin/sh\n{body}\n")
        f.chmod(0o755)

    def write_installs(self):
        listed = self.aside / "plugin-list.json"
        listed.write_text(json.dumps(self.installs))
        by_id = {}
        for i in self.installs:
            by_id.setdefault(i["id"], []).append({k: v for k, v in i.items() if k not in ("id", "enabled")})
        (self.home / ".claude/plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": by_id}))
        if any(not i["enabled"] for i in self.installs):
            s = self.settings()
            s.setdefault("enabledPlugins", {})[PLUGIN_ID] = False
            self.write_settings(s)
        self.stub("claude", f'[ "$*" = "plugin list --json" ] || exit 2\n'
                            f'{"exec cat " + str(listed) if self.claude_ok else "exit 1"}')

    def run(self, cwd):
        self.write_installs()
        for path, text in self.overrides.items():
            Path(path).write_text(text)
        self.stub("gh", f'[ "$1 $2" = "auth status" ] && exit {0 if self.gh_ok else 1}\nexit 2')
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "LANGUETTE_"))}
        env.update(HOME=str(self.home), PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                   TMPDIR=str(self.aside), PYTHONPATH=str(ROOT))
        self.before = self.snapshot()
        r = subprocess.run([sys.executable, "-m", "languette", "doctor"], cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=60)
        self.out, self.err, self.code = r.stdout, r.stderr, r.returncode

    def row(self, label):
        rows = [ln for ln in self.out.splitlines() if ln[2:].startswith(label + " ")]
        assert_that(rows, has_length(1), f"one {label!r} row in:\n{self.out}{self.err}")
        return rows[0][0], rows[0][2:][len(label):].strip()

    def cleanup(self):
        for d in (self.home, self.aside):
            shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def doctor():
    d = Doctor()
    yield d
    d.cleanup()


@given("a fake HOME")
def _fake_home(doctor):
    pass


@given("gh is signed in")
def _gh_in(doctor):
    doctor.gh_ok = True


@given("gh is signed out")
def _gh_out(doctor):
    doctor.gh_ok = False


@given("claude plugin list fails")
def _claude_fails(doctor):
    doctor.claude_ok = False


def _install(doctor, version, scope, root=ROOT, project=None, enabled=True):
    i = {"id": PLUGIN_ID, "version": version, "scope": scope, "enabled": enabled, "installPath": str(root)}
    if project:
        i["projectPath"] = doctor.expand(project)
    doctor.installs.append(i)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope'))
def _installed(doctor, version):
    _install(doctor, version, "user")


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope, disabled'))
def _installed_disabled(doctor, version):
    _install(doctor, version, "user", enabled=False)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at project scope for "(?P<project>[^"]+)"'))
def _installed_project(doctor, version, project):
    _install(doctor, version, "project", project=project)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope from a copy whose '
                  r'guard-recursive-delete hook allows everything'))
def _installed_open(doctor, version):
    copy = doctor.aside / "plugin"
    (copy / "hooks").mkdir(parents=True)
    hook = {"type": "command", "command": "cat >/dev/null # --guard guard-recursive-delete"}
    (copy / "hooks/hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [hook]}]}}))
    _install(doctor, version, "user", root=copy)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope from a copy without run\.py'))
def _installed_no_run_py(doctor, version):
    copy = doctor.aside / "plugin"
    (copy / "hooks").mkdir(parents=True)
    shutil.copy(ROOT / "hooks/hooks.json", copy / "hooks/hooks.json")
    _install(doctor, version, "user", root=copy)


@given(parsers.parse("the languette options are `{options}`"))
def _options(doctor, options):
    s = doctor.settings()
    s.setdefault("pluginConfigs", {})[PLUGIN_ID] = {"options": json.loads(options)}
    doctor.write_settings(s)


@given("the user's settings.json has a by-hand guard-recursive-delete hook")
def _by_hand(doctor):
    # The README's "Installing by hand" entry, pointed at this repo.
    deny = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": "languette/run.py is missing or crashed"}})
    command = (f'h="{ROOT}/languette/run.py"; {{ [ -f "$h" ] && python3 -I "$h" --guard guard-recursive-delete; }} '
               f"|| printf '%s\\n' '{deny}'")
    s = doctor.settings()
    s.setdefault("hooks", {}).setdefault("PreToolUse", []).append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]})
    doctor.write_settings(s)


@given("the project's settings have a by-hand guard-recursive-delete hook that leaves a mark")
def _by_hand_project(doctor):
    command = f'touch "{doctor.aside}/mark"; python3 -I "{ROOT}/languette/run.py" --guard guard-recursive-delete'
    p = doctor.home / "project/.claude/settings.json"
    p.parent.mkdir()
    p.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
                                                                                      "command": command}]}]}}))


@then("the hook left no mark")
def _no_mark(doctor):
    assert not (doctor.aside / "mark").exists(), "the doctor ran a command from a project's settings"


@given(parsers.parse('"{path}" holds `{text}`'))
def _holds(doctor, path, text):
    doctor.overrides[doctor.expand(path)] = text


@when("the doctor runs")
def _runs(doctor):
    doctor.run(doctor.home / "project")


@when(parsers.parse('the doctor runs in "{path}"'))
def _runs_in(doctor, path):
    doctor.run(doctor.expand(path))


@then(parsers.re(r'the "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) "(?P<text>.*)"'))
def _row(doctor, label, mark, text):
    assert_that(doctor.row(label), equal_to((mark, text)))


@then(parsers.re(r'the "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) matching "(?P<pattern>.*)"'))
def _row_matching(doctor, label, mark, pattern):
    got_mark, got = doctor.row(label)
    assert_that(got_mark, equal_to(mark), got)
    assert re.search(pattern, got), f"{got!r} does not match {pattern!r}"


@then(parsers.parse('the "{label}" row is there'))
def _row_there(doctor, label):
    doctor.row(label)


@then(parsers.parse("the doctor exits {code:d}"))
def _exits(doctor, code):
    assert_that(doctor.code, equal_to(code), doctor.out + doctor.err)


@then("the doctor prints no traceback")
def _no_traceback(doctor):
    assert_that(doctor.err, is_not(contains_string("Traceback")))
    assert_that(doctor.err, equal_to(""))


@then("the fake HOME is as it was")
def _home_untouched(doctor):
    assert_that(doctor.snapshot(), equal_to(doctor.before))


# What conftest.py takes: the fixture and the step fixtures pytest-bdd made above.
__all__ = ["doctor"] + [k for k in list(globals()) if k.startswith("pytestbdd_")]
