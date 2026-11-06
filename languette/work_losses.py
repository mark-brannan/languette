"""guard-git-work-loss's walk and its handler (languette/rules/guard_git_work_loss.py is
the rule set): the git moves that throw work away, and that an agent session never has a
good reason to make, are denied (two are asked about: `stow --adopt`, a lease push to a default branch). The spec is
features/guard-git-work-loss.feature. The `work-losses` test reads each segment's git or
stow call from its words alone; the `tree-state` handler reads the facts the relaxations
and the default branches turn on, from git in the payload's cwd, and gives the verdict.

  blanket staging   git add -A / --all / . / ./ / -u with no path, git commit -a; -A with paths
                    is allowed where an agent works (below), when every path resolves strictly
                    inside the tree: pathspec magic, globs and shell expansions do not
  stash pop/drop    pop, a bare drop, clear: the stash stack is shared across worktrees
  force push        bare --force / -f / +refspec; --force-with-lease to the default branch asks;
                    deleting it. The default branches are the remotes' HEAD refs and main and master
                    beside them (a moved HEAD adds a branch, never removes one)
  discard           git checkout . / git restore . / git clean -f / git reset --hard
                    (allowed when `git status --porcelain` (config-proof) in the payload's cwd is empty;
                    reset --hard to <remote>/<current branch> too, where an agent works)
  branch -D         and --delete --force
  stow --adopt      asks: it moves each conflicting file from the target into the package,
                    overwriting the repo's copy; -D and -R alone only touch links

Where an agent works: the payload's cwd is in this session's scratchpad or in a
linked worktree the session recorded as its own (guard-worktrees' record), and its
toplevel is not $HOME. $HOME and a repo's main checkout are where the user
works, so neither relaxation holds there.

Each rule has its own switch, CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<RULE>,
and is skipped only when it is exactly `false`. `yadm` and `vcsh` are git. The command is
read through languette.scan: heredoc bodies dropped, quotes removed, git found
behind wrappers and in `sh -c` bodies, a quoted message that names a flag is
not the flag. git takes any unambiguous prefix of a long option, so --har is
--hard. stow is recognised by the shape of the command, installed or not; it reads
options with Getopt::Long, so --adopt is any prefix of it (--ado), the options
bundle (-nvd dir), and --adopt may stand before, between or after the package names.
A package under -D is only unlinked; --adopt asks when some package is stowed (the
default) or restowed, and not on a dry run (-n, --simulate).
"""

import os
import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.refs import FALLBACK, default_branches
from languette.verdict import Need, Refuse, ask, deny
from languette.worktree_reaches import in_own_place


class Ask(Refuse):
    # Subclasses Refuse only so _judge and tree_state carry it up the same path; it asks, not denies.
    pass


class _Placed(Refuse):
    # `git add -A <paths>`: denied unless _judge finds the command runs where an agent works
    # and every path lands strictly inside its tree.
    def __init__(self, msg, names):
        super().__init__(msg)
        self.names = names


# Each rule's own switch, CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<RULE>, by git subcommand.
RULE = {"add": "BLANKET_STAGING", "commit": "BLANKET_STAGING", "stash": "STASH", "push": "FORCE_PUSH",
        "checkout": "DISCARD", "restore": "DISCARD", "clean": "DISCARD", "reset": "DISCARD",
        "branch": "BRANCH_DELETE"}
_WHOLE = re.compile(r"(?:\.|\./|\./\*|:/|:/\.|\*)\Z")
# A pathspec the guard cannot resolve to one place: magic (`:(top)`, `:/`, `:!x`, `:^x`), a glob,
# or a word the shell expands ($PWD, $(pwd), `pwd`, ~, {a,b}).
_UNRESOLVED = re.compile(r"\A[:~]|[$`*?\[{}]")
STATUS_TIMEOUT = 5
STOW = re.compile(r"(?:^|/)stow\Z")
# stow's own option table (its Getopt::Long spec), as scan.getopt reads it: option -> words its
# value takes. Like git, stow takes any unambiguous prefix of a long name.
_STOW = {**{"--" + o: 0 for o in "adopt compat dotfiles no-folding simulate no verbose help version stow delete "
                                 "restow".split()},
         **{"--" + o: 1 for o in "dir target ignore defer override".split()}, "-d": 1, "-t": 1}
