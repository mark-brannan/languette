"""Fail when a change adds a guard whose name is not in the approved table.

Usage: python3 tests/new_guard_names.py <base-ref>

A guard is new when its NAME is in the working tree's languette/guards/ but
not in the base's. The approved names are the first table under a heading
"Approved guard names" in any markdown file under docs/, read from the base,
so a change cannot approve its own guard and the table can move files.
Guards that already exist are not checked. Standard library only."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = re.compile(r'^NAME = "([^"]+)"$', re.M)
HEADING = re.compile(r"^#+ .*approved guard names", re.M | re.I)
TABLE = re.compile(r"(?:^\|.*\n?)+", re.M)
ROW = re.compile(r"^\| `([^`]+)` \|", re.M)


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def names_at(base):
    return set(NAME.findall(_git("grep", "-h", "^NAME = ", base, "--", "languette/guards/")))


def names_here():
    return {n for p in (ROOT / "languette/guards").glob("*.py") for n in NAME.findall(p.read_text())}


def approved(base):
    for path in _git("ls-tree", "-r", "--name-only", base, "--", "docs/").split():
        if not path.endswith(".md"):
            continue
        text = _git("show", f"{base}:{path}")
        heading = HEADING.search(text)
        table = heading and TABLE.search(text, heading.end())
        if table:
            return set(ROW.findall(table.group(0)))
    return set()


def main(base):
    table = approved(base)
    bad = sorted(names_here() - names_at(base) - table)
    for name in bad:
        print(
            f"::error::New guard `{name}` is not in the approved guard names "
            "table under docs/. Name it after a row there, or get the name "
            "approved first, in its own change."
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
