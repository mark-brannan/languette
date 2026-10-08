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
    def clear():                               # a test may have patched one out
        for f in (scan.shfmt, scan._shfmt_tree, scan._bash_n):
            getattr(f, "cache_clear", lambda: None)()
    clear()
    yield
    clear()


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
    v = verdict("echo 'unclosed", guard="guard-unparsable")
    assert v["permissionDecision"] == "deny"
    assert "shfmt: 1:6" in v["permissionDecisionReason"]
    assert verdict("echo 'unclosed") is None       # the other guards skip it


@needs_shfmt
def test_with_guard_unparsable_off_the_other_guards_read_an_unparseable_command():
    command = "rm -rf / 'unclosed"
    env = {"HOME": os.environ["HOME"]}
    assert run.respond(payload(command), env, only="guard-recursive-delete") == ""
    v = json.loads(run.respond(payload(command), {**env, "CLAUDE_PLUGIN_OPTION_GUARD_UNPARSABLE": "false"},
                               only="guard-recursive-delete"))["hookSpecificOutput"]
    assert v["permissionDecision"] == "deny"


@pytest.mark.parametrize("option", [None, "false"])
@pytest.mark.parametrize("guard", ["guard-unparsable", "guard-recursive-delete"])
def test_a_parser_crash_is_a_deny(monkeypatch, guard, option):
    def boom(text, words=False):
        raise RuntimeError("boom")
    monkeypatch.setattr(scan, "parse", boom)
    env = {"HOME": os.environ["HOME"], **({"CLAUDE_PLUGIN_OPTION_GUARD_UNPARSABLE": option} if option else {})}
    out = run.respond(payload("echo hi"), env, only=guard)
    v = json.loads(out)["hookSpecificOutput"]
    assert v["permissionDecision"] == "deny" and "crashed" in v["permissionDecisionReason"]


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


@pytest.mark.parametrize("crash", ["echo 'panic: boom' >&2; exit 2", "echo not json",
                                   'echo \'{"Type": "Stmt"}\''])
def test_a_crashing_shfmt_drops_to_awk_and_denies_nothing(tmp_path, monkeypatch, crash):
    fake_shfmt(tmp_path, monkeypatch, f'[ "$1" = --version ] && echo v3.12.0 && exit 0\n{crash}\n')
    assert scan.shfmt()
    assert scan.Scan("rm -rf x").rung == "awk"
    assert verdict("ls") is None
    assert verdict("rm -rf ~")["permissionDecision"] == "deny"


@pytest.mark.parametrize("stall, why", [("sleep 5", "shfmt took over 0.2 s"),
                                         ("kill -9 $$", "shfmt was killed by signal 9")])
@pytest.mark.parametrize("probe", [False, True])
def test_a_shfmt_run_that_fails_denies_and_never_passes_down(tmp_path, monkeypatch, stall, why, probe):
    monkeypatch.setattr(scan, "SHFMT_TIMEOUT", 0.2)
    body = f"{stall}\n" if probe else f'[ "$1" = --version ] && echo v3.12.0 && exit 0\n{stall}\n'
    fake_shfmt(tmp_path, monkeypatch, body)
    v = verdict("ls", guard="guard-unparsable")
    assert v["permissionDecision"] == "deny" and f"(shfmt: {why}" in v["permissionDecisionReason"]
    with pytest.raises(scan.Unparseable):      # a failed run is not cached as a pass
        scan.check("ls")


def test_a_bash_n_past_its_timeout_denies(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "RUNGS", ("bash -n", "awk"))
    monkeypatch.setattr(scan, "BASH_TIMEOUT", 0.2)
    f = tmp_path / "bash"
    f.write_text("#!/bin/sh\nsleep 5\n")
    f.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    with pytest.raises(scan.Unparseable) as e:
        scan.check("ls")
    assert e.value.rung == "bash -n" and "bash took over 0.2 s" in str(e.value)


def test_without_shfmt_bash_n_refuses_and_its_tree_is_not_mapped(monkeypatch):
    monkeypatch.setattr(scan, "RUNGS", ("bash -n", "awk"))
    v = verdict('echo "unclosed', guard="guard-unparsable")
    assert v["permissionDecision"] == "deny" and "(bash -n: " in v["permissionDecisionReason"]
    assert scan.parse("rm -rf x") == ("bash -n", True)
    calls = []
    monkeypatch.setattr(scan, "_bash_n", lambda text: calls.append(text))
    assert scan.Scan("rm -rf x").rung == "awk" and not calls    # Scan never asks a rung it cannot map


def test_with_no_bash_the_awk_rung_reads(monkeypatch, tmp_path):
    monkeypatch.setattr(scan, "RUNGS", ("bash -n", "awk"))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert scan.parse("rm -rf x") == ("awk", None)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("echo 'unclosed")
    assert e.value.rung == "awk"


@pytest.mark.parametrize("command", ["echo \"it's\" # don't", "cat <<'EOF'\ndon't\nEOF", "cat <<EOF\nit's $(date)\nEOF",
                                     "echo a\\'b", "printf '%s' \"a'b\"",
                                     "echo $'it\\'s'", "echo \\$'a' b",
                                     "echo $$'a\\'", "echo $$$'a\\'b'"])
def test_the_awk_rung_refuses_no_closed_quote(monkeypatch, command):
    monkeypatch.setattr(scan, "RUNGS", ("awk",))
    assert scan.parse(command) == ("awk", None)


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
def test_shfmt_reads_every_feature_command_into_the_awk_rungs_tokens_and_operators(monkeypatch):
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
        if s.rung != "shfmt" or (s.tokens(), s.live, s.op) != (a.tokens(), a.live, a.op):
            differ.append(c)
    # guard-unparsable's deny rows are refused by design, and so is a heredoc
    # opener alone in an Examples cell, whose body is the scenario's next
    # lines. Otherwise, a GraphQL query: never run as a command.
    by_design = set(feature_commands([ROOT / "features/guard-unparsable.feature"]))
    refused = [c for c in refused if c not in by_design and not re.fullmatch(r"[^\n]*<<'?EOF'?[^\n]*", c)]
    assert refused == ["mutation { addLabelsToLabelable(input:{labelableId:\"x\",labelIds:[\"y\"]}) "
                       "{ clientMutationId } }"]
    # A ' in a heredoc body: the awk lexer, reading the raw command, opens a
    # quote to the end; the shfmt rung resumes at the next Word. Every guard
    # strips heredoc bodies first, so neither reading reaches one. A " inside
    # a $(...) inside double quotes: the awk lexer closes the quote there, the
    # shfmt rung does not; both queue the substitution's body (texts_of).
    assert differ == ["cat <<EOF\n$(echo \"it's\") don't\nEOF\nrm -rf examples",
                      "cat <<\\<<< EOF\n<\necho it's\nEOF\nrm -rf examples",
                      'echo "$(echo "x"; rm -rf examples)"',
                      'echo "a $(echo "$(rm -rf examples)") b"']
