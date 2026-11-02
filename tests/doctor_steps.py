"""Steps for features/doctor.feature: `python3 -m languette doctor` run by
subprocess against a fake HOME of its own, with `claude` and the forge clients stubbed
first on PATH and this repo as the plugin's install path. conftest.py
imports these, so pytest-bdd finds them."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from hamcrest import assert_that, contains_string, equal_to, has_item, is_not
from pytest_bdd import given, parsers, then, when

from harness import FakeHome, fixture_text
from languette import terms
from languette.doctor import FORGES

DEFAULTS = terms.defaults(Path(terms.DEFAULTS).read_text())

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = "languette@languette"


class Doctor(FakeHome):
    def __init__(self):
        super().__init__("doctor", ("project/sub", ".claude/plugins"))
        self.cfg = self.home / ".claude"        # the host's configuration directory
        self.installs = []
        self.claude_ok = True
        self.signed = {"gh": True}         # forge client -> signed in; absent ones get no stub
        self.overrides = {}                    # path -> text, written over what the install steps wrote

    def expand(self, s):
        return s.replace("{HOME}", str(self.home)).replace("~/", f"{self.home}/")

    def settings(self):
        p = self.cfg / "settings.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def write_settings(self, s):
        (self.cfg / "settings.json").write_text(json.dumps(s))

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
        (self.cfg / "plugins/installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": by_id}))
        if any(not i["enabled"] for i in self.installs):
            s = self.settings()
            s.setdefault("enabledPlugins", {})[PLUGIN_ID] = False
            self.write_settings(s)
        self.stub("claude", f'[ "$*" = "plugin list --json" ] || exit 2\n'
                            f'{"exec cat " + str(listed) if self.claude_ok else "exit 1"}')

    def run(self, cwd, *extra, stdin=None):
        self.write_installs()
        for path, text in self.overrides.items():
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text)
        for name, signed in self.signed.items():
            args, lists, _ = FORGES[name]
            out = ("echo a-host" if lists else "") if signed else "echo 'No logins.' >&2" if lists else "exit 1"
            self.stub(name, f'[ "$*" = "{" ".join(args)}" ] || exit 2\n{out}')
        self.invoke(["doctor", *extra], cwd, os.environ["PATH"], stdin)
        self.last = None                       # the row the last row step asserted, for "beneath it"

    def details(self, label):
        """[(depth, mark, text)] for the lines indented beneath the row `label`."""
        lines = self.out.splitlines()
        [at] = [i for i, ln in enumerate(lines) if ln[2:].startswith(label + " ")]
        out = []
        for ln in lines[at + 1:]:
            if not ln.startswith(" "):
                break
            body = ln.lstrip(" ")
            depth = (len(ln) - len(body)) // 4
            mark, text = (body[0], body[2:]) if body[:1] in "✓!✗" else ("", body)
            out.append((depth, mark, text))
        return out

    def beneath(self, label, text, mark, depth=1):
        found = [(d, m) for d, m, t in self.details(label) if t == text and d == depth]
        assert found, f"no {text!r} at depth {depth} beneath {label!r} in:\n{self.out}{self.err}"
        assert_that(found[0][1], equal_to(mark), f"{text!r} beneath {label!r}")
        self.last_detail = text

    def group(self, name):
        """The redacted terms file's lines tagged default:<name>, each (commented out, the line)."""
        out = []
        for ln in self.terms_file().read_text().splitlines():
            m = terms.TAG.search(ln.split("\t")[-1]) if ln.count("\t") == 2 else None
            if m and m["name"] == name:
                out.append((ln.startswith("#"), ln))
        return out

    def terms_file(self):
        return self.home / ".config/languette/redacted-terms.tsv"


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


@given(parsers.parse('the host\'s configuration directory is "{path}"'))
def _config_dir(doctor, path):
    doctor.cfg = Path(doctor.expand(path))
    (doctor.cfg / "plugins").mkdir(parents=True)
    doctor.env["CLAUDE_CONFIG_DIR"] = str(doctor.cfg)


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
    doctor.overrides[doctor.expand(path)] = text.replace("{TAB}", "\t").replace("\\n", "\n")


@given(parsers.parse('"{path}" holds ``'))
def _holds_nothing(doctor, path):
    doctor.overrides[doctor.expand(path)] = ""


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
    doctor.last = label


@then(parsers.re(r'beneath it "(?P<a>[^"]+)" is (?P<ma>[✓!✗]) and "(?P<b>[^"]+)" is (?P<mb>[✓!✗])'))
def _beneath_two(doctor, a, ma, b, mb):
    doctor.beneath(doctor.last, a, ma)
    doctor.beneath(doctor.last, b, mb)


@then(parsers.re(r'beneath it "(?P<text>[^"]+)" is (?P<mark>[✓!✗])'))
def _beneath(doctor, text, mark):
    doctor.beneath(doctor.last, text, mark)


