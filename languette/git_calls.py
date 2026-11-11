"""A git call's words, read once (GitCall): the wrapper that runs it (git,
yadm, vcsh), its repository, global options, `-c` values, the places it is
pointed at, subcommand and operands; and the plain git that stands in for a
wrapper. Beside it, the readers every git walk shares: git's long-option
abbreviation (long_option, over GIT_LONG) and git add's options (add_options).
"""

import re

from .lexicon import GIT_VALUE, GIT_WRAPPERS, _base
from .messages import say
from .verdict import Refuse


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


def git_verb(wrapper, word):
    """The subcommand `word` names after the wrapper word: vcsh's abbreviation of a verb is the verb."""
    return VCSH_VERBS.get(word, word) if git_wrapper(wrapper)[1].repo else word


def git_env(word):
    """("GITDIR" or "WORKTREE", value) for a `GIT_DIR=` or `GIT_WORK_TREE=` word, which points
    every git it reaches at another repository or work tree; None for any other word."""
    for name, kind in (("GIT_DIR=", "GITDIR"), ("GIT_WORK_TREE=", "WORKTREE")):
        if word.startswith(name):
            return kind, word[len(name):]
    return None


# The global options that move git to another directory, repository or work tree, by kind.
_PLACES = {"-C": "C", "--git-dir": "GITDIR", "--work-tree": "WORKTREE"}


class GitCall:
    """One git call at g in segment a..b, read once: the wrapper (prog, its GIT_WRAPPERS row),
    the repository a wrapper names (repo), the global options (opts, their indexes), the
    subcommand's index (sub, beyond b when there is none) and the subcommand it names (verb,
    None when there is none), the `-c`/`--config-env` settings (configs, lower-cased
    `name=value`, None for one with no value), the places it is pointed at (places: (kind,
    value, index of the word holding the value), kind "GITDIR" or "WORKTREE" for a
    `GIT_DIR=`/`GIT_WORK_TREE=` word before git and for `--git-dir`/`--work-tree`, "C" for
    `-C`, in the order the words stand, value None when the segment ends first), and the
    operands' indexes past the subcommand (args)."""

    def __init__(self, s, a, g, b):
        self.prog, self.row = git_wrapper(s.w[g])
        self.repo, self.sub, self.opts = _git_walk(s, g, b)
        self.verb = git_verb(s.w[g], s.w[self.sub]) if self.sub <= b else None
        self.args = range(self.sub + 1, b + 1)
        self.places = [(e[0], e[1], i) for i in range(a, g) if s.k[i] == "w" for e in [git_env(s.w[i])] if e]
        self.configs = []
        for i in self.opts:
            x, nxt = s.w[i], (s.w[i + 1] if i + 1 <= b else None)
            name, eq, val = x.partition("=")
            if name in _PLACES and (not eq or name != "-C"):   # only a long option takes `=value`
                self.places.append((_PLACES[name], val, i) if eq else (_PLACES[name], nxt, i + 1))
            if x in ("-c", "--config-env"):
                self.configs.append(nxt.lower() if nxt is not None else None)
            elif x.startswith("--config-env="):
                self.configs.append(x[len("--config-env="):].lower())
            elif x.startswith("-c") and not x.startswith("--"):
                self.configs.append(x[2:].lower())


def _long(names):
    """`[no-]x` is `--x` and `--no-x`, as git's usage text lists a negatable option."""
    out = set()
    for n in names.split():
        out.update(("--" + n[5:], "--no-" + n[5:]) if n.startswith("[no-]") else ("--" + n,))
    return frozenset(out)


