"""The README's failure-mode table, from the @table scenario in
features/no-rm-tree.feature. Run it to regenerate the table in README.md;
it prints the table too. Standard library only, so plain python3 runs it."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE = ROOT / "features/no-rm-tree.feature"
README = ROOT / "README.md"
BLOCK = re.compile(r"(<!-- fixtures-table -->\n)(.*?)(<!-- /fixtures-table -->)", re.S)


def _cells(line):
    # A Gherkin table row; \| is a pipe inside a cell, \\ a backslash, \n a newline.
    out, cur, i, s = [], "", 0, line.strip()[1:]
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            cur += {"n": "\n", "|": "|", "\\": "\\"}.get(s[i + 1], c + s[i + 1])
            i += 2
            continue
        if c == "|":
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    return out


def rows():
    """[{command, verdict, why}] of the @table scenario's examples."""
    lines = FEATURE.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == "@table")
    table = []
    for ln in lines[start + 1:]:
        if ln.strip().startswith("|"):
            table.append(_cells(ln))
        elif table:
            break
    head = table[0]
    return [dict(zip(head, r)) for r in table[1:]]


def table():
    out = ["| Command | Verdict | Why |", "|---|---|---|"]
    for r in rows():
        v = "DENY" if r["verdict"].startswith("denies") else "allow" if r["verdict"] == "is silent" else r["verdict"]
        out.append(f"| `{r['command']}` | {v} | {r['why']} |")
    return "\n".join(out) + "\n"


def in_readme():
    m = BLOCK.search(README.read_text())
    return m.group(2) if m else None


if __name__ == "__main__":
    t = table()
    README.write_text(BLOCK.sub(lambda m: m.group(1) + t + m.group(3), README.read_text(), count=1))
    sys.stdout.write(t)
