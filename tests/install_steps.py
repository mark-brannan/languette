"""Steps for features/install.feature and features/uninstall.feature:
`python3 -m languette install` or `uninstall` run by subprocess against a fake HOME of its own, with a stub `claude` first on PATH
that records each command it is asked and answers from canned output.
conftest.py imports these, so pytest-bdd finds them."""

import json
import os
import shlex

import pytest
from hamcrest import assert_that, contains_string, equal_to, has_item, not_
from pytest_bdd import given, parsers, then, when

from harness import FakeHome
from languette.host import PLUGIN, REPO, SOURCE
from paths import ROOT



class Install(FakeHome):
    def __init__(self):
        super().__init__("install", ("project",))
        self.log = self.aside / "asked"
        self.claude = True
        self.plugins, self.marketplaces = [], []
        self.add = (0, "")                     # exit code and stderr of `claude plugin marketplace add`
        self.after_add = [{"name": "languette", "source": "github", "repo": REPO}]   # what list shows after an add
        self.remove = (0, "")                  # exit code and stderr of `claude plugin uninstall`
        self.list_fails = False                # whether `claude plugin marketplace list` exits 1
        self.answer = None                     # what uninstall reads on stdin

    def stub(self):
        listed, after = self.aside / "marketplaces.json", self.aside / "after-add.json"
        listed.write_text(json.dumps(self.marketplaces))
        after.write_text(json.dumps(self.after_add))
        # As Claude Code does, an uninstall drops the plugin's options from the user's settings.
        settings, dropped = self.home / ".claude/settings.json", self.aside / "settings-after-uninstall.json"
        held = json.loads(settings.read_text()) if settings.exists() else {}
        held.get("pluginConfigs", {}).pop(PLUGIN, None)
        dropped.write_text(json.dumps(held))
        drop = f"cp {shlex.quote(str(dropped))} {shlex.quote(str(settings))};" if settings.exists() else ""
        # An add, even one that answers "already", leaves the list as after_add says.
        answers = {"plugin list --json": (0, json.dumps(self.plugins), "", ""),
                   "plugin marketplace list --json": ((1, "", "boom", "") if self.list_fails
                                                      else (0, "", "", f"cat {shlex.quote(str(listed))};")),
                   f"plugin marketplace add {SOURCE}": (self.add[0], "", self.add[1],
                                                        f"cp {shlex.quote(str(after))} {shlex.quote(str(listed))};"),
                   "plugin install languette@languette": (0, "Installed languette", "", ""),
                   f"plugin uninstall {PLUGIN} --scope user": (self.remove[0], "", self.remove[1],
                                                                          "" if self.remove[0] else drop),
                   "plugin marketplace remove languette --scope user": (0, "Removed languette", "", "")}
        cases = "".join(f"  {shlex.quote(asked)}) {run} printf '%s' {shlex.quote(out)}; "
                        f"printf '%s' {shlex.quote(err)} >&2; exit {code};;\n"
                        for asked, (code, out, err, run) in answers.items())
        f = self.bin / "claude"
        f.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> {shlex.quote(str(self.log))}\ncase "$*" in\n{cases}'
                     "  *) exit 2;;\nesac\n")
        f.chmod(0o755)

    def run(self, *args, command="install"):
        if self.claude:
            self.stub()
        self.log.write_text("")
        # Without the real PATH, so the real claude is never found: only the stub's directory and the system's.
        self.invoke([command, *args], self.home / "project", f"/usr/bin{os.pathsep}/bin", self.answer)


def _expand(text, home=None):
    text = text.replace("{SOURCE}", SOURCE).replace("{REPO}", REPO)
    return text.replace("{HOME}", str(home)) if home else text


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


@given(parsers.parse('claude lists languette "{version}" installed at project scope for "{project}"'))
def _listed_project(installer, version, project):
    installer.plugins.append({"id": PLUGIN, "version": version, "scope": "project", "enabled": True,
                              "installPath": str(ROOT), "projectPath": _expand(project, installer.home)})


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


@given(parsers.parse('claude plugin uninstall fails with "{err}"'))
def _remove_fails(installer, err):
    installer.remove = (1, err + "\n")