_STOW_SHORT = {"-n": "--simulate", "-v": "--verbose", "-p": "--compat", "-S": "--stow", "-D": "--delete",
               "-R": "--restow", "-V": "--version", "-h": "--help"}
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


# git add's own option table (builtin/add.c, git 2.53): long name -> (takes a value, negatable).
# git takes any unambiguous prefix of a long name or of its --no- form, and a value either after
# `=` or as the next word. An option missing from here is refused rather than guessed at, since a
# guessed value could be a word git reads as the option's and the guard as a path.
_ADD_LONG = {
    "dry-run": (False, True), "verbose": (False, True), "interactive": (False, True),
    "patch": (False, True), "unified": (True, False), "inter-hunk-context": (True, False),
    "edit": (False, True), "force": (False, True), "update": (False, True),
    "renormalize": (False, True), "intent-to-add": (False, True), "all": (False, True),
    "ignore-removal": (False, True), "refresh": (False, True), "ignore-errors": (False, True),
    "ignore-missing": (False, True), "sparse": (False, True), "chmod": (True, True),
    "warn-embedded-repo": (False, True), "pathspec-from-file": (True, True),
    "pathspec-file-nul": (False, True),
}
_ADD_SHORT = {"n": "dry-run", "v": "verbose", "i": "interactive", "p": "patch", "U": "unified",
              "e": "edit", "f": "force", "u": "update", "N": "intent-to-add", "A": "all"}


def _add_long(t):
    """`--name[=value]` as git reads it: (canonical name, negated, glued value or None). An
    unknown or ambiguous name raises Refuse."""
    name, eq, val = t[2:].partition("=")
    forms = {}
    for full, (_, neg) in _ADD_LONG.items():
        forms[full] = (full, False)
        if neg:
            forms["no-" + full] = (full, True)
    if name in forms:
        hit = [forms[name]]
    else:
        hit = list({forms[f] for f in forms if f.startswith(name)}) if name else []
    if len(hit) != 1:
        raise Refuse(say("wl_add_unknown", t=t))
    full, negated = hit[0]
    if eq and not _ADD_LONG[full][0]:
        raise Refuse(say("wl_add_no_value", t=t))
    return full, negated, (val if eq else None)


def add_options(a):
    """Split git add's words into the options set (canonical names, a negated one as no-<name>)
    and the pathspecs' indexes into a, from git's own option table. A value option eats the
    next word when its value is not glued on; `--` and `--end-of-options` end the options."""
    opts, specs = [], []
    i, n = 0, len(a)
    while i < n:
        t = a[i]
        i += 1
        if t in ("--", "--end-of-options"):
            specs.extend(range(i, n))
            break
        if t in ("-h", "--help"):     # git prints usage or the manual and stages nothing
            opts.append("help")
        elif t.startswith("--"):
            full, negated, val = _add_long(t)
            if _ADD_LONG[full][0] and not negated and val is None:
                if i >= n:
                    raise Refuse(say("wl_add_needs_value", t=t))
                i += 1
            opts.append(("no-" if negated else "") + full)
        elif t.startswith("-") and t != "-":
            for j, ch in enumerate(t[1:], 1):
                full = _ADD_SHORT.get(ch)
                if full is None:
                    raise Refuse(say("wl_add_unknown_short", t=t, ch=ch))
                opts.append(full)
                if _ADD_LONG[full][0]:
                    if j == len(t) - 1:
                        if i >= n:
                            raise Refuse(say("wl_add_needs_value", t=t))
                        i += 1
                    break
        else:
            specs.append(i - 1)
    return opts, specs


def _add(a):
    opts, at = add_options(a)
    names = [a[i] for i in at]
    if "help" in opts:
        return
    for t in names:
        if _WHOLE.match(t):
            raise Refuse(say("wl_add_whole", t=t))
    every = "all" in opts or "no-ignore-removal" in opts
    upd = "update" in opts or "renormalize" in opts
    listed = "pathspec-from-file" in opts     # the paths are in a file the guard does not read
    paths = len(names)
    if every:
        if paths and not listed and not any(_UNRESOLVED.search(t) for t in names):
            raise _Placed(say("wl_add_all"), names)
        raise Refuse(say("wl_add_all"))
    if upd and not paths:
        raise Refuse(say("wl_add_u"))


