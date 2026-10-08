"""guard-bypass-ruleset: a ruleset's bypass is the user's, never the agent's.

An agent runs on the user's credentials, so wherever the user may bypass a
branch's rules, so may the agent, and GitHub cannot tell them apart. Two
doors are watched:

- a `git push` (or `yadm push`) that lands on the remote's default branch,
  when GitHub says that branch requires a pull request: a ruleset with a
  `pull_request` rule, or classic branch protection with required reviews.
  Only a "requires a pull request" answer is cached, for an hour under
  $XDG_CACHE_HOME/languette/rulesets; a file the agent can write can then
  only make the guard stricter, never silent.
- `gh pr merge --admin`, which exists only to merge past a PR's rules.

Both deny. The user's own terminal never reaches a hook, so the user keeps
the bypass. When GitHub cannot answer (no gh, signed out, offline, a 10 s
timeout, an error) or the destination cannot be read (a variable refspec,
GIT_DIR, a detached HEAD), the guard asks, so the user decides. GitHub's
"upgrade to Pro" answer is not a failure: a private repo on a free plan
cannot carry rules, so there is nothing to bypass.

The default branch is the remote's HEAD as git last fetched it, and main
and master beside it: that HEAD is a local ref the agent can move, so it may
add a branch to watch, never take one away. A `cd` the shell may undo before
the push (in a subshell, a group or a pipeline, or followed by `||`) and a
`popd` leave the directory unknown, so the guard asks. Not watched: pushes to
any other branch, tags and deletions (guard-git-work-loss and guard-git-stacked-base
judge those), remotes off github.com or behind an ssh host alias, `gh api`
writes to a ref or a merge endpoint, an alias from the user's own gitconfig
or `gh alias`, and `push.default=matching` (a bare `git push origin` pushing
every matching branch).
"""

import os
import re
from urllib.parse import quote

from languette import scan as sw
from languette.verdict import Need, Refuse, ask, deny

NAME = "guard-bypass-ruleset"
TTL = 3600

_GIT = re.compile(r"(?:^|/)(?:git|yadm)\Z")
_GH = re.compile(r"(?:^|/)gh\Z")
_CD = re.compile(r"\A(?:cd|pushd|popd)\Z")
_EXPORT = frozenset("export declare typeset".split())
_GIT_ENV = ("GIT_DIR=", "GIT_WORK_TREE=")
_GIT_VALUED = frozenset("-C -c --git-dir --work-tree --namespace --config-env".split())
_PUSH_VALUED = frozenset("-o --push-option --repo --receive-pack --exec".split())
_ALL = frozenset("--all --branches --mirror".split())
_UNREADABLE = re.compile(r"[$`*?\[{]")
_GITHUB = re.compile(r"github\.com(?::\d+)?[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?\Z", re.IGNORECASE)
# A separator after a `cd` that the shell may undo before the next command: the close of a
# subshell or group, a pipe (the cd ran in a subshell), `||`, a backtick, or a lone `&`.
_UNDOES_CD = re.compile(r"[)}|`]|(?<!&)&(?!&)")
_FALLBACK = ("main", "master")
HEAD, ALL, IMPLICIT = object(), object(), object()

ADMIN = ("guard-bypass-ruleset: `gh pr merge --admin` merges past the PR's required reviews and checks on "
         "the user's bypass. Merge without --admin, or with --auto to merge once the checks pass. "
         "Bypassing is the user's to do, from their own terminal.")


class _Push:
    def __init__(self, prog, here, remote, dsts):
        self.prog, self.here, self.remote, self.dsts = prog, here, remote, dsts


def _resolve(base, target, live):
    """The directory `cd target` lands in from base, or None if unreadable."""
    if base is None or live or _UNREADABLE.search(target) or target.startswith("~") or target == "-":
        return None
    return os.path.normpath(target if target.startswith("/") else os.path.join(base, target))


