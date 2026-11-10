"""A git call's words: the wrapper that runs it (git, yadm, vcsh), its
repository, global options and subcommand, and the plain git that stands in
for a wrapper.
"""

import re

from .lexicon import GIT_VALUE, GIT_WRAPPERS, _base


def git_wrapper(word):
    """(name, row) of the GIT_WRAPPERS entry a word that GIT matched names."""
    name = word.rsplit("/", 1)[-1]
    return name, GIT_WRAPPERS[name]


# vcsh's own verbs, each with the abbreviations vcsh accepts for it. A word in this
# table after `vcsh` is a verb, never a repository name.
VCSH_VERBS = {v: v for v in (
    "clone commit delete enter foreach help init list list-tracked list-tracked-by list-untracked "
    "pull push rename run status upgrade version which write-gitignore").split()}
for _v, _abbr in {"clone": "clon clo cl", "commit": "commi comm com co ci", "delete": "delet dele del de",
                  "enter": "ente ent en", "help": "hel he", "init": "ini in", "pull": "pul", "push": "pus",
                  "rename": "renam rena ren re", "run": "ru", "status": "statu stat sta st",
                  "upgrade": "upgrad upgra upgr up", "version": "versio versi vers ver ve", "which": "whi wh",
                  "write-gitignore": "write writ wri wr"}.items():
    VCSH_VERBS.update(dict.fromkeys(_abbr.split(), _v))
# The verbs that run git in every repository: vcsh hands `commit` its arguments and
# runs a bare `git pull` or `git push` in each.
VCSH_ALL = frozenset("commit pull push".split())


def _git_walk(s, g, b):
    """(repository, subcommand index, indexes of the global option words) of the git call at g.
    A wrapper that takes a repository names it before the git arguments, or after `run`;
    `vcsh <verb>` is not a git call (the subcommand is beyond b) except the verbs that run
    git: `commit`, `pull` and `push` in every repository (repository None), `foreach [-p] <git
    arguments>` likewise (`foreach -g <command>` only when the command is git), and `run <repo> git ...`."""
    opts = []

    def take(i):
        while i <= b and s.w[i].startswith("-"):
            opts.append(i)
            i += 1 + (s.w[i] in GIT_VALUE)
        return i

    i = take(g + 1)
    if not git_wrapper(s.w[g])[1].repo or i > b:
        return None, i, opts
    verb = VCSH_VERBS.get(s.w[i])
    if verb is None:
        return s.w[i], take(i + 1), opts
    if verb in VCSH_ALL:
        return None, i, opts
    repo, j = None, i + 1
    if verb == "foreach":
        # vcsh's getopts "gp": -g and -p flags (clustered too), then the command. Without -g
        # vcsh puts `git` before it, so the next word is the subcommand, in every repository.
        general = False
        while j <= b and s.k[j] == "w" and re.fullmatch(r"-[gp]+", s.w[j]):
            general = general or "g" in s.w[j]
            j += 1
        if j <= b and s.w[j] == "--":
            j += 1
        if not general:
            return None, take(j), opts
    elif verb == "run":
        repo, j = (s.w[j] if j <= b else None), j + 1
    else:
        return None, b + 1, opts
    if j <= b and s.k[j] == "w" and _base(s.w[j]) == "git":
        return repo, take(j + 1), opts
    return repo, b + 1, opts


def git_call(s, g, b):
    """(repository, index of the subcommand word) of the git call at g, past its global options;
    the index is beyond b when the segment ends first or the call is no git call. The repository
    is the name a wrapper such as vcsh takes, None when it takes none or acts on every one."""
    repo, sub, _ = _git_walk(s, g, b)
    return repo, sub


def git_subcommand(s, g, b):
    """The index of the subcommand word of the git call at g, past its global options
    (and the repository name a wrapper takes); beyond b when the segment ends first."""
    return git_call(s, g, b)[1]


def git_verb(wrapper, word):
    """The subcommand `word` names after the wrapper word: vcsh's abbreviation of a verb is the verb."""
    return VCSH_VERBS.get(word, word) if git_wrapper(wrapper)[1].repo else word


def git_options(s, g, sub):
    """The index of each global option word of the git call at g, before its subcommand at sub."""
    return iter(_git_walk(s, g, sub - 1)[2])


def wrapper_git(wrapper, repo, env):
    """(program, leading arguments) that run plain git for a call by `wrapper` (its word) on `repo`, or
    None when no such call can be made safely. A guard never runs vcsh, whose verbs change the
    system: it runs git against the repository's own git dir, the one vcsh keeps under
    $XDG_CONFIG_HOME/vcsh/repo.d (VCSH_REPO_D and vcsh's config file are not read), with the work
    tree at $HOME. A name that is a vcsh verb or a path, or an environment that does not say where, is None."""
    name, row = git_wrapper(wrapper)
    if not row.repo:
        return name, ()
    home = env.get("HOME") or ""
    conf = env.get("XDG_CONFIG_HOME") or (home and home + "/.config")
    if (not repo or repo in VCSH_VERBS or "/" in repo or repo[0] in ".-"
            or not home.startswith("/") or not conf.startswith("/")):
        return None
    return "git", (f"--git-dir={conf}/vcsh/repo.d/{repo}.git", f"--work-tree={home}")