def _commit(a):
    if any(_pfx(t, "--all") or _has(t, "a") for t in a):
        raise Refuse(say("wl_commit_a"))


def _stash(a):
    words = [t for t in a if not t.startswith("-")]
    op, refs = (words[0], len(words) - 1) if words else ("", 0)
    if op == "pop":
        raise Refuse(say("wl_stash_pop"))
    if op == "clear":
        raise Refuse(say("wl_stash_clear"))
    if op == "drop" and not refs:
        raise Refuse(say("wl_stash_drop"))


def _default(branches):
    return re.compile(r"(?:refs/heads/)?(?:" + "|".join(map(re.escape, branches)) + r")\Z")


def _push_may_hurt(a):
    """Whether a push could force, lease, delete or colon-refspec: only then does the default branch matter."""
    return any(t.startswith((":", "+", "--force", "--delete")) or _pfx(t, "--force") or _pfx(t, "--delete")
               or _has(t, "f") or _has(t, "d") for t in a)


def _push(doc, a):
    if not _push_may_hurt(a):
        return
    branches = yield from _default_branches(doc)
    main = _default(branches)
    force = lease = delete = False
    protected_branch = ""  # the default branch this push targets, or "" if none
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
        elif t.startswith(":") and main.match(_dst(t)):
            delete = True
            protected_branch = _dst(t).removeprefix("refs/heads/")
        elif not t.startswith("-") and main.match(_dst(t)):
            protected_branch = _dst(t).removeprefix("refs/heads/")
    if force:
        raise Refuse(say("wl_force_push", branches=', '.join(branches)))
    if protected_branch and delete:
        raise Refuse(say("wl_delete_protected", branch=protected_branch))
    if protected_branch and lease:
        raise Ask(say("wl_lease_protected", branch=protected_branch))


def _discard(sub, a):
    staged = wt = False
    wh = ""
    for t in a:
        staged = staged or t == "-S" or _pfx(t, "--staged") or _has(t, "S")
        wt = wt or t == "-W" or _pfx(t, "--worktree") or _has(t, "W")
        if _WHOLE.match(t):
            wh = t
    if wh and not (sub == "restore" and staged and not wt):
        raise Refuse(say("wl_discard", sub=sub, wh=wh))


def _clean(a):
    force = any(_pfx(t, "--force") or _has(t, "f") for t in a)
    dry = any(_pfx(t, "--dry-run") or _has(t, "n") for t in a)
    if force and not dry:
        raise Refuse(say("wl_clean_f"))


def _branch(a):
    delete = force = False
    for t in a:
        if t == "-D" or _has(t, "D"):
            raise Refuse(say("wl_branch_D"))
        delete = delete or t == "-d" or _pfx(t, "--delete") or _has(t, "d")
        force = force or t == "-f" or _pfx(t, "--force") or _has(t, "f")
    if delete and force:
        raise Refuse(say("wl_branch_delete_force"))


def _reset(a):
    if any(_pfx(t, "--hard") for t in a):
        raise Refuse(say("wl_reset_hard"))


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
    """True when cwd's toplevel is this session's own: inside its scratchpad, or a linked
    worktree it recorded, and is not $HOME's: then the toplevel, else "". Another session's
    worktree, a repo's main checkout outside the scratchpad, and $HOME, are the user's. Any failure to ask is "", as is a toplevel of /."""
    home = (doc.env or {}).get("HOME") or ""
    if not home.startswith("/"):
        return ""
    try:
        rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "rev-parse", "--path-format=absolute",
                                "--show-toplevel")
        top = out.strip()
        if rc != 0 or not top:
            return ""
        top = yield Need("path", "realpath", top)
        if top in ("", "/") or top == (yield Need("path", "realpath", home)):
            return ""
        return top if (yield from in_own_place(doc, top)) else ""
    except Exception:  # noqa: BLE001
        return ""


def _upstream_target(args):
    """(R, X) of `reset --hard R/X`, given only --hard and -q beside it; else None."""
    refs = [t for t in args if not t.startswith("-")]
    flags = [t for t in args if t.startswith("-")]
    remote, _, branch = refs[0].partition("/") if len(refs) == 1 else ("", "", "")
    if not remote or not branch:
        return None
    if not all(_pfx(t, "--hard") or t == "-q" or _pfx(t, "--quiet") for t in flags):
        return None
    return remote, branch


