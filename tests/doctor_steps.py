"""Steps for features/doctor.feature: `python3 -m languette doctor` run by
subprocess against a fake HOME of its own, with `claude` and the forge clients stubbed
first on PATH and this repo as the plugin's install path. conftest.py
imports these, so pytest-bdd finds them."""

import json
import os
import re
import shutil
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, equal_to, is_not
from pytest_bdd import given, parsers, then, when

from harness import FakeHome, fixture_text
from languette.doctor import FORGES

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = "languette@languette"


class Doctor(FakeHome):
    def __init__(self):
        super().__init__("doctor", ("project/sub", ".claude/plugins"))
        self.installs = []
        self.claude_ok = True
        self.signed = {"gh": True}         # forge client -> signed in; absent ones get no stub
        self.overrides = {}                    # path -> text, written over what the install steps wrote

    def expand(self, s):
        return s.replace("{HOME}", str(self.home)).replace("~/", f"{self.home}/")

    def settings(self):
        p = self.home / ".claude/settings.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def write_settings(self, s):
        (self.home / ".claude/settings.json").write_text(json.dumps(s))

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

    def run(self, cwd, *extra):
        self.write_installs()
        for path, text in self.overrides.items():
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text)
        for name, signed in self.signed.items():
            args, lists, _ = FORGES[name]
            out = ("echo a-host" if lists else "") if signed else "echo 'No logins.' >&2" if lists else "exit 1"
            self.stub(name, f'[ "$*" = "{" ".join(args)}" ] || exit 2\n{out}')
        self.invoke(["doctor", *extra], cwd, os.environ["PATH"])


@pytest.fixture
def doctor():
    d = Doctor()
    yield d
    d.cleanup()


@given("a fake HOME")
def _fake_home(doctor):
    pass


@given(parsers.re(r"(?P<name>[\w-]+) is signed (?P<state>in|out)"))
def _forge_signed(doctor, name, state):
    assert name in FORGES, f"{name} is not a forge client the doctor knows"
    doctor.signed[name] = state == "in"


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
                  r'(?P<guard>[\w-]+) hook allows everything'))
def _installed_open(doctor, version, guard):
    copy = doctor.aside / "plugin"
    (copy / "hooks").mkdir(parents=True)
    # Both probed guards get a hook: the named one lets everything through, the other is the real one.
    hooks = [_real_hook_for(_other_probed(guard)),
             {"type": "command", "command": f'cat >/dev/null # languette/run.py" --guard {guard}'}]
    (copy / "languette").symlink_to(ROOT / "languette")      # the real guard behind the real hook
    (copy / "hooks/hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": hooks}]}}))
    _install(doctor, version, "user", root=copy)


def _other_probed(guard):
    [other] = {"guard-recursive-delete", "require-well-formed"} - {guard}
    return other


def _real_hook_for(guard):
    """The plugin's one PreToolUse hook, narrowed to `guard` alone: a copy wired per guard."""
    [h] = [h for e in json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"] for h in e["hooks"]]
    run_py = 'python3 -I "${CLAUDE_PLUGIN_ROOT}/languette/run.py"'
    assert h["command"].count(run_py) == 1
    return {**h, "command": h["command"].replace(run_py, f"{run_py} --guard {guard}")}


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope from a copy without a '
                  r'(?P<guard>[\w-]+) hook'))
def _installed_without(doctor, version, guard):
    copy = doctor.aside / "plugin"
    (copy / "hooks").mkdir(parents=True)
    hooks = [_real_hook_for(_other_probed(guard))]
    (copy / "languette").symlink_to(ROOT / "languette")
    (copy / "hooks/hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": hooks}]}}))
    _install(doctor, version, "user", root=copy)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope from a copy without run\.py'))
def _installed_no_run_py(doctor, version):
    copy = doctor.aside / "plugin"
    (copy / "hooks").mkdir(parents=True)
    shutil.copy(ROOT / "hooks/hooks.json", copy / "hooks/hooks.json")
    _install(doctor, version, "user", root=copy)


