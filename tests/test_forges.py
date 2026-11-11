"""Forges as rows (docs/design/forges.md): which forge a remote's URL names,
and the world asking that forge's client."""

import json
import os

import pytest
from hamcrest import assert_that, equal_to

from languette import scan
from languette.verdict import Need
from languette.world import World


@pytest.mark.parametrize("url, want", [
    ("https://github.com/o/r.git", ("github", "github.com", "o/r")),
    ("git@github.com:o/r.git", ("github", "github.com", "o/r")),
    ("ssh://git@ssh.github.com:443/o/r/", ("github", "github.com", "o/r")),
    ("https://user:tok@GitHub.com/o/r", ("github", "github.com", "o/r")),
    ("git@gitlab.com:g/sub/p.git", ("gitlab", "gitlab.com", "g/sub/p")),
    ("https://gitlab.example.com/g/p", ("gitlab", "gitlab.example.com", "g/p")),
    ("ssh://git@altssh.gitlab.com:443/g/p.git", ("gitlab", "gitlab.com", "g/p")),
    ("https://github.com/o/r/x", None),          # not a GitHub repo's path
    ("https://github.com/o/..", None),
    ("https://codeberg.org/o/r", None),          # no row yet
    ("https://example.com/github.com/o/r", None),
    ("/srv/git/r.git", None),
    ("", None),
])
def test_a_remote_names_its_forge_by_host(url, want):
    assert_that(scan.remote(url), equal_to(want if want is None else scan.Remote(*want)))


@pytest.fixture
def client(tmp_path):
    """A forge client on PATH that logs its argv and answers $ANSWER, exiting $CODE."""
    def make(name):
        f = tmp_path / name
        f.write_text('#!/bin/sh\nprintf \'%s\\n\' "${0##*/} $*" > "$LOG"\nprintf \'%s\\n\' "$ANSWER"\nexit "$CODE"\n')
        f.chmod(0o755)
    return make


@pytest.mark.parametrize("forge, host, code, answer, argv, status", [
    ("github", "github.com", 0, {"a": 1}, "gh api p", 200),
    ("github", "github.com", 1, {"message": "Not Found", "status": "404"}, "gh api p", 404),
    ("gitlab", "gitlab.com", 0, [], "glab api p", 200),
    ("gitlab", "gitlab.example.com", 1, {"message": "404 Project Not Found"},
     "glab api --hostname gitlab.example.com p", 404),
    ("gitlab", "gitlab.com", 1, {"error": "invalid_token"}, "glab api p", None),
])
def test_the_world_asks_the_forges_own_client(client, tmp_path, forge, host, code, answer, argv, status):
    client(scan.FORGES[forge]["cli"])
    env = {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "LOG": str(tmp_path / "log"),
           "ANSWER": json.dumps(answer), "CODE": str(code)}
    got = World(env, {}).answer(Need("forge-api", forge, host, "p"))
    assert_that(got, equal_to((status, answer if status else None)))
    assert_that((tmp_path / "log").read_text().strip(), equal_to(argv))


def _api(command):
    """The GhApi of a `gh api` command."""
    s = scan.Scan(command)
    return scan.gh_api(s, 2, len(s.w) - 1)


@pytest.mark.parametrize("command, graphql, writes", [
    ("gh api graphql -f query='{viewer{login}}'", True, False),
    ("gh api https://ghe.example.com/api/graphql -f query='{viewer{login}}'", True, False),
    ("gh api --hostname ghe.example.com graphql -f query='mutation{x}'", True, True),
    ("gh api https://ghe.example.com/api/graphql -f query='mutation{x}'", True, True),
    ("gh api -X POST graphql -f query='query{viewer{login}}'", True, False),
    ('gh api graphql -f query="{repository(name:\\"$R\\"){id}}"', True, False),   # a read, filled at run time
    ('gh api graphql -f query="$Q"', True, None),
    ("gh api graphql --input q.json", True, None),
    ("gh api graphql -F query=@q.graphql", True, None),
    ("gh api repos/o/r/issues", False, False),
    ("gh api repos/o/r/issues -f title=t", False, True),
    ("gh api -X GET repos/o/r/issues -f state=open", False, False),
    ("gh api -X DELETE repos/o/r/issues/1/labels", False, True),
])
def test_one_reading_of_a_gh_api_call(command, graphql, writes):
    api = _api(command)
    assert_that((api.graphql, api.writes), equal_to((graphql, writes)))


@pytest.mark.parametrize("command, repo", [
    ("gh issue delete 7", None),
    ("GH_REPO=a/one gh issue delete 7", "a/one"),
    ("GH_REPO=a/one GH_REPO=b/two gh issue delete 7", "b/two"),      # the shell keeps the last
    ("GH_REPO=a/one gh issue delete 7 -R c/three", "c/three"),
    ("gh -R c/three issue delete 7 --repo=d/four", "d/four"),
])
def test_the_target_repo_reads_as_the_shell_and_gh_do(command, repo):
    s = scan.Scan(command)
    g = s.w.index("gh")
    assert_that(scan.gh_repo(s, 0, g, len(s.w) - 1), equal_to(repo))
