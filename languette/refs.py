"""What the repository says about itself that two guards ask the same way.

The default branch is read from the remote's HEAD ref (refs/remotes/<remote>/HEAD),
never presumed. The remote a repository means is the one `gh` would act on, never the
branch's tracking remote (see remote_url). The account `gh` acts as is GraphQL's viewer
(see viewer). A guard hands in how it asks git; the answer is a Need the world performs,
so a guard stays pure."""

import json

from languette.verdict import Need

FALLBACK = ("main", "master")      # always protected, beside what a remote HEAD names
# The account a gh call goes out as, in a GraphQL query's selection.
VIEWER = "viewer { login __typename }"
GH_TIMEOUT = 10                    # seconds


def bot(login, typename=None):
    """Whether a GitHub account is an App's: GitHub types it Bot, or its login ends in `[bot]`.
    GraphQL types its viewer User even for an App's token, so the login is what tells."""
    return typename == "Bot" or str(login or "").endswith("[bot]")


def viewer(cwd):
    """(login, typename) of the account gh acts as, or why gh could not say: one gh call."""
    try:
        rc, out, err = yield Need("run", cwd, GH_TIMEOUT, "gh", "api", "graphql", "-f", f"query={{ {VIEWER} }}")
    except Exception as e:  # noqa: BLE001 -- gh missing or hung: the caller says what that means
        return f"gh did not run ({type(e).__name__})"
    if rc != 0:
        return f"gh exited {rc}: {(err or out).strip()[:200]}"
    try:
        v = json.loads(out)["data"]["viewer"]
        login, typename = v["login"], v.get("__typename")
    except (ValueError, KeyError, TypeError, AttributeError):
        login = typename = None
    return (login, typename) if isinstance(login, str) and login else "GitHub named no viewer"


def remote_heads(ask, remote=None):
    """The branches the remote HEAD refs name, in the order git lists them; none where no HEAD ref is a symref.

    `ask(*git_args)` is a generator that returns git's stdout, or None on a failure. With
    `remote`, only that remote's HEAD is read; without it, every remote's, so a repository
    whose one remote is not called origin is read as readily as one whose is."""
    ref = f"refs/remotes/{remote}/HEAD" if remote else "refs/remotes/*/HEAD"
    out = yield from ask("for-each-ref", "--format=%(refname)\t%(symref)", ref)
    found = []
    for line in (out or "").splitlines():
        name, _, target = line.partition("\t")
        base = name.removesuffix("HEAD")
        if base != name and target.startswith(base) and len(target) > len(base):
            found.append(target[len(base):])
    return tuple(found)


def default_branches(ask, remote=None):
    """The default branches to protect: those the remote HEAD refs name, then main and master.

    A HEAD ref is a local ref the agent can move, so it adds a branch, never removes one."""
    return tuple(dict.fromkeys([*(yield from remote_heads(ask, remote)), *FALLBACK]))


def remote_url(cwd):
    """The URL of the remote `gh` would act on, or None when git cannot say or it is ambiguous.

    `gh repo set-default` writes `remote.<name>.gh-resolved` as `base` or as `owner/repo`;
    the latter sends `gh` to that repo, which need not be any remote's URL, so a value other
    than `base` anywhere leaves the target unknown. Otherwise: with one remote, that remote.
    With several, the one marked `base`, else the first of upstream, github, origin, as `gh`
    picks; with none of those, unknown. The branch's tracking remote is no part of it: `gh`
    ignores it, so a guard that trusted it could skip a scan of a post `gh` sends elsewhere.
    Read in `cwd`."""
    def ask(*argv):
        return (yield Need("git", "git", cwd, *argv))
    names = ((yield from ask("remote")) or "").split()
    marked = []
    for line in ((yield from ask("config", "--get-regexp", r"^remote\..*\.gh-resolved$")) or "").splitlines():
        key, _, value = line.partition(" ")
        if value.strip() != "base":
            return None
        marked.append(key.removeprefix("remote.").removesuffix(".gh-resolved"))
    if len(names) > 1:
        marked = [n for n in marked if n in names]
        names = marked[:1] or next(([n] for n in ("upstream", "github", "origin") if n in names), [])
    return (yield from ask("remote", "get-url", names[0])) if len(names) == 1 else None
