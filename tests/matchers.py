"""PyHamcrest matchers that speak the promise: a guard denies, asks, warns
or says nothing. A mismatch prints the guard's raw output and its reason."""

import json
from dataclasses import dataclass, field

from hamcrest.core.base_matcher import BaseMatcher


@dataclass
class Verdict:
    """What one run of a guard produced."""
    stdout: str
    code: int = 0
    stderr: str = ""
    json: dict | None = field(default=None, init=False)
    error: str | None = field(default=None, init=False)

    def __post_init__(self):
        if self.stdout.strip():
            try:
                self.json = json.loads(self.stdout)
            except ValueError as e:
                self.error = f"not JSON ({e})"

    @property
    def out(self):
        h = (self.json or {}).get("hookSpecificOutput") if isinstance(self.json, dict) else None
        return h if isinstance(h, dict) else {}

    @property
    def decision(self):
        return self.out.get("permissionDecision")

    @property
    def reason(self):
        return self.out.get("permissionDecisionReason", "")

    def show(self):
        lines = [f"exit {self.code}, stdout {self.stdout!r}"]
        if self.error:
            lines.append(self.error)
        if self.reason:
            lines.append(f"reason: {self.reason}")
        if self.stderr:
            lines.append(f"stderr: {self.stderr!r}")
        return "\n     ".join(lines)


class _Decides(BaseMatcher):
    def __init__(self, decision, naming=None):
        self.want, self.naming = decision, naming

    def _matches(self, v):
        return (v.code == 0 and v.error is None and v.out.get("hookEventName") == "PreToolUse"
                and v.decision == self.want and (self.naming is None or self.naming in v.reason))

    def describe_to(self, d):
        d.append_text(f"a PreToolUse {self.want}")
        if self.naming is not None:
            d.append_text(f" whose reason names {self.naming!r}")

    def describe_mismatch(self, v, d):
        d.append_text(v.show())


class _Silent(BaseMatcher):
    def _matches(self, v):
        return v.code == 0 and v.stdout == ""

    def describe_to(self, d):
        d.append_text("no output and exit 0")

    def describe_mismatch(self, v, d):
        d.append_text(v.show())


class _Warns(BaseMatcher):
    def __init__(self, text):
        self.text = text

    def _matches(self, v):
        return (v.code == 0 and v.error is None and v.out.get("hookEventName") == "PreToolUse"
                and "permissionDecision" not in v.out and self.text in v.out.get("additionalContext", ""))

    def describe_to(self, d):
        d.append_text(f"a PreToolUse warning, with no decision, whose context names {self.text!r}")

    def describe_mismatch(self, v, d):
        d.append_text(v.show())
        if v.out.get("additionalContext"):
            d.append_text(f"\n     context: {v.out['additionalContext']}")


def denies(naming=None):
    return _Decides("deny", naming)


def asks(naming=None):
    return _Decides("ask", naming)


def is_silent():
    return _Silent()


def warns_about(text):
    return _Warns(text)
