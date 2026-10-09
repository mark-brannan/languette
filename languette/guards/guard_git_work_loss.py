"""guard-git-work-loss: the git moves that throw work away, and that an agent
session never has a good reason to make, are denied. The spec is
features/guard-git-work-loss.feature.

  blanket staging   git add -A / --all / . / ./ / -u with no path, git commit -a
  stash pop/drop    pop, a bare drop, clear: the stash stack is shared across worktrees
  force push        bare --force / -f / +refspec; --force-with-lease to main or master;
                    deleting main
  discard           git checkout . / git restore . / git clean -f / git reset --hard
  branch -D         and --delete --force

Each rule has its own switch, CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<RULE>,
and is skipped only when it is exactly `false`. `yadm` is git. The command is
read through languette.scan: heredoc bodies dropped, quotes removed, git found
behind wrappers and in `sh -c` bodies, a quoted message that names a flag is
not the flag. git takes any unambiguous prefix of a long option, so --har is
--hard.
"""

import re

from languette import scan as sw
from languette.verdict import Refuse, deny

NAME = "guard-git-work-loss"
GIT = re.compile(r"(?:^|/)(?:git|yadm)\Z")
GLOBAL_VALUE = frozenset("-C -c --git-dir --work-tree --namespace --config-env --attr-source".split())
RULE = {"add": "BLANKET_STAGING", "commit": "BLANKET_STAGING", "stash": "STASH", "push": "FORCE_PUSH",
        "checkout": "DISCARD", "restore": "DISCARD", "clean": "DISCARD", "reset": "DISCARD",
        "branch": "BRANCH_DELETE"}
_WHOLE = re.compile(r"(?:\.|\./|\./\*|:/|:/\.|\*)\Z")
_MAIN = re.compile(r"(?:refs/heads/)?(?:main|master)\Z")


def _has(t, ch):
    """A single-dash cluster holding `ch`: -Av has A."""
    return re.fullmatch(r"-[A-Za-z0-9]*" + ch + r"[A-Za-z0-9]*", t) is not None


def _pfx(t, full):
    return len(t) >= 3 and full.startswith(t)


def _dst(t):
    t = t[1:] if t.startswith("+") else t
    return t.split(":", 1)[1] if ":" in t else t


def _add(a):
    paths = upd = 0
    for t in a:
        if t == "-A" or _pfx(t, "--all") or _pfx(t, "--no-ignore-removal") or _has(t, "A"):
            raise Refuse("`git add -A` is blocked: stage by path. Where the worktree is $HOME it stages the home "
                         "directory; elsewhere it sweeps in files a parallel session is working on.")
        if _WHOLE.match(t):
            raise Refuse(f"`git add {t}` is blocked: stage by path, not the whole tree.")
        if t == "-u" or _pfx(t, "--update") or _has(t, "u"):
            upd = 1
        elif not t.startswith("-"):
            paths += 1
    if upd and not paths:
        raise Refuse("`git add -u` with no path is blocked: stage by path.")


def _commit(a):
    if any(_pfx(t, "--all") or _has(t, "a") for t in a):
        raise Refuse("`git commit -a` is blocked: it is `git add -u` in disguise. Stage by path, then commit.")


def _stash(a):
    words = [t for t in a if not t.startswith("-")]
    op, refs = (words[0], len(words) - 1) if words else ("", 0)
    if op == "pop":
        raise Refuse("`git stash pop` is blocked: the stash stack is shared across worktrees and pop can take "
                     "another session's entry. Use `git stash apply <sha>` and drop the entry afterwards.")
    if op == "clear":
        raise Refuse("`git stash clear` is blocked: the stash stack is shared across worktrees; it is not all "
                     "yours to clear.")
    if op == "drop" and not refs:
        raise Refuse("bare `git stash drop` drops stash@{0}, which may be another session's. "
                     "Name the entry: `git stash drop stash@{n}` after finding it by tag.")


