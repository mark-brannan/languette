"""Steps for features/config.feature: `python3 -m languette config` run by subprocess against
the doctor's fake HOME (doctor_steps.py), its `claude` stub answering `plugin configure` as
the host does. conftest.py imports these, so pytest-bdd finds them."""

import json

from hamcrest import assert_that, equal_to
from pytest_bdd import parsers, then, when

from doctor_steps import PLUGIN_ID


def _held(doctor):
    return doctor.settings().get("pluginConfigs", {}).get(PLUGIN_ID, {}).get("options", {})


@when(parsers.re(r"languette config runs(?: with `(?P<args>[^`]+)`)?"))
def _config_runs(doctor, args):
    doctor.run(doctor.home / "project", *(args or "").split(), command="config")


@then(parsers.re(r"the stored options are `(?P<options>[^`]*)`"))
def _stored(doctor, options):
    assert_that(_held(doctor), equal_to(json.loads(options)), doctor.out + doctor.err)


@then(parsers.re(r'it lists "(?P<name>\w+)" as "(?P<value>[^"]*)", (?P<where>.+)'))
def _lists(doctor, name, value, where):
    rows = [ln.split(None, 2) for ln in doctor.out.splitlines()]
    want = [name, value, doctor.expand(where).replace(str(doctor.home), "~")]
    assert_that([r for r in rows if r[:1] == [name]], equal_to([want]), doctor.out + doctor.err)


@then(parsers.re(r"it lists every option in the manifest, in its order"))
def _lists_all(doctor):
    from doctor_steps import ROOT
    names = list(json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["userConfig"])
    assert_that([ln.split()[0] for ln in doctor.out.splitlines()], equal_to(names))
