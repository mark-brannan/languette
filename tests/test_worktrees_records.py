"""guard-worktrees where features/guard-worktrees.feature cannot reach: the
per-session record edited on disk, a tool taken off PATH, and a deny whose
output must stay valid JSON. Each test runs the hook as hooks.json does, by an
absolute python3 with the payload on stdin, against a throwaway repo with real
linked worktrees: the guard asks git what a path is, so only paths git really
answers about mean anything."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOOK = [sys.executable, "-I", str(ROOT / "languette" / "run.py"), "--guard", "guard-worktrees"]
GIT = ["git", "-c", "user.email=t@e", "-c", "user.name=t"]


@pytest.fixture
def fx(tmp_path):
    """A repo with linked worktrees `mine` and `theirs`, an unrelated clone, and
    TMPDIR (where the hook keeps its records) inside tmp_path."""
    t = tmp_path.resolve()
    repo = t / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run([*GIT, "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    for name in ("mine", "theirs"):
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", name,
                        str(repo / ".claude" / "worktrees" / name)], check=True)
    subprocess.run(["git", "clone", "-q", str(repo), str(t / "other-clone")], check=True)
    (t / "records").mkdir()
    wts = repo / ".claude" / "worktrees"
    return {"tmp": t, "repo": repo, "wts": wts, "mine": wts / "mine", "theirs": wts / "theirs",
            "clone": t / "other-clone", "records": t / "records"}


def _env(fx, **over):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    env["TMPDIR"] = str(fx["records"])
    return {**env, **over}


def _bash(command, cwd, session=None):
    p = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
    if session:
        p["session_id"] = session
    return json.dumps(p)


def _hook(payload, env):
    out = subprocess.run(HOOK, input=payload, env=env, capture_output=True, text=True).stdout
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else "allow"


def test_a_record_whose_inode_is_stale_is_not_own(fx):
    s, new3 = "11111111-0000-4000-8000-000000000003", fx["wts"] / "new3"
    env = _env(fx)
    assert _hook(_bash("git status", fx["mine"], s), env) == "allow"
    assert _hook(_bash(f"git worktree add -b new3 {new3} && cd {new3}", fx["mine"], s), env) == "allow"
    subprocess.run(["git", "-C", str(fx["repo"]), "worktree", "add", "-q", "-b", "new3", str(new3)], check=True)
    assert _hook(_bash("git status", new3, s), env) == "allow"
    assert _hook(_bash(f"git -C {new3} status", fx["clone"], s), env) == "allow"
    rec = fx["records"] / f"languette-guard-worktrees.{s}"
    lines = [line.split("\t") for line in rec.read_text().splitlines()]
    assert any(f[0] == str(new3) for f in lines)
    # A worktree removed and re-created at the recorded path has another .git inode.
    rec.write_text("".join("\t".join([f[0], "1", *f[2:]] if f[0] == str(new3) else f) + "\n" for f in lines))
    assert _hook(_bash(f"git -C {new3} status", fx["clone"], s), env) == "deny"


def test_a_symlinked_record_grants_nothing(fx):
    """A shared /tmp could plant one."""
    s = "11111111-0000-4000-8000-000000000007"
    planted = fx["tmp"] / "planted"
    planted.write_text(f"{fx['theirs']}\t{(fx['theirs'] / '.git').stat().st_ino}\n")
    (fx["records"] / f"languette-guard-worktrees.{s}").symlink_to(planted)
    assert _hook(_bash(f"git -C {fx['theirs']} status", fx["mine"], s), _env(fx)) == "deny"
    # The same lines as a plain file are honoured, so the deny above is the symlink's.
    s8 = "11111111-0000-4000-8000-000000000008"
    shutil.copy(planted, fx["records"] / f"languette-guard-worktrees.{s8}")
    assert _hook(_bash(f"git -C {fx['theirs']} status", fx["mine"], s8), _env(fx)) == "allow"


def test_nothing_on_path_fails_closed_with_valid_json(fx):
    env = {"PATH": "/nonexistent", "HOME": os.environ["HOME"], "TMPDIR": str(fx["records"])}
    assert _hook(_bash(f"git -C {fx['theirs']} status", fx["mine"]), env) == "deny"


def test_no_git_on_path_fails_closed(fx, tmp_path):
    """git is what every foreignness answer is asked of: without it no path may
    read as not foreign."""
    bin_ = tmp_path / "no-git-bin"
    bin_.mkdir()
    for tool in ("jq", "awk", "sed"):
        if p := shutil.which(tool):
            (bin_ / tool).symlink_to(p)
    env = {"PATH": str(bin_), "HOME": os.environ["HOME"], "TMPDIR": str(fx["records"])}
    assert _hook(_bash(f"git -C {fx['theirs']} status", fx["mine"]), env) == "deny"


def test_a_control_character_in_the_path_still_gives_valid_deny_json(fx):
    tab_dir = fx["theirs"] / "tab\tdir"
    tab_dir.mkdir()
    assert _hook(_bash(f"ls '{tab_dir}'", fx["mine"]), _env(fx)) == "deny"