@then(parsers.re(r'beneath the "(?P<label>[^"]+)" row "(?P<text>[^"]+)" is (?P<mark>[✓!✗])'))
def _beneath_row(doctor, label, text, mark):
    doctor.last = label
    doctor.beneath(label, text, mark)


@then(parsers.re(r'beneath that, "(?P<text>.+)"'))
def _beneath_that(doctor, text):
    """A bare line one level deeper than the detail line last asserted."""
    found = [(d, t) for d, _, t in doctor.details(doctor.last) if d == 2 and t == text]
    assert found, f"no {text!r} two levels beneath {doctor.last!r} in:\n{doctor.out}"


@then(parsers.re(r'beneath that, one ! line per off guard, "\(off\) (?P<guard>\w*): " and its one-line description'))
def _off_guards(doctor, guard):
    deeper = [(m, t) for d, m, t in doctor.details(doctor.last) if d == 2]
    want = [guard] if guard else []
    assert_that([t.split(":")[0] for _, t in deeper], equal_to([f"(off) {g}" for g in want]), doctor.out)
    for m, t in deeper:
        assert m == "!" and t.split(": ", 1)[1].strip(), t


@then(parsers.re(r'beneath it a line is (?P<mark>[✓!✗]) matching "(?P<pattern>.*)"'))
def _beneath_matching(doctor, mark, pattern):
    found = [(m, t) for d, m, t in doctor.details(doctor.last) if d == 1 and re.search(pattern, t)]
    assert found, f"nothing matching {pattern!r} beneath {doctor.last!r} in:\n{doctor.out}"
    assert_that(found[0][0], equal_to(mark), found[0][1])


@then(parsers.re(r'beneath the "(?P<label>[^"]+)" row "line 13", "line 17" and "line 22" are each ✗ with their reasons'))
def _bad_lines(doctor, label):
    doctor.last = label
    bad = {t.split(":")[0]: (m, t) for d, m, t in doctor.details(label) if d == 1 and t.startswith("line ")}
    assert_that(sorted(bad), equal_to(["line 13", "line 17", "line 22"]), doctor.out)
    want = {"line 13": "four columns", "line 17": "matches the empty string",
            "line 22": "a quantifier inside a quantified group"}
    for k, (m, t) in bad.items():
        assert_that((m, t), equal_to(("✗", f"{k}: {want[k]}")))


@given('"~/.config/languette/redacted-terms.tsv" holds a malformed line 13, an empty-matching re: line 17, '
       'a nested-quantifier line 22 and 8 valid re: lines')
def _holds_mixed(doctor):
    lines = ["# padding"] * 25
    for n in (2, 4, 6, 8, 10, 12, 15, 20):
        lines[n - 1] = f"re:v{n}-\\d+\tp{n}"
    lines[12] = "a\tb\tc\td"
    lines[16] = "re:x*"
    lines[21] = "re:(a+)+$"
    doctor.overrides[str(doctor.terms_file())] = "\n".join(lines).replace("\\d", "\\d") + "\n"


@then(parsers.re(r'the last line is "(?P<text>.*)"'))
def _last_line(doctor, text):
    assert_that(doctor.out.rstrip("\n").splitlines()[-1], equal_to(text))


@given(parsers.parse('"{path}" is a directory'))
def _is_dir(doctor, path):
    Path(doctor.expand(path)).mkdir(parents=True)


