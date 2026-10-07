"""The parser ladder in languette/scan.py: which rung reads, and what a
refusal, a crash or an old shfmt does. The scenarios in features/ already run
on both rungs (conftest.py); these are the edges between them."""

import json
import os
import re
from pathlib import Path

import pytest

from languette import run, scan

ROOT = Path(__file__).resolve().parent.parent
REAL = scan.shfmt()
needs_shfmt = pytest.mark.skipif(not REAL and not os.environ.get("CI"), reason="no shfmt new enough on PATH")


@pytest.fixture(autouse=True)
def fresh():
    scan.shfmt.cache_clear(); scan._shfmt_tree.cache_clear()
    yield
    scan.shfmt.cache_clear(); scan._shfmt_tree.cache_clear()


def fake_shfmt(tmp_path, monkeypatch, body):
    """A shfmt on PATH that is a shell script, ahead of any real one."""
    f = tmp_path / "shfmt"
    f.write_text("#!/bin/sh\n" + body)
    f.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")


def payload(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": os.environ["HOME"]})


def verdict(command, guard="guard-recursive-delete"):
    out = run.respond(payload(command), {"HOME": os.environ["HOME"]}, only=guard)
    return json.loads(out)["hookSpecificOutput"] if out else None


@needs_shfmt
def test_a_command_shfmt_refuses_is_denied_not_read_by_awk():
    v = verdict("echo 'unclosed")
    assert v["permissionDecision"] == "deny"
    assert "shfmt cannot parse" in v["permissionDecisionReason"]


@needs_shfmt
def test_nested_text_shfmt_refuses_is_read_by_awk():
    # The quoted string may be Python, not shell: no deny for that.
    assert verdict('python3 -c "print(1)"') is None
    assert verdict('mytool --run "rm -rf / (x"')["permissionDecision"] == "deny"   # awk still finds rm


@needs_shfmt
def test_shfmt_reads_quotes_the_awk_rung_splits():
    # The awk rung ends the string at the inner quote: ["w:echo", "q:$(printf ", ";", "w:)", "w:x"].
    s = scan.Scan('echo "$(printf ")")" x')
    assert (s.rung, s.tokens()) == ("shfmt", ["w:echo", 'q:$(printf ")")', "w:x"])


@pytest.mark.parametrize("version", ["v3.4.3", "3.5.1", "(devel)", ""])
def test_a_shfmt_too_old_or_unversioned_drops_to_awk(tmp_path, monkeypatch, version):
    fake_shfmt(tmp_path, monkeypatch, f'[ "$1" = --version ] && echo "{version}" && exit 0\nexit 1\n')
    assert scan.shfmt() is None
    assert scan.Scan("rm -rf x").rung == "awk"


def test_no_shfmt_drops_to_awk(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert scan.shfmt() is None
    assert scan.Scan("rm -rf x").rung == "awk"


@pytest.mark.parametrize("crash", ["echo 'panic: boom' >&2; exit 2", "kill -9 $$", "echo not json",
                                   'echo \'{"Type": "Stmt"}\''])
def test_a_crashing_shfmt_drops_to_awk_and_denies_nothing(tmp_path, monkeypatch, crash):
    fake_shfmt(tmp_path, monkeypatch, f'[ "$1" = --version ] && echo v3.12.0 && exit 0\n{crash}\n')
    assert scan.shfmt()
    assert scan.Scan("rm -rf x").rung == "awk"
    assert verdict("ls") is None
    assert verdict("rm -rf ~")["permissionDecision"] == "deny"


def test_the_pip_rung_is_an_empty_slot(monkeypatch):
    monkeypatch.setattr(scan, "RUNGS", ("pip", "awk"))
    assert scan.Scan("rm -rf x").rung == "awk"


def feature_commands(files=None):
    """Every command a scenario names: backticked, in a docstring, or in an
    Examples table's first column."""
    out = set()
    for f in files or sorted((ROOT / "features").glob("*.feature")):
        t = f.read_text()
        out |= set(re.findall(r"`([^`\n]+)`", t))
        for m in re.finditer(r'"""\n(.*?)\n\s*"""', t, re.S):
            lines = m.group(1).split("\n")
            ind = min(len(x) - len(x.lstrip(" ")) for x in lines if x.strip())
            out.add("\n".join(x[ind:] for x in lines))
        out |= {c.strip().replace("\\|", "|") for c in re.findall(r"^\s*\|\s*((?:\\\||[^|])+?)\s*\|", t, re.M)}
    return sorted(c for c in out if not re.search(r"<[a-z]+>", c))   # Outline placeholders


@needs_shfmt
def test_shfmt_reads_every_feature_command_into_the_awk_rungs_tokens(monkeypatch):
    refused, differ = [], []
    for c in feature_commands():
        try:
            scan.check(c)
        except scan.Unparseable:
            refused.append(c)
            continue
        s = scan.Scan(c)
        monkeypatch.setattr(scan, "RUNGS", ("awk",))
        a = scan.Scan(c)
        monkeypatch.undo()
        if s.rung != "shfmt" or (s.tokens(), s.live) != (a.tokens(), a.live):
            differ.append(c)
    # parse-check's deny rows are refused by design, and so is a heredoc
    # opener alone in an Examples cell, whose body is the scenario's next
    # lines. Otherwise, a GraphQL query: never run as a command.
    by_design = set(feature_commands([ROOT / "features/parse-check.feature"]))
    refused = [c for c in refused if c not in by_design and not re.fullmatch(r"[^\n]*<<'?EOF'?[^\n]*", c)]
    assert refused == ["mutation { addLabelsToLabelable(input:{labelableId:\"x\",labelIds:[\"y\"]}) "
                       "{ clientMutationId } }"]
    # A ' in a heredoc body: the awk lexer, reading the raw command, opens a
    # quote to the end; the shfmt rung resumes at the next Word. Every guard
    # strips heredoc bodies first, so neither reading reaches one.
    assert differ == ["cat <<EOF\n$(echo \"it's\") don't\nEOF\nrm -rf examples",
                      "cat <<\\<<< EOF\n<\necho it's\nEOF\nrm -rf examples"]