@given(parsers.re(r'languette "(?P<version>\w+)" is installed at user scope from a copy whose '
                  r'guard-recursive-delete raises when called'))
def _installed_crashing(doctor, version):
    copy = doctor.aside / "plugin"
    shutil.copytree(ROOT / "hooks", copy / "hooks")
    shutil.copytree(ROOT / "languette", copy / "languette", ignore=shutil.ignore_patterns("__pycache__"))
    with open(copy / "languette/guards/guard_recursive_delete.py", "a", encoding="utf-8") as f:
        f.write("\n\ndef check(doc):\n    raise RuntimeError(\"canary\")\n")
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
    doctor.overrides[doctor.expand(path)] = text.replace("{TAB}", "\t")


@given(parsers.parse('"{path}" holds the fixture "{name}"'))
def _holds_fixture(doctor, path, name):
    doctor.overrides[doctor.expand(path)] = fixture_text(name, str(doctor.home))


@when("the doctor runs")
def _runs(doctor):
    doctor.run(doctor.home / "project")


@when(parsers.re(r'the doctor runs with `(?P<flag>--[a-z]+)` and the fixture "(?P<name>[^"]+)"(?: plus the line "(?P<extra>[^"]*)")?'))
def _runs_with_fixture(doctor, flag, name, extra):
    post = doctor.aside / "post.md"
    post.write_text(fixture_text(name, str(doctor.home)) + (f"\n{extra}" if extra else ""))
    doctor.run(doctor.home / "project", flag, str(post))


@then(parsers.re(r'it prints the fixture "(?P<name>[^"]+)"'))
def _prints_fixture(doctor, name):
    want = fixture_text(name, str(doctor.home)).strip()
    assert want in doctor.out, f"{want!r} not in:\n{doctor.out}{doctor.err}"


@then(parsers.re(r'it prints "(?P<text>.*)"'))
def _prints(doctor, text):
    assert_that(doctor.out, contains_string(text.replace('\\"', '"')))


@when(parsers.parse('the doctor runs in "{path}"'))
def _runs_in(doctor, path):
    doctor.run(doctor.expand(path))


@then(parsers.re(r'the "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) "(?P<text>.*)"'))
def _row(doctor, label, mark, text):
    doctor.assert_row(label, mark, text)


@then(parsers.re(r'the "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) "(?P<state>[^"]*)" and its note'))
def _row_noted(doctor, label, mark, state):
    got_mark, text = doctor.row(label)
    head, semicolon, _ = text.partition(";")
    assert (got_mark, head, semicolon) == (mark, state, ";"), text   # the state, then some note; not the note's words


@then(parsers.re(r'the "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) matching "(?P<pattern>.*)"'))
def _row_matching(doctor, label, mark, pattern):
    got_mark, got = doctor.row(label)
    assert_that(got_mark, equal_to(mark), got)
    assert re.search(pattern, got), f"{got!r} does not match {pattern!r}"


@then(parsers.parse('the "{first}" row comes before the "{second}" row'))
def _row_order(doctor, first, second):
    labels = [ln[2:].split("  ")[0].strip() for ln in doctor.out.splitlines()]
    assert_that(labels.index(first) < labels.index(second), f"{first!r} before {second!r} in:\n{doctor.out}")


@then(parsers.parse('the "{label}" row is there'))
def _row_there(doctor, label):
    doctor.row(label)


@then(parsers.parse("the doctor exits {code:d}"))
def _exits(doctor, code):
    doctor.assert_exit(code)


@then("the doctor prints no traceback")
def _no_traceback(doctor):
    assert_that(doctor.err, is_not(contains_string("Traceback")))
    assert_that(doctor.err, equal_to(""))


@then("the fake HOME is as it was")
def _home_untouched(doctor):
    doctor.assert_untouched()


# What conftest.py takes: the fixture and the step fixtures pytest-bdd made above.
__all__ = ["doctor"] + [k for k in list(globals()) if k.startswith("pytestbdd_")]
