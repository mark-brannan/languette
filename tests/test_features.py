"""Every scenario in features/ but smoke.feature, once per engine (see
conftest.py). smoke.feature builds its own PATHs: CI's smoke job runs it,
through smoke_steps.py."""

from pathlib import Path

from pytest_bdd import scenarios

FEATURES = Path(__file__).resolve().parent.parent / "features"
scenarios(*sorted(p.name for p in FEATURES.glob("*.feature") if p.name != "smoke.feature"))