# The long options of the subcommands a guard reads, as `git <sub> -h` lists them (git 2.53).
# Only an option git has belongs here: one it lacks would make a real abbreviation look
# ambiguous, and the guard would miss it. One missing only makes the guard read an
# abbreviation git refuses.
GIT_LONG = {
    "push": _long(
        "[no-]all [no-]atomic [no-]branches [no-]delete [no-]dry-run [no-]exec [no-]follow-tags "
        "[no-]force [no-]force-if-includes [no-]force-with-lease ipv4 ipv6 [no-]mirror no-verify "
        "[no-]porcelain [no-]progress [no-]prune [no-]push-option [no-]quiet [no-]receive-pack "
        "[no-]recurse-submodules [no-]repo [no-]set-upstream [no-]signed [no-]tags [no-]thin "
        "[no-]verbose verify"),
    "reset": _long(
        "hard [no-]intent-to-add inter-hunk-context keep merge mixed no-refresh [no-]patch "
        "[no-]pathspec-file-nul [no-]pathspec-from-file [no-]quiet [no-]recurse-submodules refresh "
        "soft unified"),
    "clean": _long(
        "[no-]dry-run exclude [no-]force [no-]interactive [no-]quiet"),
    "branch": _long(
        "[no-]abbrev all [no-]color [no-]column contains [no-]copy [no-]create-reflog [no-]delete "
        "[no-]edit-description [no-]force [no-]format [no-]ignore-case [no-]list merged [no-]move "
        "no-contains no-merged [no-]omit-empty [no-]points-at [no-]quiet [no-]recurse-submodules "
        "remotes [no-]set-upstream-to [no-]show-current [no-]sort [no-]track [no-]unset-upstream "
        "[no-]verbose"),
    "restore": _long(
        "[no-]conflict [no-]ignore-skip-worktree-bits [no-]ignore-unmerged inter-hunk-context "
        "[no-]merge ours [no-]overlay [no-]patch [no-]pathspec-file-nul [no-]pathspec-from-file "
        "[no-]progress [no-]quiet [no-]recurse-submodules [no-]source [no-]staged theirs unified "
        "[no-]worktree"),
    "checkout": _long(
        "[no-]conflict [no-]detach [no-]force [no-]guess [no-]ignore-other-worktrees "
        "[no-]ignore-skip-worktree-bits inter-hunk-context [no-]merge [no-]orphan ours [no-]overlay "
        "[no-]overwrite-ignore [no-]patch [no-]pathspec-file-nul [no-]pathspec-from-file "
        "[no-]progress [no-]quiet [no-]recurse-submodules theirs [no-]track unified"),
    "commit": _long(
        "[no-]ahead-behind [no-]all allow-empty allow-empty-message [no-]amend [no-]author "
        "[no-]branch [no-]cleanup [no-]date [no-]dry-run [no-]edit [no-]file [no-]fixup [no-]gpg-sign "
        "[no-]include inter-hunk-context [no-]interactive [no-]long [no-]message no-post-rewrite "
        "no-verify [no-]null [no-]only [no-]patch [no-]pathspec-file-nul [no-]pathspec-from-file "
        "[no-]porcelain post-rewrite [no-]quiet [no-]reedit-message [no-]reset-author "
        "[no-]reuse-message [no-]short [no-]signoff [no-]squash [no-]status [no-]template trailer "
        "unified [no-]untracked-files [no-]verbose verify"),
    "merge": _long(
        "[no-]abort [no-]allow-unrelated-histories [no-]autostash [no-]cleanup [no-]commit "
        "[no-]compact-summary [no-]continue [no-]edit [no-]ff ff-only file [no-]gpg-sign "
        "[no-]into-name [no-]log [no-]message no-verify [no-]overwrite-ignore [no-]progress "
        "[no-]quiet [no-]quit [no-]rerere-autoupdate [no-]signoff [no-]squash [no-]stat [no-]strategy "
        "[no-]strategy-option [no-]summary [no-]verbose verify [no-]verify-signatures"),
    "pull": _long(
        "[no-]all [no-]allow-unrelated-histories [no-]append [no-]autostash [no-]cleanup [no-]commit "
        "[no-]compact-summary [no-]deepen [no-]depth [no-]dry-run [no-]edit [no-]ff ff-only "
        "[no-]force [no-]gpg-sign [no-]ipv4 [no-]ipv6 [no-]jobs [no-]keep [no-]log "
        "[no-]negotiation-tip [no-]progress [no-]prune [no-]quiet [no-]rebase [no-]recurse-submodules "
        "refmap [no-]server-option [no-]set-upstream [no-]shallow-exclude [no-]shallow-since "
        "[no-]show-forced-updates [no-]signoff [no-]squash [no-]stat [no-]strategy "
        "[no-]strategy-option [no-]tags unshallow [no-]update-shallow [no-]upload-pack [no-]verbose "
        "[no-]verify [no-]verify-signatures"),
    "rebase": _long(
        "abort apply [no-]autosquash [no-]autostash [no-]committer-date-is-author-date continue "
        "edit-todo empty [no-]exec ff [no-]force-rebase [no-]fork-point [no-]gpg-sign "
        "[no-]ignore-whitespace interactive [no-]keep-base merge no-ff no-stat no-verify [no-]onto "
        "[no-]quiet quit [no-]reapply-cherry-picks [no-]rebase-merges [no-]rerere-autoupdate "
        "[no-]reschedule-failed-exec [no-]reset-author-date [no-]root show-current-patch [no-]signoff "
        "skip stat [no-]strategy [no-]strategy-option [no-]update-refs [no-]verbose verify "
        "[no-]whitespace"),
    "am": _long(
        "abort allow-empty [no-]committer-date-is-author-date continue [no-]directory empty "
        "[no-]exclude [no-]gpg-sign [no-]ignore-date [no-]ignore-space-change [no-]ignore-whitespace "
        "[no-]include [no-]interactive [no-]keep [no-]keep-cr [no-]keep-non-patch [no-]message-id "
        "no-verify [no-]patch-format [no-]quiet quit quoted-cr [no-]reject [no-]rerere-autoupdate "
        "resolved [no-]resolvemsg retry [no-]scissors show-current-patch [no-]signoff skip [no-]utf8 "
        "verify [no-]whitespace"),
}


