"""A guard never runs vcsh: its verbs (init, clone, delete, ...) change the system, and the
repository word is the agent's. Where a guard needs git's answer about a vcsh repository it
runs plain git against the repository's git dir, and for a word that is a verb or a path it
runs nothing."""

import pytest

from languette.document import Document
from languette.guards import guard_bypass_ruleset, prose_budget_commit
from languette.verdict import Need

ENV = {"HOME": "/home/u", "XDG_CONFIG_HOME": "/home/u/.config"}


def needs(guard, command, env=ENV):
    """Every Need the guard yields for the command, each answered as a machine with no
    repository, no network and an engine that finds nothing would."""
    doc = Document({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": "/home/u"}, env)
    gen, seen, answer = guard.check(doc), [], None
    try:
        while True:
            need = gen.send(answer)
            seen.append(need)
            answer = {"which": "/usr/bin/" + need.args[0], "path": True, "run": (0, "", "")}.get(need.kind)
    except StopIteration:
        return seen


def programs(seen):
    """The program each Need that runs one names."""
    return [n.args[0] if n.kind in ("git", "which") else n.args[2] for n in seen if n.kind in ("git", "run", "which")]


@pytest.mark.parametrize("command", [
    "vcsh init push origin main",
    "vcsh clone push origin main",
    "vcsh delete push origin main",
    "vcsh run push origin main",
    "vcsh pull origin main",
    "vcsh dots/x push origin main",
    "vcsh ../dots push origin main",
    "vcsh .dots push origin main",
    "vcsh push",
])
def test_ruleset_runs_nothing_for_a_vcsh_word_that_is_not_a_repository(command):
    seen = needs(guard_bypass_ruleset, command)
    assert [n for n in seen if n.kind == "git"] == []


@pytest.mark.parametrize("repo", ["init", "clone", "delete", "run", "rename", "dots/x", "../dots", ".dots", "-x", ""])
def test_a_commit_listing_runs_nothing_for_a_vcsh_word_that_is_not_a_repository(repo):
    seen = needs(prose_budget_commit, f"vcsh {repo} commit -a -m x")
    assert "vcsh" not in programs(seen)
    assert [n for n in seen if n.kind == "run" and any(str(a).startswith("--git-dir") for a in n.args)] == []


@pytest.mark.parametrize("command", ["vcsh dots push origin main", "vcsh run dots git push origin main"])
def test_ruleset_asks_git_about_the_repositorys_own_git_dir_never_vcsh(command):
    seen = needs(guard_bypass_ruleset, command)
    gits = [n for n in seen if n.kind == "git"]
    assert gits and all(n.args[0] == "git" for n in gits)
    assert all(n.args[2:4] == ("--git-dir=/home/u/.config/vcsh/repo.d/dots.git", "--work-tree=/home/u") for n in gits)
    assert "vcsh" not in programs(seen)


def test_the_git_dir_follows_xdg_config_home_and_a_relative_one_is_refused():
    seen = needs(guard_bypass_ruleset, "vcsh dots push origin main", {"HOME": "/h", "XDG_CONFIG_HOME": "/x"})
    assert {n.args[2] for n in seen if n.kind == "git"} == {"--git-dir=/x/vcsh/repo.d/dots.git"}
    seen = needs(guard_bypass_ruleset, "vcsh dots push origin main", {"HOME": "/h", "XDG_CONFIG_HOME": "x"})
    assert [n for n in seen if n.kind == "git"] == []


def test_a_commit_listing_runs_git_against_the_repositorys_git_dir():
    seen = needs(prose_budget_commit, "vcsh dots commit -a -m x")
    runs = [n.args for n in seen if n.kind == "run" and n.args[2] == "/usr/bin/git"]
    assert runs and all(a[3:5] == ("--git-dir=/home/u/.config/vcsh/repo.d/dots.git", "--work-tree=/home/u") for a in runs)
    assert "vcsh" not in programs(seen)
