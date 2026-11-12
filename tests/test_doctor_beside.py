"""sandbox.enabledPlatforms, which Claude Code reads from managed settings alone: a path under /etc
the feature's sandboxed runs cannot write, so its layers are handed to the doctor here."""
from pathlib import Path

import pytest

from languette import doctor, host

MANAGED = Path("/etc/claude-code/managed-settings.json")
ON = {"sandbox": {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}}


@pytest.mark.parametrize("scope, platforms, mark", [
    ("managed", ["macos"], doctor.WARN),
    ("managed", ["linux"], doctor.OK),
    ("user", ["macos"], doctor.OK),            # Claude Code ignores it outside managed settings
])
def test_enabled_platforms_from_managed_settings_alone(monkeypatch, tmp_path, scope, platforms, mark):
    box = {"sandbox": {"enabledPlatforms": platforms}}
    layers = [("managed", MANAGED, box if scope == "managed" else {}),
              ("user", tmp_path / "settings.json", {"sandbox": {**ON["sandbox"], **(box["sandbox"] if scope == "user" else {})}})]
    monkeypatch.setattr(host, "layers", lambda cwd: layers)
    monkeypatch.setattr(host, "platform", lambda: "linux")
    monkeypatch.setattr(host, "managed_dropins", lambda: [])
    [sandbox] = [r for r in doctor.beside_rows(tmp_path) if r[1] == "sandbox"]
    assert sandbox[0] == mark, sandbox


def test_a_managed_drop_in_makes_the_sandbox_row_a_warning(monkeypatch, tmp_path):
    layers = [("user", tmp_path / "settings.json", ON)]
    monkeypatch.setattr(host, "layers", lambda cwd: layers)
    monkeypatch.setattr(host, "managed_dropins", lambda: [MANAGED.parent / "managed-settings.d/10-org.json"])
    [sandbox] = [r for r in doctor.beside_rows(tmp_path) if r[1] == "sandbox"]
    assert sandbox[0] == doctor.WARN and any("does not merge" in text for _, text, _ in sandbox[3]), sandbox
