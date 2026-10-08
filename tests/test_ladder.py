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
        for f in (scan.shfmt, scan._shfmt_tree, scan._bash_n, scan._ts_parser, scan._tree_sitter, scan._bashlex_mod,
                  scan._bashlex):
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


@pytest.mark.parametrize("crash", ["echo 'panic: boom' >&2; exit 2", "kill -9 $$", "echo not json",
                                   'echo \'{"Type": "Stmt"}\''])
def test_a_crashing_shfmt_drops_to_awk_and_denies_nothing(tmp_path, monkeypatch, crash):
    fake_shfmt(tmp_path, monkeypatch, f'[ "$1" = --version ] && echo v3.12.0 && exit 0\n{crash}\n')
    assert scan.shfmt()
    assert scan.Scan("rm -rf x").rung == "awk"
    assert verdict("ls") is None
    assert verdict("rm -rf ~")["permissionDecision"] == "deny"


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


class Node:
    """Enough of a tree-sitter node for _tree_sitter: kind is "ok", "ERROR" or "MISSING"."""
    def __init__(self, kind="ok", children=(), at=(0, 0), text=b"", type="program"):
        self.is_error, self.is_missing = kind == "ERROR", kind == "MISSING"
        self.children, self.start_point, self.text, self.type = list(children), at, text, type
        self.has_error = self.is_error or self.is_missing or any(c.has_error for c in self.children)


def fake_ts(monkeypatch, root):
    tree = type("Tree", (), {"root_node": root})()
    monkeypatch.setattr(scan, "_ts_parser", lambda: type("P", (), {"parse": lambda self, b: tree})())


def refuse(monkeypatch, why="line 1: unexpected EOF"):
    """bash -n, faked to refuse, so the column is the only thing under test."""
    def bash_n(text):
        raise scan.Unparseable(why)
    monkeypatch.setattr(scan, "_bash_n", bash_n)
    monkeypatch.setattr(scan, "RUNGS", ("bash -n", "awk"))


@pytest.mark.parametrize("root, at", [
    (Node(children=[Node(), Node("ERROR", at=(0, 4), text=b" 'unclosed")]), "1:6"),
    (Node(children=[Node("ERROR", at=(0, 0), text=b"case x in")]), "1:1"),
    (Node(children=[Node(children=[Node("MISSING", at=(1, 11), type=")")]), Node("ERROR")]), "2:12"),
])
def test_tree_sitter_adds_the_column_to_a_refusal_below_shfmt(monkeypatch, root, at):
    fake_ts(monkeypatch, root)
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("x")
    assert (e.value.rung, str(e.value)) == ("bash -n", f"line 1: unexpected EOF, at {at} per tree-sitter-bash")


def test_tree_sitter_never_decides(monkeypatch):
    fake_ts(monkeypatch, Node(children=[Node("ERROR", at=(0, 0), text=b"x")]))
    monkeypatch.setattr(scan, "RUNGS", ("awk",))
    assert scan.parse("echo ok") == ("awk", None)            # an ERROR node, and the text still reads


@pytest.mark.parametrize("parser", [
    None,                                                    # not installed
    type("P", (), {"parse": lambda self, b: 1 / 0})(),        # crashes
    type("P", (), {"parse": lambda self, b: type("T", (), {"root_node": Node()})()})(),  # a clean tree
])
def test_with_no_column_the_refusal_stands_as_its_rung_wrote_it(monkeypatch, parser):
    monkeypatch.setattr(scan, "_ts_parser", lambda: parser)
    monkeypatch.setattr(scan, "_bashlex_mod", lambda: None)
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("x")
    assert (e.value.rung, str(e.value)) == ("bash -n", "line 1: unexpected EOF")


def fake_bashlex(monkeypatch, raises):
    """A bashlex whose parse raises raises(text), or reads clean when raises is None."""
    class ParsingError(Exception):
        def __init__(self, message, s, position):
            super().__init__(message)
            self.message, self.s, self.position = message, s, position

    def parse(text):
        if raises:
            raise raises(ParsingError, text)
    monkeypatch.setattr(scan, "_bashlex_mod", lambda: type("M", (), {"parse": staticmethod(parse)}))


@pytest.mark.parametrize("raises, at", [
    (lambda E, s: E("unexpected EOF while looking for matching \"'\"", s, len(s)), "2:7"),
    (lambda E, s: E("unexpected token '('", s, 3), "1:4"),
    (lambda E, s: E("past the end", s, 99), "2:7"),
])
def test_bashlex_adds_the_column_when_tree_sitter_gives_none(monkeypatch, raises, at):
    monkeypatch.setattr(scan, "_ts_parser", lambda: None)
    fake_bashlex(monkeypatch, raises)
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("if true; then\necho x")
    assert (e.value.rung, str(e.value)) == ("bash -n", f"line 1: unexpected EOF, at {at} per bashlex")


def test_tree_sitter_answers_before_bashlex(monkeypatch):
    fake_ts(monkeypatch, Node(children=[Node("ERROR", at=(0, 4), text=b" 'x")]))
    fake_bashlex(monkeypatch, lambda E, s: E("unexpected EOF", s, 0))
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("x")
    assert str(e.value).endswith(", at 1:6 per tree-sitter-bash")


def test_bashlex_never_decides(monkeypatch):
    fake_bashlex(monkeypatch, lambda E, s: E("unexpected token '-f'", s, 3))
    monkeypatch.setattr(scan, "RUNGS", ("awk",))
    assert scan.parse("[[ -f x ]] && echo y") == ("awk", None)


@pytest.mark.parametrize("raises", [
    None,                                                    # a clean parse
    lambda E, s: NotImplementedError("arithmetic expansion"),  # unsupported: no position
    lambda E, s: 1 / 0,                                      # crashes
    lambda E, s: E("unexpected EOF", s, None),               # a position that is not one
])
def test_with_no_bashlex_column_the_refusal_stands(monkeypatch, raises):
    monkeypatch.setattr(scan, "_ts_parser", lambda: None)
    fake_bashlex(monkeypatch, raises)
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("x")
    assert (e.value.rung, str(e.value)) == ("bash -n", "line 1: unexpected EOF")


def test_with_no_bashlex_package_the_refusal_stands(monkeypatch):
    monkeypatch.setattr(scan, "_ts_parser", lambda: None)
    monkeypatch.setattr(scan, "_bashlex_mod", lambda: None)
    refuse(monkeypatch)
    with pytest.raises(scan.Unparseable) as e:
        scan.check("x")
    assert str(e.value) == "line 1: unexpected EOF"


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