def _push(a):
    force = lease = tomain = delete = False
    for t in a:
        if t.startswith("--force-with-lease=") or (t.startswith("--force-") and (
                _pfx(t, "--force-with-lease") or _pfx(t, "--force-if-includes"))):
            lease = True
            continue
        if _pfx(t, "--force") or _has(t, "f"):
            force = True
        elif _pfx(t, "--delete") or _has(t, "d"):
            delete = True
        elif t.startswith("+"):
            force = True
        elif t.startswith(":") and _MAIN.match(_dst(t)):
            delete = tomain = True
        elif not t.startswith("-") and _MAIN.match(_dst(t)):
            tomain = True
    if force:
        raise Refuse("bare `git push --force` is blocked. Rebasing a session branch is the one legitimate force: "
                     "use `--force-with-lease origin <branch>`, never to main.")
    if tomain and (lease or delete):
        raise Refuse("force-pushing or deleting main is blocked. Main takes rebased branches through a PR.")


def _discard(sub, a):
    staged = wt = False
    wh = ""
    for t in a:
        staged = staged or t == "-S" or _pfx(t, "--staged") or _has(t, "S")
        wt = wt or t == "-W" or _pfx(t, "--worktree") or _has(t, "W")
        if _WHOLE.match(t):
            wh = t
    if wh and not (sub == "restore" and staged and not wt):
        raise Refuse(f"`git {sub} {wh}` is blocked: it discards every uncommitted change, same as reset --hard. "
                     "Restore one path at a time, or ask the user.")


def _clean(a):
    force = any(_pfx(t, "--force") or _has(t, "f") for t in a)
    dry = any(_pfx(t, "--dry-run") or _has(t, "n") for t in a)
    if force and not dry:
        raise Refuse("`git clean -f` is blocked: it deletes untracked files, unrecoverably. "
                     "`git clean -n` to list them, then remove by path.")


def _branch(a):
    delete = force = False
    for t in a:
        if t == "-D" or _has(t, "D"):
            raise Refuse("`git branch -D` is blocked: it deletes unmerged work. `git branch -d` refuses when there "
                         "is something to lose; if it refuses, that is the answer.")
        delete = delete or t == "-d" or _pfx(t, "--delete") or _has(t, "d")
        force = force or t == "-f" or _pfx(t, "--force") or _has(t, "f")
    if delete and force:
        raise Refuse("`git branch --delete --force` is blocked: same as -D.")


def _reset(a):
    if any(_pfx(t, "--hard") for t in a):
        raise Refuse("`git reset --hard` is blocked at user scope. It discards uncommitted work, and on a shared "
                     "checkout that work may not be yours. Ask the user to run it themselves, or reach for a "
                     "reversible move: `git revert`, a new branch off the good commit, `git stash`, "
                     "`git reset --soft`/`--mixed`.")


def _segment(s, a, b, nested, env):
    g = sw.cmd_index(s, a, b, GIT, nested)
    if g is None:
        return
    i = g + 1
    while i <= b and s.w[i].startswith("-"):
        i += 1 + (s.w[i] in GLOBAL_VALUE)
    if i > b:
        return
    sub = s.w[i]
    rule = RULE.get(sub)
    if rule and env.get(f"CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_{rule}") == "false":
        return
    args = s.w[i + 1:b + 1]
    if sub == "add":
        _add(args)
    elif sub == "commit":
        _commit(args)
    elif sub == "stash":
        _stash(args)
    elif sub == "push":
        _push(args)
    elif sub in ("checkout", "restore"):
        _discard(sub, args)
    elif sub == "clean":
        _clean(args)
    elif sub == "branch":
        _branch(args)
    elif sub == "reset":
        _reset(args)


def check(payload, env=None):
    env = env or {}
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd:
        return None
    try:
        for text, nested in sw.texts_of(sw.strip_heredocs(cmd + "\n")):
            s = sw.Scan(text)
            for a, b in s.segments():
                if a <= b:
                    _segment(s, a, b, nested, env)
    except Refuse as r:
        return deny(f"{NAME}: {r}")
    return None
