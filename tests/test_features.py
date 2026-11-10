"""Every scenario in features/ but smoke.feature, once per engine (see
conftest.py). smoke.feature builds its own PATHs: CI's smoke job runs it,
through smoke_steps.py."""

from pytest_bdd import scenarios
from paths import ROOT

FEATURES = ROOT / "features"
scenarios(*sorted(p.name for p in FEATURES.glob("*.feature") if p.name != "smoke.feature"))
