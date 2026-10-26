"""guard-git-work-loss: the git moves that throw work away, and that an agent
session never has a good reason to make, are denied (one is asked about). The spec is
features/guard-git-work-loss.feature.

  blanket staging   git add -A / --all / . / ./ / -u with no path, git commit -a; -A with paths
                    is allowed where an agent works (below)
  stash pop/drop    pop, a bare drop, clear: the stash stack is shared across worktrees
  force push        bare --force / -f / +refspec; --force-with-lease to main or master asks;
                    deleting main
  discard           git checkout . / git restore . / git clean -f / git reset --hard
                    (allowed when `git status --porcelain` (config-proof) in the payload's cwd is empty;
                    reset --hard to origin/<current branch> too, where an agent works)
  branch -D         and --delete --force

Where an agent works: the payload's cwd is in a linked worktree (git's own
--git-dir differs from --git-common-dir) or the session's scratchpad, and its
toplevel is not $HOME. $HOME and a repo's main checkout are where the user
works, so neither relaxation holds there.

Each rule has its own switch, CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<RULE>,
and is skipped only when it is exactly `false`. `yadm` is git. The command is
read through languette.scan: heredoc bodies dropped, quotes removed, git found
behind wrappers and in `sh -c` bodies, a quoted message that names a flag is
not the flag. git takes any unambiguous prefix of a long option, so --har is
--hard.
"""

import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import Need, Refuse, ask, deny


class Ask(Refuse):
    # Subclasses Refuse only so _segment and its callers carry it up the same path; it asks, not denies.
    pass


class _Placed(Refuse):
    # `git add -A <paths>`: denied unless _segment finds the command runs where an agent works.
    pass

NAME = "guard-git-work-loss"
RULE = {"add": "BLANKET_STAGING", "commit": "BLANKET_STAGING", "stash": "STASH", "push": "FORCE_PUSH",
        "checkout": "DISCARD", "restore": "DISCARD", "clean": "DISCARD", "reset": "DISCARD",
        "branch": "BRANCH_DELETE"}
_WHOLE = re.compile(r"(?:\.|\./|\./\*|:/|:/\.|\*)\Z")
_MAIN = re.compile(r"(?:refs/heads/)?(?:main|master)\Z")
STATUS_TIMEOUT = 5
# Words that re-aim the tree a discard is judged in, or the config git reads. A git global
# option naming a tree or config counts only as one of git's own (`sh -c` is not git's -c);
# the environment's spelling and any config naming a work tree count in any word. A cd,
# pushd, popd or wrapper chdir is paths.moves_directory's.
_AIM_OPT = re.compile(r"(?:-C|-c|--git-dir|--work-tree|--config-env)\Z|(?:--git-dir|--work-tree|--config-env)=.*", re.I)
_AIM_ANY = re.compile(r"(?:GIT_(?:DIR|WORK_TREE|COMMON_DIR|INDEX_FILE|CONFIG\w*)=.*|.*core\.worktree=.*)\Z", re.I)


def _reaimed(scans):
    """Some word of the command re-aims the tree or the config: an environment or config word
    anywhere, or a global option of any git call in any scanned text."""
    for (s, nested) in scans:
        if any(k == "w" and _AIM_ANY.match(w) for k, w in zip(s.k, s.w)):
            return True
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, sw.GIT, nested) if a <= b else None
            if g is not None and any(_AIM_OPT.match(s.w[i]) for i in sw.git_options(s, g, sw.git_subcommand(s, g, b))):
                return True
    return False


def _has(t, ch):
    """A single-dash cluster holding `ch`: -Av has A."""
    return re.fullmatch(r"-[A-Za-z0-9]*" + ch + r"[A-Za-z0-9]*", t) is not None


def _pfx(t, full):
    return len(t) >= 3 and full.startswith(t)


def _dst(t):
    t = t[1:] if t.startswith("+") else t
    return t.split(":", 1)[1] if ":" in t else t


