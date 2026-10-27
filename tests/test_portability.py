"""Rule 1 of docs/design/portability.md: nothing in the package, the hooks,
the feature files, the tests, the README or the docs names the maintainer or
the maintainer's setup. The project's own homepage, install coordinates and
issue links are the one exception.

A denylist, not a proof: it catches the identifier that slips into a fixture,
not every way a setup can leak."""

import re
from pathlib import Path

from hamcrest import assert_that, empty

ROOT = Path(__file__).resolve().parent.parent
DIRS = ("languette", "hooks", "features", "tests", "docs", "README.md")
# The maintainer's identifiers, and the words of the workflow languette was born in.
DENY = re.compile(r"mark-brannan|markbrannan|solace|claude_prompts_scratch"
                  r"|claim.?stamp|\bcuria\b|\bagora\b", re.IGNORECASE)
# The project's own homepage, install coordinates, and links to its own issues and pull requests.
ALLOW = re.compile(r"(?:https://github\.com/)?mark-brannan/(?:tap/languette|languette(?:/(?:issues|pull)/\d+|#\w+)?)\b")


def _hits():
    for d in DIRS:
        for f in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else [ROOT / d]:
            if not f.is_file() or f == Path(__file__).resolve() or "__pycache__" in f.parts:
                continue
            try:
                text = f.read_text()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if DENY.search(ALLOW.sub("", line)):
                    yield f"{f.relative_to(ROOT)}:{n}: {line.strip()[:120]}"


def test_no_maintainer_identity_in_package_hooks_specs_tests_or_docs():
    assert_that(list(_hits()), empty())