def _config_value(s, i, b):
    """The lower-cased `name=value` a `-c` or `--config-env` word at i sets, in any spelling."""
    x = s.w[i]
    if x in ("-c", "--config-env"):
        return s.w[i + 1].lower() if i + 1 <= b else None
    if x.startswith("--config-env="):
        return x[13:].lower()
    if x.startswith("-c") and not x.startswith("--"):
        return x[2:].lower()
    return None


def _opt(x, full):
    """Whether x is `full` or an abbreviation git would accept for it (`--al` for `--all`)."""
    x = x.split("=", 1)[0]
    return len(x) > 2 and x.startswith("--") and full.startswith(x)


def _push(s, a, b, nested, here):
    g = sw.cmd_index(s, a, b, _GIT, nested)
    if g is None:
        return None
    prog = "yadm" if s.w[g].endswith("yadm") else "git"
    if any(s.w[i].startswith(_GIT_ENV) for i in range(a, g)):
        here = None
    i = g + 1
    while i <= b and s.w[i] != "push":
        x = s.w[i]
        if x == "-C" and i + 1 <= b:
            here = _resolve(here, s.w[i + 1], s.live[i + 1])
        if x.startswith(("--git-dir", "--work-tree")):
            here = None
        cfg = _config_value(s, i, b)
        if cfg and (cfg.startswith("alias.") or "insteadof" in cfg):
            raise Refuse("a `-c` override of an alias or a URL rewrite can turn any subcommand into a push, "
                         "or any remote into another")
        if x in _GIT_VALUED:
            i += 2
        elif x.startswith("-"):
            i += 1
        elif s.live[i] or _UNREADABLE.search(x):
            raise Refuse(f"the subcommand `{x}` is built at run time")
        else:
            return None                        # another subcommand
    if i > b:
        return None
    remote, pos, all_, tags, dry, dashdash = None, [], False, False, False, False
    i += 1
    while i <= b:
        x = s.w[i]
        if dashdash or not x.startswith("-") or x == "-":
            pos.append(i)
        elif x == "--":
            dashdash = True
        elif x == "--no-dry-run":
            dry = False                        # the last of -n and --no-dry-run wins
        elif _opt(x, "--repo") and "=" not in x and i + 1 <= b:
            remote = s.w[i + 1]
            if s.live[i + 1]:
                raise Refuse(f"the remote `{remote}` is built at run time")
        elif _opt(x, "--repo") and "=" in x:
            remote = x.split("=", 1)[1]
            if s.live[i]:
                raise Refuse(f"the remote `{remote}` is built at run time")
        elif any(_opt(x, f) for f in _ALL):
            all_ = True
        elif _opt(x, "--tags"):
            tags = True
        elif _opt(x, "--delete") or re.match(r"-[^o-]*d", x):
            return None                        # a deletion is other guards'
        elif _opt(x, "--dry-run") or re.match(r"-[^o-]*n", x):
            dry = True                         # a dry run pushes nothing
        if x in _PUSH_VALUED or (_opt(x, "--repo") and "=" not in x):
            i += 1
        i += 1
    if dry:
        return None
    if remote is None and pos:
        k = pos.pop(0)
        remote = s.w[k]
        if s.live[k]:
            raise Refuse(f"the remote `{remote}` is built at run time")
    if remote is not None and _UNREADABLE.search(remote):
        raise Refuse(f"the remote `{remote}` is built at run time")
    if all_:
        return _Push(prog, here, remote, [ALL])
    if not pos:
        return None if tags else _Push(prog, here, remote, [IMPLICIT])
    dsts = []
    for j in pos:
        r = s.w[j].lstrip("+")
        if s.live[j] or _UNREADABLE.search(r):
            raise Refuse(f"the refspec `{s.w[j]}` is built at run time, so where it lands can't be read")
        src, _, dst = r.partition(":")
        if ":" in r and not src:
            continue                           # :branch deletes
        dst = dst or src
        if dst in ("HEAD", "@"):
            dsts.append(HEAD)
            continue
        if dst.startswith("refs/heads/"):
            dst = dst[11:]
        elif dst.startswith("refs/"):
            continue                           # a tag or another namespace
        dsts.append(dst)
    return _Push(prog, here, remote, dsts) if dsts else None