def long_option(word, full, sub=None):
    """Whether `word`, less any `=value`, is the long option `full` as git reads it: `full`
    itself, or a prefix of it (`--al` for `--all`) that no other long option of the
    subcommand `sub` (GIT_LONG) starts with. git takes any unambiguous prefix and refuses an
    ambiguous one; `--` and one letter more is the shortest prefix read. Without `sub`, or
    for one GIT_LONG lacks, any such prefix is `full`."""
    name = word.split("=", 1)[0]
    if name == full:
        return True
    return (len(name) > 2 and name.startswith("--") and full.startswith(name)
            and not any(o != full and o.startswith(name) for o in GIT_LONG.get(sub, ())))


class UnreadOption(Refuse):
    """A word an option reader cannot take apart; str() says why. A guard that reads
    it as a refusal lets it carry up as one."""


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
    unknown or ambiguous name raises UnreadOption."""
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
        raise UnreadOption(say("wl_add_unknown", t=t))
    full, negated = hit[0]
    if eq and not _ADD_LONG[full][0]:
        raise UnreadOption(say("wl_add_no_value", t=t))
    return full, negated, (val if eq else None)


def add_options(a):
    """Split git add's words into the options set (canonical names, a negated one as no-<name>)
    and the pathspecs' indexes into a, from git's own option table. A value option eats the
    next word when its value is not glued on; `--` and `--end-of-options` end the options. A
    word it cannot read raises UnreadOption."""
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
                    raise UnreadOption(say("wl_add_needs_value", t=t))
                i += 1
            opts.append(("no-" if negated else "") + full)
        elif t.startswith("-") and t != "-":
            for j, ch in enumerate(t[1:], 1):
                full = _ADD_SHORT.get(ch)
                if full is None:
                    raise UnreadOption(say("wl_add_unknown_short", t=t, ch=ch))
                opts.append(full)
                if _ADD_LONG[full][0]:
                    if j == len(t) - 1:
                        if i >= n:
                            raise UnreadOption(say("wl_add_needs_value", t=t))
                        i += 1
                    break
        else:
            specs.append(i - 1)
    return opts, specs


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