@given("claude's marketplace list fails")
def _list_fails(installer):
    installer.list_fails = True


@given(parsers.parse("the user's settings hold the languette options `{options}`"))
def _options_held(installer, options):
    f = installer.home / ".claude/settings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pluginConfigs": {PLUGIN: {"options": json.loads(options)}}}))


@then("the user's settings are as Claude Code's uninstall left them")
def _settings_as_claude_left(installer):
    left = (installer.aside / "settings-after-uninstall.json").read_text()
    assert_that(json.loads((installer.home / ".claude/settings.json").read_text()), equal_to(json.loads(left)))


@then(parsers.parse('uninstall said before asking "{text}"'))
def _said_before(installer, text):
    head, _, _ = installer.out.partition("Remove them? [y/N] ")
    assert_that(head.splitlines(), has_item(text))


@then(parsers.parse("the user's settings hold the languette options `{options}`"))
def _options_still(installer, options):
    s = json.loads((installer.home / ".claude/settings.json").read_text())
    assert_that(s["pluginConfigs"][PLUGIN], equal_to({"options": json.loads(options)}))


TERMS = ".config/languette/redacted-terms.tsv"


@given(parsers.parse('the redacted terms file holds "{text}"'))
def _terms_held(installer, text):
    f = installer.home / TERMS
    f.parent.mkdir(parents=True)
    f.write_text(text.replace("\\t", "\t"))
    installer.held = f.read_text()


@given("the redacted terms path is a file, not a directory")
def _terms_blocked(installer):
    (installer.home / ".config").write_text("")


@then("the redacted terms file starts with the redacted header")
def _terms_header(installer):
    assert_that((installer.home / TERMS).read_text(), contains_string("find\t"))


@then("the redacted terms file is unchanged")
def _terms_unchanged(installer):
    assert_that((installer.home / TERMS).read_text(), equal_to(installer.held))
    assert_that(installer.out, not_(contains_string("redacted terms")))


@when("install runs")
def _runs(installer):
    installer.run()


@when(parsers.parse('install runs for "{host}"'))
def _runs_for(installer, host):
    installer.run(host)


@when(parsers.re(r'uninstall runs, answering "(?P<answer>[^"]*)"'))
def _uninstall_runs(installer, answer):
    installer.answer = answer + "\n" if answer else None
    installer.run(command="uninstall")


@when(parsers.parse('uninstall runs for "{host}"'))
def _uninstall_runs_for(installer, host):
    installer.run(host, command="uninstall")


@then("uninstall listed, before asking:")
def _listed_before(installer, docstring):
    head, asked, _ = installer.out.partition("Remove them? [y/N] ")
    assert_that(asked, equal_to("Remove them? [y/N] "), installer.out)
    listed = [ln.strip() for ln in head.splitlines() if ln.startswith("  ")]
    assert_that(listed, equal_to([ln.strip() for ln in _expand(docstring).splitlines()]))


@then("uninstall did not ask")
def _not_asked(installer):
    assert_that(installer.out, not_(contains_string("Remove them?")))


@then(parsers.re(r'the (?:un)?install "(?P<label>[^"]+)" row is (?P<mark>[✓!✗]) "(?P<text>.*)"'))
def _row(installer, label, mark, text):
    installer.assert_row(label, mark, _expand(text))


@then("claude was asked only:")
def _asked(installer, docstring):
    assert_that(installer.log.read_text().splitlines(), equal_to(_expand(docstring).splitlines()))


@then("claude was asked nothing")
def _asked_nothing(installer):
    assert_that(installer.log.read_text(), equal_to(""))


@then(parsers.re(r"(?:un)?install exits (?P<code>\d+)"), converters={"code": int})
def _exits(installer, code):
    installer.assert_exit(code)


@then(parsers.re(r'(?:un)?install says on stderr "(?P<text>.*)"'))
def _stderr(installer, text):
    assert_that(installer.err, contains_string(text))


@then(parsers.re(r"the fake HOME is as it was before (?:un)?install"))
def _home_untouched(installer):
    installer.assert_untouched()


# What conftest.py takes: the fixture and the step fixtures pytest-bdd made above.
__all__ = ["installer"] + [k for k in list(globals()) if k.startswith("pytestbdd_")]