def _admin_merge(s, a, b, nested):
    g = sw.cmd_index(s, a, b, _GH, nested)
    if g is None:
        return False
    w = s.w[g + 1:b + 1]
    admin = any(x == "--admin" or x.startswith("--admin=") for x in w)
    dyn = [s.live[g + 1 + k] or bool(_UNREADABLE.search(x)) for k, x in enumerate(w)]
    if "pr" in w and "merge" in w:
        if admin:
            return True
        if any(dyn):
            raise Refuse("a `gh pr merge` word is built at run time and could be `--admin`")
        return False
    if any(dyn):
        if admin:
            return True                        # a live subcommand beside a literal --admin
        first, skip = [], False                # the group and its verb; a literal -R value is neither
        for k, x in enumerate(w):
            if skip:
                skip = False
                if dyn[k]:                     # a run-time -R value may split into `pr merge`
                    first.append(k)
            elif x.startswith("-"):
                skip = x in ("-R", "--repo") or _opt(x, "--repo") and "=" not in x
            elif len(first) < 2:
                first.append(k)
        # Only a run-time group, or a run-time verb under a literal `pr`, could spell `pr merge`.
        if first and (dyn[first[0]] or (w[first[0]] == "pr" and len(first) > 1 and dyn[first[1]])):
            raise Refuse("the `gh` subcommand is built at run time and could be `pr merge --admin`")
    return False


def _walk(cmd, cwd):
    """(pushes, whether an admin merge was seen, the first Refuse). A Refuse ends only its own
    command, so an admin merge or a push on PR-only main later in the line still denies."""
    pushes, admin, refused = [], False, None
    for text, nested in sw.texts_of(sw.strip_heredocs(cmd + "\n")):
        s, here, moved = sw.Scan(text), cwd, False
        for a, b in s.segments():
            if a > b:
                continue
            c = sw.seg_cmd(s, a, b)
            if c is not None and _CD.match(s.w[c]):
                here = _resolve(here, s.w[c + 1], s.live[c + 1]) if c + 1 <= b and s.w[c] != "popd" else None
                moved = True
            elif c is not None and s.w[c] in _EXPORT and any(s.w[j].startswith(_GIT_ENV) for j in range(c + 1, b + 1)):
                here = None                    # an exported GIT_DIR moves every later git
            else:
                try:
                    admin = admin or _admin_merge(s, a, b, nested)
                    p = _push(s, a, b, nested, here)
                except Refuse as e:
                    refused = refused or e
                    continue
                if p:
                    pushes.append(p)
            if moved and b + 1 < len(s) and _UNDOES_CD.search(s.op[b + 1]):
                here = None                    # the shell may undo the cd before the next command
    return pushes, admin, refused


def _git(p, env, *args):
    if p.here is None and p.prog == "git":
        return None
    return (yield Need("git", p.prog, p.here or env.get("HOME") or "/", *args))


def _says(body, words):
    return isinstance(body, dict) and words in str(body.get("message", "")).lower()


def _requires_pr(slug, branch):
    """"pr", "open", or None when GitHub can't answer."""
    cached = yield Need("ruleset-cache", slug, branch)
    if cached and cached[1] == "pr" and (yield Need("clock")) - cached[0] < TTL:
        return "pr"
    b = quote(branch, safe="")
    code, body = yield Need("gh-api", f"repos/{slug}/rules/branches/{b}")
    if code == 200 and isinstance(body, list) and any(isinstance(r, dict) and r.get("type") == "pull_request"
                                                      for r in body):
        got = "pr"
    elif code == 403 and _says(body, "upgrade"):
        got = "open"                           # this plan can carry no rules and no protection
    elif code != 200:
        return None
    else:
        code, body = yield Need("gh-api", f"repos/{slug}/branches/{b}/protection")
        if code == 200 and isinstance(body, dict):
            got = "pr" if body.get("required_pull_request_reviews") else "open"
        elif code == 404 and (_says(body, "not protected") or _says(body, "branch not found")):
            got = "open"                       # no branch, and the rules endpoint already said no ruleset
        else:
            return None
    if got == "pr":
        yield Need("ruleset-keep", slug, branch, got)
    return got


