"""Fail when a change adds a guard whose name is not in the approved table.

Usage: python3 tests/new_guard_names.py <base-ref>

A guard is new when its NAME is in the working tree's languette/guards/ but
not in the base's. The table is docs/decisions.md's "Approved guard names"
section, read from the base, so a change cannot approve its own guard.
Guards that already exist are not checked. Standard library only."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^NAME = "([^"]+)"$', re.M)
ROW = re.compile(r"^\| `([^`]+)` \|", re.M)


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def names_at(base):
    return set(NAME.findall(_git("grep", "-h", "^NAME = ", base, "--", "languette/guards/")))


def names_here():
    return {n for p in (ROOT / "languette/guards").glob("*.py") for n in NAME.findall(p.read_text())}


def approved(decisions):
    section = re.search(r"^## Approved guard names.*?(?=^## |\Z)", decisions, re.M | re.S)
    return set(ROW.findall(section.group(0))) if section else set()


def main(base):
    table = approved(_git("show", f"{base}:docs/decisions.md"))
    bad = sorted(names_here() - names_at(base) - table)
    for name in bad:
        print(
            f"::error file=docs/decisions.md::New guard `{name}` is not in the "
            "approved guard names table in docs/decisions.md. Name it after a "
            "row there, or get the name approved first, in its own change."
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