def _own_upstream(cwd, remote, branch):
    """True when HEAD is refs/heads/<branch>, <remote>/<branch> resolves to the remote-tracking
    ref of that name (not a local ref or tag that shadows it), and the branch tracks that
    ref or nothing. Read from git, not from @{u} alone."""
    rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "rev-parse", "--symbolic-full-name",
                            "HEAD", f"{remote}/{branch}")
    if rc != 0 or out.split() != ["refs/heads/" + branch, f"refs/remotes/{remote}/{branch}"]:
        return False
    rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", "for-each-ref", "--format=%(upstream)",
                            "refs/heads/" + branch)
    return rc == 0 and out.strip() in ("", f"refs/remotes/{remote}/{branch}")


def _nothing_to_lose(doc, sub, args):
    """True when the discard `sub args` loses nothing uncommitted: no word of the command moves
    or re-aims the tree, no other segment of it can run before the discard and dirty the
    tree (the status is read before the command runs), the payload's cwd is a git work
    tree with a clean status and no file marked assume-unchanged or skip-worktree, and
    the discard is not one that reaches past the status (clean -x) or drops a commit
    (reset to a ref). The one reset to a ref that passes is to <remote>/<current branch>,
    where agents work (_where_agents_work, _own_upstream); it drops any commit the branch
    has ahead of that remote, which this check does not look for (the reflog keeps them).
    Any failure to ask is False."""
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
        if upstream and not ((yield from _where_agents_work(doc, cwd)) and (yield from _own_upstream(cwd, *upstream))):
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


def _default_branches(doc):
    """The default branches of the repository at the payload's cwd, as the remotes' HEAD refs
    name them (all remotes, a push's remote being as likely a URL or an alias); main and master
    always beside them. Read in the payload's cwd; a push aimed elsewhere (-C, cd, GIT_DIR) still has main and master."""
    cwd = doc.payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        return FALLBACK

    def ask(*argv):
        rc, out, _ = yield Need("run", cwd, STATUS_TIMEOUT, "git", *argv)
        return out if rc == 0 else None
    try:
        return (yield from default_branches(ask))
    except Exception:  # noqa: BLE001
        return FALLBACK


def _staging_where_agents_work(doc, names):
    """`git add -A <paths>` stages only those paths; it passes when no word of the command
    moves or re-aims the tree, the payload's cwd is where agents work, and each path,
    resolved from the cwd, lies strictly inside the toplevel both as git reads it (lexically,
    so `link/..` is `.`) and with symlinks followed. A path that resolves to the
    toplevel or above it (`..`, the root's absolute path) is the whole tree: plain blanket
    staging, denied as such."""
    cwd = doc.payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        return False
    scans = [(doc.scan(text), nested) for text, nested in doc.texts()]
    if paths.moves_directory(scans) or _reaimed(scans):
        return False
    top = yield from _where_agents_work(doc, cwd)
    if not top:
        return False
    try:
        here = yield Need("path", "realpath", cwd)
        for t in names:
            lexical = os.path.normpath(os.path.join(here, t))
            real = yield Need("path", "realpath", os.path.join(cwd, t))
            if not (lexical.startswith(top + "/") and real.startswith(top + "/")):
                break
        else:
            return True
    except Exception:  # noqa: BLE001
        return False
    raise Refuse(say("wl_add_all"))


def _stow_adopts(a):
    """True when the stow words `a` run --adopt on some package that is stowed or restowed.
    An action option (-S, -D, -R) holds for the package names after it, the default being
    stow. An unknown option is read as flag-only, so it cannot hide an --adopt after it."""
    adopt, action, stowed = False, "--stow", False
    for opt, _ in sw.getopt(a, _STOW, abbreviate=True, ends=("--", "--end-of-options")):
        opt = _STOW_SHORT.get(opt, opt)
        if opt is None:
            stowed = stowed or action != "--delete"
        elif opt in ("--help", "--version", "--simulate", "--no"):
            return False
        elif opt == "--adopt":
            adopt = True
        elif opt in ("--stow", "--delete", "--restow"):
            action = opt
    return adopt and stowed