def _add(a):
    paths = upd = every = listed = 0
    for t in a:
        if _WHOLE.match(t):
            raise Refuse(f"`git add {t}` is blocked: stage by path, not the whole tree.")
        if t == "-A" or _pfx(t, "--all") or _pfx(t, "--no-ignore-removal") or _has(t, "A"):
            every = 1
        elif t == "-u" or _pfx(t, "--update") or _has(t, "u"):
            upd = 1
        elif _pfx(t.split("=", 1)[0], "--pathspec-from-file"):
            listed = 1                         # the paths are in a file the guard does not read
        elif not t.startswith("-"):
            paths += 1
    if every:
        msg = ("`git add -A` is blocked: stage by path. Where the worktree is $HOME it stages the home "
               "directory; elsewhere it sweeps in files a parallel session is working on.")
        if paths and not listed:
            raise _Placed(msg)
        raise Refuse(msg)
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
    if tomain and delete:
        raise Refuse("deleting main is blocked. Main takes rebased branches through a PR.")
    if tomain and lease:
        raise Ask("`--force-with-lease` to main rewrites shared history. Main takes rebased branches through a PR; "
                  "if a force to main is meant, the user confirms it.")


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


def _short(t, ch):
    """A single-dash cluster holding `ch` before any glued value: -fde, -fe!* and -e!* hold e."""
    return re.match(r"-[A-Za-z0-9]*" + ch, t) is not None and not t.startswith("--")


def _exclude(t):
    """clean's --exclude, in any unambiguous prefix, separate or `=` form."""
    return _pfx(t.split("=", 1)[0], "--exclude")


def _own_command(s, a, b, g):
    """The git at g is the segment's own command: nothing but VAR=x assignments, or `env`
    and assignments, stand before it. A wrapper (ssh, docker exec, watch, nsenter, ...) runs
    git elsewhere or later, where the status read here says nothing."""
    c = sw.seg_cmd(s, a, b)
    if c == g:
        return True
    return (c is not None and s.w[c].rsplit("/", 1)[-1] == "env"
            and all(s.k[i] == "w" and sw._ASSIGN.match(s.w[i]) for i in range(c + 1, g)))


def _where_agents_work(doc, cwd):
    """True when cwd's toplevel is a linked worktree or inside the session's scratchpad,
    and is not $HOME's. A repo's main checkout outside the scratchpad, and $HOME, are the
    user's. Any failure to ask is False."""
    home = (doc.env or {}).get("HOME") or ""
    if not home.startswith("/"):
        return False
    try:
        rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "rev-parse", "--path-format=absolute",
                                "--show-toplevel", "--git-dir", "--git-common-dir")
        lines = out.splitlines()
        if rc != 0 or len(lines) != 3:
            return False
        top, gdir, common = lines
        top = yield Need("path", "realpath", top)
        if top == (yield Need("path", "realpath", home)):
            return False
        if (yield Need("path", "realpath", gdir)) != (yield Need("path", "realpath", common)):
            return True
        sid = doc.payload.get("session_id")
        scratch = (yield Need("worktree", "scratchpad", sid)) if isinstance(sid, str) and sid else None
        if not scratch:
            return False
        scratch = yield Need("path", "realpath", scratch)
    except Exception:  # noqa: BLE001
        return False
    return top == scratch or top.startswith(scratch.rstrip("/") + "/")


def _upstream_target(args):
    """The branch X of `reset --hard origin/X`, given only --hard and -q beside it; else None."""
    refs = [t for t in args if not t.startswith("-")]
    flags = [t for t in args if t.startswith("-")]
    if len(refs) != 1 or not refs[0].startswith("origin/") or len(refs[0]) == len("origin/"):
        return None
    if not all(_pfx(t, "--hard") or t == "-q" or _pfx(t, "--quiet") for t in flags):
        return None
    return refs[0][len("origin/"):]


def _own_upstream(cwd, branch):
    """True when HEAD is refs/heads/<branch>, origin/<branch> resolves to the remote-tracking
    ref of that name (not a local ref or tag that shadows it), and the branch tracks that
    ref or nothing. Read from git, not from @{u} alone."""
    rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "rev-parse", "--symbolic-full-name",
                            "HEAD", "origin/" + branch)
    if rc != 0 or out.split() != ["refs/heads/" + branch, "refs/remotes/origin/" + branch]:
        return False
    rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "for-each-ref", "--format=%(upstream)",
                            "refs/heads/" + branch)
    return rc == 0 and out.strip() in ("", "refs/remotes/origin/" + branch)