def _judge(p, env):
    """deny or ask for one push, or None."""
    remote, dsts = p.remote, list(p.dsts)
    if IMPLICIT in dsts:
        dsts.remove(IMPLICIT)
        up = yield from _git(p, env, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}")
        if up and "/" in up:
            r, br = up.split("/", 1)
            remote = remote or r
            dsts.append(br)
        else:
            dsts.append(HEAD)
    if HEAD in dsts:
        dsts.remove(HEAD)
        cur = yield from _git(p, env, "symbolic-ref", "--short", "HEAD")
        if cur is None:
            return ask(f"guard-bypass-ruleset: this {p.prog} push sends the current branch, and the hook can't "
                       "tell which branch that is (another directory, or a detached HEAD), so it can't check "
                       "whether the push goes around a rule that requires a pull request.")
        dsts.append(cur)
    if remote is None:
        cur = (yield from _git(p, env, "symbolic-ref", "--short", "HEAD")) or ""
        for key in (f"branch.{cur}.pushRemote", "remote.pushDefault", f"branch.{cur}.remote"):
            remote = yield from _git(p, env, "config", key)
            if remote:
                break
        remote = remote or "origin"
    url = remote if ("/" in remote or ":" in remote) else (yield from _git(p, env, "remote", "get-url", "--push",
                                                                           remote))
    head = yield from _git(p, env, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    defaults = list(_FALLBACK)
    if head and "/" in head and head.split("/", 1)[1] not in defaults:
        defaults.insert(0, head.split("/", 1)[1])
    hits = defaults if ALL in dsts else [d for d in dsts if d in defaults]
    if not hits:
        return None
    if url is None:
        return ask(f"guard-bypass-ruleset: this pushes to `{hits[0]}` through remote `{remote}`, in a repository the "
                   "hook can't find (a cd or -C it can't follow, or GIT_DIR), so it can't ask GitHub whether "
                   f"`{hits[0]}` requires a pull request. The agent runs on your credentials, so it can use your "
                   "bypass.")
    m = _GITHUB.search(url)
    if not m:
        return None
    if {".", ".."} & set(m.groups()):
        return None
    slug = f"{m.group(1)}/{m.group(2)}"
    asked = None
    for branch in hits:
        got = yield from _requires_pr(slug, branch)
        if got == "pr":
            return deny(f"guard-bypass-ruleset: `{branch}` on {slug} requires a pull request, and this push would go "
                        "around it on the user's bypass. Push a branch and open a PR. A direct push is the user's "
                        "to make, from their own terminal.")
        if got is None:
            asked = asked or ask(f"guard-bypass-ruleset: this pushes to `{branch}` on {slug}, and GitHub couldn't say "
                                 f"whether `{branch}` requires a pull request (gh missing, signed out, offline or "
                                 f"an error):\n  gh api repos/{slug}/rules/branches/{quote(branch, safe='')}\n"
                                 "The agent runs on your credentials, so it can use your bypass.")
    return asked


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        cwd = yield Need("cwd")
    pushes, admin, refused = _walk(cmd.rstrip("\n"), cwd)
    if admin:
        return deny(ADMIN)
    asked = None
    for p in pushes:
        v = yield from _judge(p, env)
        if v and v["permissionDecision"] == "deny":
            return v
        asked = asked or v
    if refused:
        return ask(f"guard-bypass-ruleset: {refused}, so the hook can't check whether it goes around a rule that "
                   "requires a pull request. The agent runs on your credentials, so it can use your bypass.")
    return asked