@given(parsers.parse('"{path}" exists but is not readable'))
def _unreadable(doctor, path):
    if os.geteuid() == 0:
        pytest.skip("root reads every file")
    p = Path(doctor.expand(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("zephyr-01\tx\n")
    p.chmod(0)


@when(parsers.re(r'the doctor runs with `(?P<args>[^`]+)`'))
def _runs_with(doctor, args):
    doctor.run(doctor.home / "project", *args.split())


@when(parsers.re(r'the doctor runs with `(?P<args>[^`]+)` and the fixture "(?P<name>[^"]+)" on stdin'))
def _runs_with_stdin(doctor, args, name):
    doctor.run(doctor.home / "project", *args.split(), stdin=fixture_text(name, str(doctor.home)))


@when(parsers.re(r'the doctor runs with `(?P<args>[^`]+)` and answers (?P<answer>yes|no)'))
def _runs_answering(doctor, args, answer):
    doctor.run(doctor.home / "project", *args.split(), stdin=answer[0] + "\n")


@then(parsers.re(r'it prints (?P<mark>[✓!✗]) "(?P<text>.*)"'))
def _prints_marked(doctor, mark, text):
    assert_that(doctor.out.splitlines(), has_item(f"{mark} {text}"), doctor.out + doctor.err)


@then('"~/.config/languette/redacted-terms.tsv" holds the default entries')
def _holds_defaults(doctor):
    got = terms.defaults(doctor.terms_file().read_text())
    assert_that(got, equal_to(DEFAULTS))
    for name, group in DEFAULTS.items():
        assert_that([ln for _, ln in doctor.group(name)], equal_to(terms.written(name, group)))


@then('"~/.config/languette/blocked-terms.tsv" holds a header and no terms')
def _holds_header(doctor):
    text = (doctor.home / ".config/languette/blocked-terms.tsv").read_text()
    assert_that(text.split("\n")[0], equal_to(terms.header("blocked")))
    assert_that(list(terms.entries(text, "blocked", {})), equal_to([]))


@then(parsers.parse('"{path}" is unchanged'))
def _unchanged(doctor, path):
    p = doctor.expand(path)
    assert_that(Path(p).read_text(), equal_to(doctor.overrides[p]))


def _edited(name):
    """The default's lines as an earlier version wrote them: one find changed, the tag matching."""
    group = [terms.Default(d.find.replace("(?!", "(?!x", 1) if i == 0 else d.find, d.put, d.about)
             for i, d in enumerate(DEFAULTS[name])]
    return terms.written(name, group)


def _by_hand(name):
    """The default's lines with one put changed by hand, the tag left as written."""
    return [ln.replace("\t<host>\t", "\t<machine>\t", 1) if i == 0 else ln
            for i, ln in enumerate(terms.written(name, DEFAULTS[name]))]


@given(parsers.re(r'"~/.config/languette/redacted-terms.tsv" holds every default entry but "(?P<missing>[\w-]+)"'
                  r'(?P<rest>.*)'))
def _holds_defaults_but(doctor, missing, rest):
    lines = [terms.header("redacted")]
    for name, group in DEFAULTS.items():
        if name == missing:
            continue
        written = terms.written(name, group)
        if f'with "{name}" commented out' in rest:
            written = ["# " + ln for ln in written]
        lines += written
    if 'the line "zephyr-01\\tthe boat"' in rest:
        lines.append("zephyr-01\tthe boat")
    doctor.overrides[str(doctor.terms_file())] = "\n".join(lines) + "\n"


@given('"~/.config/languette/redacted-terms.tsv" holds "home" as an earlier version wrote it, and "host" edited by hand')
def _holds_old_and_edited(doctor):
    lines = [terms.header("redacted")] + _edited("home") + _by_hand("host") \
        + terms.written("private-ip", DEFAULTS["private-ip"])
    doctor.overrides[str(doctor.terms_file())] = "\n".join(lines) + "\n"


@then("it prints the diff before writing")
def _diff_first(doctor):
    out = doctor.out
    assert "@@" in out and "\n+" in out, out
    assert out.index("@@") < out.index("wrote"), out


@then(parsers.parse('"{name}" is back where it sits in the defaults\' order'))
def _in_order(doctor, name):
    assert_that([ln for _, ln in doctor.group(name)], equal_to(terms.written(name, DEFAULTS[name])))
    seen = []
    for ln in doctor.terms_file().read_text().splitlines():
        m = terms.TAG.search(ln.split("\t")[-1]) if ln.count("\t") == 2 else None
        if m and m["name"] not in seen:
            seen.append(m["name"])
    assert_that(seen, equal_to(list(DEFAULTS)))


@then(parsers.parse('"{name}" is still commented out'))
def _still_off(doctor, name):
    group = doctor.group(name)
    assert group and all(off for off, _ in group), group


@then(parsers.parse('the line "{text}" is unchanged'))
def _line_kept(doctor, text):
    assert_that(doctor.terms_file().read_text().splitlines(), has_item(text.replace("\\t", "\t")))


@then("running it again changes nothing")
def _again(doctor):
    before = doctor.terms_file().read_text()
    doctor.overrides.pop(str(doctor.terms_file()))        # a run re-seeds the overrides; keep what was written
    doctor.run(doctor.home / "project", "--restore-redacted-terms", stdin="y\n")
    assert_that(doctor.terms_file().read_text(), equal_to(before))
    assert_that(doctor.out, contains_string("nothing to write"))


@then(parsers.parse('"{name}" holds the current version'))
def _current(doctor, name):
    assert_that([ln for _, ln in doctor.group(name)], equal_to(terms.written(name, DEFAULTS[name])))


@then(parsers.parse('"{name}" is unchanged, and it prints that "{same}" was edited by hand'))
def _left_edited(doctor, name, same):
    assert_that([ln for _, ln in doctor.group(name)], equal_to(_by_hand(name)))
    assert_that(doctor.out, contains_string(f"{name}: edited by hand"))


@then("it prints the doctor's own options")
def _own_options(doctor):
    for flag in ("--redact", "--init-redacted-terms", "--init-blocked-terms", "--restore-redacted-terms"):
        assert_that(doctor.out, contains_string(flag))


@then("it then prints everything `languette --help` prints")
def _parent_help(doctor):
    r = subprocess.run([sys.executable, "-m", "languette", "--help"], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert_that(doctor.out, contains_string(r.stdout.strip()))
    assert doctor.out.index("--restore-redacted-terms") < doctor.out.index(r.stdout.strip()[:40]), doctor.out


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
