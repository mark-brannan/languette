"""What the repository says about itself that two guards ask the same way.

The default branch is read from the remote's HEAD ref (refs/remotes/<remote>/HEAD),
never presumed. A guard hands in how it asks git; the answer is a Need the world
performs, so a guard stays pure."""

FALLBACK = ("main", "master")      # always protected, beside what a remote HEAD names


def default_branches(ask, remote=None):
    """The default branches to protect: those the remote HEAD refs name, then main and master.

    A HEAD ref is a local ref the agent can move, so it adds a branch, never removes one.

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
    return tuple(dict.fromkeys([*found, *FALLBACK]))
