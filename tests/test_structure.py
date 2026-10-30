"""The reuse check (docs/decisions.md, "New guards", 2026-10-13): a guard is
written against the shared layer, Document for the call, scan for the words,
paths for path words, verdict for the answer, messages for the sentences. A
primitive two guards would share lands there first. This test reads the
guards as modules and source and fails on the slip that rule names: a constant
a guard keeps that the shared layer already holds, one that two guards keep,
a call field read from the payload that Document already read, a sentence
said outside messages.

The KNOWN tables hold today's copies as ceilings, as tests/test_purity.py
holds its known escapes: a copy beyond them fails the run, and one that goes
passes, so a refactor elsewhere never turns this test red. An entry is pruned
by whoever notices it is stale.
"""

import ast
import importlib
import re
from collections import Counter
from pathlib import Path

from hamcrest import assert_that, empty, equal_to

ROOT = Path(__file__).resolve().parent.parent
GUARDS = {f.stem: importlib.import_module(f"languette.guards.{f.stem}")
          for f in sorted((ROOT / "languette" / "guards").glob("*.py")) if f.stem != "__init__"}
SHARED = {m: importlib.import_module(f"languette.{m}") for m in ("scan", "paths", "verdict", "document", "secrets")}

# The fields of the call Document reads once; a guard reads them from the Document.
DOCUMENT_FIELDS = {"tool_name", "tool_input", "hook_event_name", "permission_mode"}
# What a guard answers with; its text comes from messages.say.
ANSWERS = {"Refuse", "deny", "ask", "context"}

# A constant two or more guards keep: the names, as one set each; a found set
# must fall inside one of these.
KNOWN_TWICE = {
    frozenset({"guard_bypass_labels.GH", "guard_bypass_ruleset._GH", "guard_cross_session_send._GH",
               "guard_duplicate_prs.GH", "guard_github_issues.GH", "guard_private_terms.GH",
               "guard_review_threads.GH", "guard_signed_comments.GH"}),
    frozenset({"guard_bypass_ruleset._GITHUB", "guard_duplicate_prs._GITHUB"}),
    frozenset({"guard_bypass_ruleset._VAR", "guard_signed_comments._VAR"}),
    frozenset({"guard_permissions._FIND", "guard_recursive_delete._FIND"}),
}
# Reads of a DOCUMENT_FIELDS key from the payload, at most, per guard.
KNOWN_PAYLOAD_READS = {"guard_bypass_labels": 2, "guard_cross_session_send": 8, "guard_duplicate_prs": 2,
                       "guard_github_issues": 3, "guard_private_terms": 3, "guard_signed_comments": 2,
                       "guard_worktrees": 4, "prose_budget_commit": 2}
# Answers whose text is anything but a messages.say call, at most, per guard.
KNOWN_INLINE_TEXT = {"ask_first": 2, "guard_bypass_labels": 12, "guard_bypass_ruleset": 10, "guard_cross_session_send": 2,
                     "guard_duplicate_prs": 4, "guard_git_work_loss": 20, "guard_permissions": 1,
                     "guard_secrets": 9, "guard_worktrees": 2,
                     "prose_budget_commit": 1}


def _imported(tree):
    """The names a module binds by import: an import is a use of the shared thing, never a copy."""
    return {a.asname or a.name.split(".")[0] for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}


def _constants(mod, skip=()):
    """The module's string sets, string sequences and compiled patterns, by name, as comparable values."""
    out = {}
    for k, v in vars(mod).items():
        if k.startswith("__") or k in skip:
            continue
        if isinstance(v, (frozenset, set)) and v and all(isinstance(x, str) for x in v):
            out[k] = ("set", frozenset(v))
        elif isinstance(v, re.Pattern):
            out[k] = ("re", v.pattern, v.flags)
        elif isinstance(v, (tuple, list)) and v and all(isinstance(x, str) for x in v):
            out[k] = ("seq", tuple(v))
    return out


def _guard_constants():
    """guard.NAME -> value, for the constants a guard makes itself (re.compile caches equal
    patterns, so identity cannot tell a copy from an import; the source can)."""
    return {f"{g}.{k}": v for g, mod in GUARDS.items()
            for k, v in _constants(mod, skip=_imported(_source(g))).items()}


def _source(g):
    return ast.parse((ROOT / "languette" / "guards" / f"{g}.py").read_text())


def _key(n):
    """The string key a subscript or .get() reads, or None."""
    if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant):
        return n.slice.value
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
            and n.args and isinstance(n.args[0], ast.Constant)):
        return n.args[0].value
    return None


def _answer_text(n):
    """The text node a Refuse/deny/ask/context call is given, first positional or first keyword, or None."""
    if not isinstance(n, ast.Call):
        return None
    name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else None
    if name not in ANSWERS:
        return None
    return n.args[0] if n.args else next((k.value for k in n.keywords), None)


def _over(found, ceilings):
    """The guards past their ceiling, with what was found."""
    return {g: n for g, n in found.items() if n > ceilings.get(g, 0)}


def _said(n):
    return isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "say"


def test_no_guard_keeps_a_constant_the_shared_layer_holds():
    shared = {v: f"{m}.{k}" for m, mod in SHARED.items() for k, v in _constants(mod).items()}
    found = {name: shared[v] for name, v in _guard_constants().items() if v in shared}
    assert_that(found, equal_to({}))


def test_no_two_guards_keep_the_same_constant():
    by_value = {}
    for name, v in _guard_constants().items():
        by_value.setdefault(v, set()).add(name)
    found = [names for names in by_value.values() if len(names) > 1]
    assert_that(sorted(sorted(n) for n in found if not any(n <= k for k in KNOWN_TWICE)), empty())


def test_every_guard_has_its_feature():
    missing = [mod.NAME for mod in GUARDS.values() if not (ROOT / "features" / f"{mod.NAME}.feature").is_file()]
    assert_that(missing, empty())


def test_a_guard_reads_the_call_through_the_document():
    found = Counter()
    for g in GUARDS:
        found[g] += sum(_key(n) in DOCUMENT_FIELDS for n in ast.walk(_source(g)))
    assert_that(_over(found, KNOWN_PAYLOAD_READS), equal_to({}))


def test_a_guard_says_its_text_through_messages():
    found = Counter()
    for g in GUARDS:
        for t in map(_answer_text, ast.walk(_source(g))):
            if t is not None and not _said(t):
                found[g] += 1
    assert_that(_over(found, KNOWN_INLINE_TEXT), equal_to({}))
