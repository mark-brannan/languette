"""The message catalog (languette/messages.py): a guard says a message by code,
and the code and its blanks must exist. Read as source, never run."""

import ast
import importlib
import string
from pathlib import Path

from hamcrest import assert_that, empty, equal_to

from languette.messages import MESSAGES

ROOT = Path(__file__).resolve().parent.parent / "languette"


def _calls():
    """(file, line, code, blanks or None when **kwargs hides them) for every say("code", ...).
    The rules engine says a rule's `why`: its one such call stands for each shipped rule's, with
    that call's blanks, at line 0 of the rule set's file."""
    found, rule_said = [], []
    for f in sorted(ROOT.rglob("*.py")):
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "say" and n.args:
                code = n.args[0].value if isinstance(n.args[0], ast.Constant) else None
                blanks = None if any(k.arg is None for k in n.keywords) else {k.arg for k in n.keywords}
                if code is None and f.name == "engine.py":
                    rule_said.append(blanks)
                    continue
                found.append((f.name, n.lineno, code, blanks))
    assert len(rule_said) == 1, f"the engine says a rule's why {len(rule_said)} times, want once"
    for f in sorted((ROOT / "rules").glob("*.py")):
        if f.name != "__init__.py":
            rule_set = importlib.import_module(f"languette.rules.{f.stem}").RULE_SET
            found += [(f.name, 0, r["why"], rule_said[0]) for r in rule_set["rules"]]
    return found


def _blanks(template):
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_every_message_said_exists_and_gets_exactly_its_blanks():
    bad = []
    for f, line, code, blanks in _calls():
        if code not in MESSAGES:
            bad.append(f"{f}:{line} says {code!r}, which the catalog lacks")
        elif blanks is not None and blanks != _blanks(MESSAGES[code]):
            bad.append(f"{f}:{line} fills {sorted(blanks)} but {code!r} has {sorted(_blanks(MESSAGES[code]))}")
    assert_that(bad, empty())


def test_every_message_in_the_catalog_is_said_somewhere():
    said = {code for _, _, code, _ in _calls()}
    assert_that(sorted(set(MESSAGES) - said), empty())


def test_a_blank_with_braces_in_it_is_filled_as_text():
    from languette.messages import say
    assert_that(say("payload_unreadable", err="{x}"), equal_to("languette: unreadable hook payload ({x})"))


def test_the_listing_page_is_the_catalog():
    from languette.messages import listing
    page = ROOT.parent / "docs" / "messages.md"
    assert_that(page.read_text(), equal_to(listing()), "regenerate: python -m languette.messages > docs/messages.md")
