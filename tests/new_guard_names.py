"""Fail when a change adds a guard whose name is not in the approved table.

Usage: python3 tests/new_guard_names.py <base-ref>

A guard is new when its NAME is in the working tree's languette/guards/ but
not in the base's. The approved names are the first table under a heading
"Approved guard names" in any markdown file under docs/, read from the base,
so a change cannot approve its own guard and the table can move files.
Guards that already exist are not checked. The first cell of a table row
must be exactly one backticked name, `| `name` | ...`; anything else is not
read as a name. Standard library only."""

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDS = "languette/guards"
HEADING = re.compile(r"^#+ approved guard names", re.M | re.I)
ANY_HEADING = re.compile(r"^#+ ", re.M)
TABLE = re.compile(r"(?:^\|.*\n?)+", re.M)
ROW = re.compile(r"^\| `([^`]+)` \|", re.M)


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


class BadName(Exception):
    pass


def _names(src):
    # Parsed, not matched: `NAME: str = 'x'  # why` registers a guard too.
    out = set()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise BadName(f"Does not parse: {e.msg}")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "NAME" for t in targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                raise BadName("NAME is not a string literal")
            if not isinstance(value, str):
                raise BadName("NAME is not a string literal")
            out.add(value)
    return out


def base_guard_paths(base):
    return _git("ls-tree", "-r", "--name-only", base, "--", f"{GUARDS}/").split()


def names_at(base):
    return {
        n
        for p in base_guard_paths(base)
        if p.endswith(".py")
        for n in _names(_git("show", f"{base}:{p}"))
    }


def names_here(base):
    # A nameless module is an error only when it is new: an existing helper
    # module (say guards/_util.py) is not this PR's doing.
    existing = set(base_guard_paths(base))
    out, errors = set(), []
    for p in sorted((ROOT / GUARDS).rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if p.name == "__init__.py" or rel in existing:
            continue
        try:
            found = _names(p.read_text())
        except BadName as e:
            errors.append(f"::error file={rel}::{e}.")
            continue
        if not found:
            errors.append(f"::error file={rel}::Guard module defines no NAME.")
        out |= found
    return out, errors


def approved(base):
    for path in _git("ls-tree", "-r", "--name-only", base, "--", "docs/").split():
        if not path.endswith(".md"):
            continue
        text = _git("show", f"{base}:{path}")
        heading = HEADING.search(text)
        if not heading:
            continue
        # The table must sit under its heading, before the next heading of any level.
        nxt = ANY_HEADING.search(text, heading.end())
        section = text[heading.end(): nxt.start() if nxt else len(text)]
        table = TABLE.search(section)
        if table:
            return set(ROW.findall(table.group(0)))
    return None


def main(base):
    table = approved(base)
    if table is None:
        print("::error::No \"Approved guard names\" table found under docs/ at the base.")
        return 1
    try:
        here, errors = names_here(base)
        existing = names_at(base)
    except BadName as e:
        print(f"::error::Base guard module {e}.")
        return 1
    for line in errors:
        print(line)
    bad = sorted(here - existing - table)
    for name in bad:
        print(
            f"::error::New guard `{name}` is not in the approved guard names "
            "table under docs/. Name it after a row there, or get the name "
            "approved first, in its own change."
        )
    return 1 if bad or errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
