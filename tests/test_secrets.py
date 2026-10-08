"""languette/secrets.py: every shape in a word is found and masked, a data
line's findings land on its own index, and shown() echoes at most a quarter of
a value, and a project regex has a length cap. Samples are built at runtime, as in test_secret_rules.py, so no literal
token sits in the repo."""

import json
import random
import string

import pytest

from languette import scan as sw
from languette import secrets
from languette.guards import guard_secrets
from languette.verdict import Refuse

_R = random.Random(20261007)


def pat():
    return "ghp_" + "".join(_R.choice(string.ascii_letters + string.digits) for _ in range(36))  # gitleaks:allow


def test_every_shape_in_one_word_is_found_and_masked():
    one, two = pat(), pat()
    s = secrets.Text(f"a={one},b={two}")
    found = secrets.findings(s)
    assert [(f.index, f.rule, f.how) for f in found] == [(0, "github-pat", "shape")] * 2
    assert secrets.redact(s, found) == ["a=****,b=****"]


def test_a_text_finds_each_line_on_its_own_index():
    s = secrets.Text(f"# config\nGITHUB_TOKEN={pat()}\nname=app\n  password: Zq9kLm2pQ7rXv4Tn\n")  # gitleaks:allow
    assert [(f.index, f.how) for f in secrets.findings(s)] == [(1, "shape"), (3, "context")]


def test_redact_keeps_the_key_and_masks_the_value():
    s = sw.Scan(f"export GITHUB_TOKEN={pat()}")
    assert secrets.redact(s, secrets.findings(s))[-1] == "GITHUB_TOKEN=****"


def test_shown_echoes_at_most_a_quarter_of_the_value():
    for value, shown in (("Zq9kLm2pQ7rXv4Tn", "Zq9k…"), ("Zq9kLm2p", "Zq…")):  # gitleaks:allow
        s = secrets.Text(f"DB_PASSWORD={value}")
        (f,) = secrets.findings(s)
        assert secrets.shown(s, f) == shown
    s = secrets.Text(pat())
    (f,) = secrets.findings(s)
    assert secrets.shown(s, f) == "ghp_…"


def test_a_project_regex_over_512_characters_is_refused():
    load = guard_secrets._load("/p/.languette/secrets.json")
    next(load)
    with pytest.raises(Refuse, match="longer than 512"):
        load.send(json.dumps({"patterns": [{"id": "long", "regex": "a" * 513}]}))


@pytest.mark.parametrize("regex", ["(a+)+$", "(a*)*b", "(\\w+\\s?)+$", "(?:x|(a+))+", "((ab)*)+"])
def test_a_project_regex_nesting_unbounded_repeats_is_refused(regex):
    load = guard_secrets._load("/p/.languette/secrets.json")
    next(load)
    with pytest.raises(Refuse, match="nests one unbounded repeat"):
        load.send(json.dumps({"patterns": [{"id": "slow", "regex": regex}]}))


@pytest.mark.parametrize("regex", ["acme_[a-z0-9]{24}", "(a+)b+", "(?:ab)+c", "(a{1,3})+", "^-----BEGIN .* KEY-----$",
                                   "(?=.*\\d)[A-Za-z0-9]{32,}", "(a|b)*c"])
def test_a_project_regex_with_one_level_of_repeat_is_kept(regex):
    load = guard_secrets._load("/p/.languette/secrets.json")
    next(load)
    try:
        load.send(json.dumps({"patterns": [{"id": "ok", "regex": regex}]}))
    except StopIteration as stop:
        assert [r.id for r in stop.value] == ["ok"]
    else:
        raise AssertionError("_load did not return")