def _nothing_to_lose(doc, sub, args):
    """True when the discard `sub args` cannot lose anything: no word of the command moves
    or re-aims the tree, no other segment of it can run before the discard and dirty the
    tree (the status is read before the command runs), the payload's cwd is a git work
    tree with a clean status and no file marked assume-unchanged or skip-worktree, and
    the discard is not one that reaches past the status (clean -x) or drops a commit
    (reset to a ref). The one reset to a ref that passes is to origin/<current branch>,
    where agents work (_where_agents_work, _own_upstream). Any failure to ask is False."""
    cwd = doc.payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        return False
    upstream = _upstream_target(args) if sub == "reset" else None
    if sub == "reset" and not upstream and any(not t.startswith("-") and t != "HEAD" for t in args):
        return False
    if sub == "clean" and any(_short(t, "x") or _short(t, "X") or _short(t, "e") or _exclude(t) for t in args):
        return False  # -x/-X, and -e '!pat' un-ignoring, reach files the status does not list
    scans = [(doc.scan(text), nested) for text, nested in doc.texts()]
    if paths.moves_directory(scans) or not sw.alone(scans, sw.GIT):
        return False
    if _reaimed(scans):
        return False
    try:
        if upstream and not ((yield from _where_agents_work(doc, cwd)) and (yield from _own_upstream(cwd, upstream))):
            return False
        rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "-c", "status.showUntrackedFiles=all", "status", "--porcelain",
                           "--untracked-files=all", "--ignore-submodules=none")
        if rc != 0 or out != "":
            return False
        # status leaves out a file marked assume-unchanged or skip-worktree, whose edits a discard
        # still throws away: any such file, anywhere in the tree (`:/`), is something to lose.
        rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "ls-files", "-v", "-z", ":/")
    except Exception:  # noqa: BLE001
        return False
    return rc == 0 and not any(e[:1].islower() or e[:1] == "S" for e in out.split("\0") if e)


def _staging_where_agents_work(doc):
    """`git add -A <paths>` stages only those paths; it passes when no word of the command
    moves or re-aims the tree and the payload's cwd is where agents work."""
    cwd = doc.payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        return False
    scans = [(doc.scan(text), nested) for text, nested in doc.texts()]
    if paths.moves_directory(scans) or _reaimed(scans):
        return False
    return (yield from _where_agents_work(doc, cwd))


def _segment(doc, s, a, b, nested, env):
    g = sw.cmd_index(s, a, b, sw.GIT, nested)
    if g is None:
        return
    i = sw.git_subcommand(s, g, b)
    if i > b:
        return
    sub = s.w[i]
    rule = RULE.get(sub)
    if rule and env.get(f"CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_{rule}") == "false":
        return
    args = s.w[i + 1:b + 1]
    try:
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
    except _Placed:
        if not s.w[g].endswith("yadm") and _own_command(s, a, b, g) and (yield from _staging_where_agents_work(doc)):
            return
        raise Refuse(say("wl_add_all_paths"))
    except Refuse as r:
        if (rule == "DISCARD" and not s.w[g].endswith("yadm") and _own_command(s, a, b, g)
                and (yield from _nothing_to_lose(doc, sub, args))):
            return
        if sub == "reset" and _upstream_target(args):
            raise Refuse(say("wl_reset_upstream", why=r))
        raise


def check(doc):
    payload, env = doc.payload, doc.env or {}
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd:
        return None
    asked = None
    try:
        for text, nested in doc.texts():
            s = doc.scan(text)
            for a, b in s.segments():
                if a <= b:
                    try:
                        yield from _segment(doc, s, a, b, nested, env)
                    except Ask as r:
                        asked = asked or r
    except Refuse as r:
        return deny(say("judged", guard=NAME, why=r))
    if asked:
        return ask(say("judged", guard=NAME, why=asked))
    return None
