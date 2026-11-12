"""The commands the scan knows by name: git and the tools that run it, the
forge clients, prose consumers, executors, wrappers and launchers. And the
readers that take a program's words apart: operands, getopt, listed.
"""

import re
from collections import namedtuple


# The tools that run git. home: its work tree is always $HOME, wherever it runs.
# repo: it takes the name of one of its repositories before the git arguments.
Wrapper = namedtuple("Wrapper", "home repo")
GIT_WRAPPERS = {"git": Wrapper(False, False), "yadm": Wrapper(True, False), "vcsh": Wrapper(True, True)}
GIT = re.compile(r"(?:^|/)(?:" + "|".join(GIT_WRAPPERS) + r")\Z")
GH = re.compile(r"(?:^|/)gh\Z")
GLAB = re.compile(r"(?:^|/)glab\Z")
# Either forge's client (docs/design/forges.md); client() says which a word is.
CLIENTS = re.compile(r"(?:^|/)(?:gh|glab)\Z")


def basename(w):
    """The name a command word runs: its last path part (`/usr/bin/git` is `git`)."""
    return w.rsplit("/", 1)[-1]


def client(w):
    """"gh" or "glab" for a word CLIENTS matches, by its basename."""
    return basename(w)


# A word that is cd, pushd or popd: the builtins that move the working directory.
CD = re.compile(r"\A(?:cd|pushd|popd)\Z")
# git's global options that take the next word as their value.
GIT_VALUE = frozenset("-C -c --git-dir --work-tree --namespace --config-env --attr-source".split())
# `git push`'s options that take the next word as their value. A push takes any unambiguous prefix
# of a long option; --exec is --receive-pack.
GIT_PUSH_VALUE = frozenset("-o --push-option --repo --receive-pack --exec".split())
PROSE = frozenset("grep egrep fgrep rg ag ack echo printf gh glab sed awk jq yq "
                  "cat tee test [ diff sort head tail wc tr cut less more".split()) | frozenset(GIT_WRAPPERS)
# Process tools name a script to find it, not to run it.
PROSE_PROCESS = PROSE | frozenset("pkill pgrep killall ps lsof fuser which type".split())
LAUNCH = frozenset("npx bunx pnpm yarn bun".split())
LAUNCH_SUB = frozenset("exec dlx x".split())
# Package managers that stand in for each other in a command rule, and npm's aliases for `run`.
PM = frozenset("npm pnpm yarn bun".split())
RUN = frozenset("run run-script rum urn".split())
# Words that run what follows an unknown number of times.
LOOP = frozenset("for while until select xargs parallel watch -exec -execdir -ok -okdir".split())
EXEC = frozenset("sh bash zsh dash ksh ash busybox eval exec xargs su ssh sudo doas env nohup "
                 "timeout nice time watch parallel script chroot docker podman kubectl".split())
_FIND_EXECS = frozenset("-exec -execdir -ok -okdir".split())
_FIND_WRAPPERS = frozenset("sudo doas env nice nohup time command exec ionice xargs stdbuf timeout".split())
SHELL = frozenset("sh bash zsh dash ksh ash eval source .".split())
WRAP = frozenset("sudo env command exec time nice nohup timeout doas builtin "
                 "if then else elif while until do !".split())


def operands(words, valued=(), options=False):
    """`words` less each option in `valued` and its value, read as getopt reads them (a
    cluster `-xn ns` included); the other options stay only when `options`, each word once.
    An option outside `valued` is read as a flag, and `--` is one too. `valued` is a
    program's own table of options that take a value."""
    keep, valued = {}, frozenset(valued)
    for i, opt, w in _getopt(words, dict.fromkeys(valued, 1), False, ()):
        keep[i] = keep.get(i, True) and (opt is None or (options and opt not in valued))
    return [words[i] for i, k in keep.items() if k]


def getopt(words, options, abbreviate=False, ends=("--",)):
    """Read `words` as a getopt_long parser does: yield (option, word) for each option set,
    and (None, word) for each operand, every word past one of `ends` included. `options`
    maps an option (`-c`, `--file`) to how many words its value takes when not glued on with
    = or to its short letter, 0 for a flag; an option it lacks is a flag, so it cannot hide
    what follows it. A cluster `-xvf` sets each letter up to a valued one, whose value is the
    rest. With `abbreviate`, a unique prefix of a long option in `options` is that option."""
    for _, opt, w in _getopt(words, options, abbreviate, ends):
        yield opt, w


def _getopt(words, options, abbreviate, ends):
    """getopt's reading, each item led by the index of its word."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        i += 1
        if w in ends:
            yield from ((x, None, words[x]) for x in range(i, n))
            return
        if w.startswith("--"):
            name, eq, _ = w.partition("=")
            same = [o for o in options if o == name]
            same = same or [o for o in options if abbreviate and o.startswith("--") and o.startswith(name)]
            name = same[0] if len(same) == 1 else name
            yield i - 1, name, w
            i += 0 if eq else options.get(name, 0)
        elif w.startswith("-") and w != "-":
            at = i - 1
            for j, ch in enumerate(w[1:], 1):
                yield at, "-" + ch, w
                if options.get("-" + ch):
                    i += options["-" + ch] if j == len(w) - 1 else 0
                    break
        else:
            yield i - 1, None, w


def listed(value):
    """The entries of a comma-separated setting, trimmed and non-empty; none
    when it is unset."""
    return [x.strip() for x in (value or "").split(",") if x.strip()]
