"""Fail when a change adds a guard whose name is not in the approved table.

Usage: python3 tests/new_guard_names.py <base-ref>

A guard is new when its NAME is in the working tree's languette/guards/ but
not in the base's. The approved names are the first table under a heading
"Approved guard names" in any markdown file under docs/, read from the base,
so a change cannot approve its own guard and the table can move files.
Guards that already exist are not checked. Standard library only."""

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDS = "languette/guards"
HEADING = re.compile(r"^#+ .*approved guard names", re.M | re.I)
TABLE = re.compile(r"(?:^\|.*\n?)+", re.M)
ROW = re.compile(r"^\| `([^`]+)` \|", re.M)


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def _names(src):
    # Parsed, not matched: `NAME: str = 'x'  # why` registers a guard too.
    out = set()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "NAME" for t in targets):
            out.add(ast.literal_eval(node.value))
    return out


def names_at(base):
    paths = _git("ls-tree", "-r", "--name-only", base, "--", f"{GUARDS}/").split()
    return {n for p in paths if p.endswith(".py") for n in _names(_git("show", f"{base}:{p}"))}


def names_here():
    out, unnamed = set(), []
    for p in sorted((ROOT / GUARDS).rglob("*.py")):
        found = _names(p.read_text())
        if not found and p.name != "__init__.py":
            unnamed.append(p.relative_to(ROOT))
        out |= found
    return out, unnamed


def approved(base):
    for path in _git("ls-tree", "-r", "--name-only", base, "--", "docs/").split():
        if not path.endswith(".md"):
            continue
        text = _git("show", f"{base}:{path}")
        heading = HEADING.search(text)
        table = heading and TABLE.search(text, heading.end())
        if table:
            return set(ROW.findall(table.group(0)))
    return None


def main(base):
    table = approved(base)
    if table is None:
        print("::error::No \"Approved guard names\" table found under docs/ at the base.")
        return 1
    here, unnamed = names_here()
    for path in unnamed:
        print(f"::error file={path}::Guard module defines no NAME.")
    bad = sorted(here - names_at(base) - table)
    for name in bad:
        print(
            f"::error::New guard `{name}` is not in the approved guard names "
            "table under docs/. Name it after a row there, or get the name "
            "approved first, in its own change."
        )
    return 1 if bad or unnamed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