def _off(env, rule):
    """The rule's own switch is exactly `false`."""
    return env.get(f"CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_{rule}") == "false"




def _stow(s, a, b, nested, env):
    """`stow --adopt` asks: its reason, or None. A stow call without it, or one that only
    deletes, does not.

    A stray ask on a reader such as `man stow --adopt` is accepted: it only asks, never denies."""
    k = sw.cmd_index(s, a, b, STOW, nested)
    if k is None or _off(env, "ADOPT"):
        return None
    return say("wl_stow_adopt") if _stow_adopts(s.w[k + 1:b + 1]) else None


def _git(s, a, b, nested, env):
    """What the segment's git call does that may throw work away, read from its words alone:
    {"sub", "args", "rule" (its switch's name), "mine" (git is the segment's own command and
    runs no wrapper's home), and one of "refused" (the Refuse its words earn), "placed" (the paths
    of an `add -A` that may land where an agent works) or "push" (a push the default branches
    judge)}, or None for a call that loses nothing, or whose rule is off."""
    g = sw.cmd_index(s, a, b, sw.GIT, nested)
    if g is None:
        return None
    i = sw.git_subcommand(s, g, b)
    if i > b:
        return None
    sub = s.w[i]
    rule = RULE.get(sub)
    if rule and _off(env, rule):
        return None
    args = s.w[i + 1:b + 1]
    found = {"sub": sub, "args": args, "rule": rule,
             "mine": not sw.git_wrapper(s.w[g])[1].home and _own_command(s, a, b, g)}
    try:
        if sub == "add":
            _add(args)
        elif sub == "commit":
            _commit(args)
        elif sub == "stash":
            _stash(args)
        elif sub == "push":
            return {**found, "push": True} if _push_may_hurt(args) else None
        elif sub in ("checkout", "restore"):
            _discard(sub, args)
        elif sub == "clean":
            _clean(args)
        elif sub == "branch":
            _branch(args)
        elif sub == "reset":
            _reset(args)
    except _Placed as p:
        return {**found, "placed": p.names}
    except Refuse as r:
        return {**found, "refused": r}
    return None


def losses(doc):
    """The `work-losses` test: {"segments": [{"git": what _git found or None, "stow": the
    reason a `stow --adopt` asks or None}, ...]} for the segments that hold either, in the
    command's order, or None when none does."""
    if not doc.text:
        return None
    env = doc.env or {}
    found = []
    for text, nested in doc.texts():
        s = doc.scan(text)
        for a, b in s.segments():
            if a <= b:
                seg = {"git": _git(s, a, b, nested, env), "stow": _stow(s, a, b, nested, env)}
                if seg["git"] or seg["stow"]:
                    found.append(seg)
    return {"segments": found} if found else None


def _judge(doc, f):
    """Raise Refuse, or Ask, for the git call _git found, once the facts its relaxations
    turn on are read: the default branches for a push, whether a discard loses nothing,
    whether an `add -A` lands where an agent works."""
    try:
        if "placed" in f:
            raise _Placed(say("wl_add_all"), f["placed"])
        if "refused" in f:
            raise f["refused"]
        if "push" in f:
            (yield from _push(doc, f["args"]))
    except _Placed as p:
        if f["mine"] and (yield from _staging_where_agents_work(doc, p.names)):
            return
        raise Refuse(say("wl_add_all_paths"))
    except Refuse as r:
        if f["rule"] == "DISCARD" and f["mine"] and (yield from _nothing_to_lose(doc, f["sub"], f["args"])):
            return
        if f["sub"] == "reset" and _upstream_target(f["args"]):
            raise Refuse(say("wl_reset_upstream", why=r))
        raise


def tree_state(doc, guard, found):
    """The `tree-state` handler: each segment the `work-losses` test found, in order, judged
    against the tree it runs in. The first refusal denies; else the first ask asks. A
    segment whose git call asks is not asked about again for its stow."""
    asked = None
    try:
        for seg in found["segments"]:
            try:
                if seg["git"]:
                    yield from _judge(doc, seg["git"])
                if seg["stow"]:
                    raise Ask(seg["stow"])
            except Ask as r:
                asked = asked or r
    except Refuse as r:
        return deny(say("judged", guard=guard, why=r))
    if asked:
        return ask(say("judged", guard=guard, why=asked))
    return None
