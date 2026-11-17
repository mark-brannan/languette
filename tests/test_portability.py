"""Rule 1 of docs/design/portability.md: nothing in the package, the hooks,
the feature files, the tests, the README or the docs names the maintainer or
the maintainer's setup. The project's own homepage, install coordinates and
issue links are the one exception, and so is the maintainer's handle on the
attribution line of docs/decisions.md, which names whose decisions they are.

The same holds for the names of the maintainer's own tools, over what ships
(the package, the hooks, the plugin manifest, the specs, the README and the
design docs): a shipped guard must not know them. Dated records and research
notes may name a tool that was once shipped.

A denylist, not a proof: it catches the identifier that slips into a fixture,
not every way a setup can leak."""

import re
from pathlib import Path

from hamcrest import assert_that, empty
from paths import ROOT

DIRS = ("languette", "hooks", ".claude-plugin", "features", "tests", "docs", "README.md")
# What ships, or specifies what ships; docs/decisions.md and the research notes are dated records.
SHIPPED = ("languette", "hooks", ".claude-plugin", "features", "tests", "docs/design", "docs/messages.md", "README.md")
# The maintainer's identifiers, and the words of the workflow languette was born in.
DENY = re.compile(r"mark-brannan|markbrannan|solace|claude_prompts_scratch"
                  r"|claim.?stamp|\bcuria\b|\bagora\b", re.IGNORECASE)
# The maintainer's own tools, which a shipped guard must not call, name or configure.
TOOLS = re.compile(r"prose[-_ ]?budget|work-item|worker-start|pickup-list|agent-decision|apply-edits", re.IGNORECASE)
# The project's own homepage, install coordinates, and links to its own issues and pull requests.
ALLOW = re.compile(r"(?:https://github\.com/)?mark-brannan/(?:tap/languette|languette(?:/(?:issues|pull)/\d+|#\w+)?)\b")
ATTRIBUTION = ("docs/decisions.md", "line is the maintainer's (@mark-brannan) unless it says otherwise.")


def _hits(dirs=DIRS, deny=DENY):
    for d in dirs:
        for f in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else [ROOT / d]:
            if not f.is_file() or f == Path(__file__).resolve() or "__pycache__" in f.parts:
                continue
            try:
                text = f.read_text()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if (str(f.relative_to(ROOT)), line) == ATTRIBUTION:
                    continue
                if deny.search(ALLOW.sub("", line)):
                    yield f"{f.relative_to(ROOT)}:{n}: {line.strip()[:120]}"


def test_no_maintainer_identity_in_package_hooks_specs_tests_or_docs():
    assert_that(list(_hits()), empty())


def test_no_maintainer_tooling_in_what_ships():
    assert_that(list(_hits(SHIPPED, TOOLS)), empty())
