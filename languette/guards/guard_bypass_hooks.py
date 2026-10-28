"""guard-bypass-hooks: `--no-verify` on `git commit`, `push`, `merge`, `pull`,
`rebase` and `am`, `-n` on commit and am, and `git -c core.hooksPath=...` (or
`--config-env`) run only after the user said yes to that one run, through
AskUserQuestion; with no approval they are denied.

A hook that blocks a commit or push is telling the agent something, and
skipping the repo's hooks is the user's call, never the agent's. On push -n
is --dry-run, and on merge, pull and rebase it is --no-stat; those pass.
`yadm` and `vcsh` count as git. Not seen: a git alias that adds the flag, and
core.hooksPath set by `git config` or the GIT_CONFIG_* environment. The command is
read the way the other guards read one: through wrappers, `sh -c "..."`, env
prefixes and git's global options, and a message or heredoc that merely names
the flag is not the flag.

Approval is the mechanism ask-first uses (languette.guards.ask_first): the
user's answer to an AskUserQuestion is exactly APPROVE_LABEL, the question's
text proves nothing, and each approval allows one run: it is recorded as
spent beside the transcript and never counts again. A command that skips the
hooks twice needs two approvals; one inside a loop or xargs is denied
outright.
"""

import re

from languette import scan as sw
from languette.messages import say
from languette.secrets import quote
from languette.verdict import approve, deny

NAME = "guard-bypass-hooks"
APPROVE_LABEL = "Skip hooks once"

# Options that take the next word as a value, so a message that is just
# `--no-verify` is a message. Short ones are the letters, tried in a cluster.
VALUE = {
    "commit": (frozenset("mFCct"), frozenset(
        "--message --file --reuse-message --reedit-message --author --date --template "
        "--cleanup --fixup --squash --trailer".split())),
    "push": (frozenset("o"), frozenset("--push-option --repo --receive-pack --exec".split())),
    "merge": (frozenset("sXmF"), frozenset("--cleanup --strategy --strategy-option --message --file --into-name".split())),
    "pull": (frozenset("sXo"), frozenset(
        "--cleanup --strategy --strategy-option --upload-pack --depth --shallow-since --shallow-exclude "
        "--deepen --refmap --server-option --negotiation-tip".split())),
    "rebase": (frozenset("CxsX"), frozenset("--onto --whitespace --exec --strategy --strategy-option".split())),
    "am": (frozenset("Cp"), frozenset(
        "--quoted-cr --whitespace --directory --exclude --include --patch-format".split())),
}
# Where -n is --no-verify; elsewhere it is --dry-run or --no-stat.
SHORT_N = frozenset(("commit", "am"))
FLAG = "--no-verify"


def _is_flag(w):
    """git takes any unambiguous prefix of a long option; shorter than
    --no-veri is ambiguous with --no-verbose, and git refuses it anyway."""
    return len(w) >= 9 and FLAG.startswith(w)


def _skips(sub, args):
    """Does `git <sub> <args>` skip the hooks?"""
    short, long_ = VALUE[sub]
    i = 0
    while i < len(args):
        w = args[i]
        i += 1
        if w == "--":
            break
        if _is_flag(w):
            return True
        if w in long_:
            i += 1
        elif re.fullmatch(r"-[A-Za-z0-9]+", w):
            for n, ch in enumerate(w[1:], 1):
                if ch in short:
                    i += n == len(w) - 1       # the value is the next word unless attached
                    break
                if ch == "n" and sub in SHORT_N:
                    return True
    return False


def _runs(doc):
    """(how many times the command skips the hooks, whether any of it is in a loop)."""
    n, (segs, loop) = 0, sw.segments(doc)
    for s, a, b, nested in segs:
        g = sw.cmd_index(s, a, b, sw.GIT, nested)
        if g is None:
            continue
        i, hooks_path = sw.git_subcommand(s, g, b), False
        for j in sw.git_options(s, g, i):
            w = s.w[j]
            v = w[len("--config-env="):] if w.startswith("--config-env=") else (
                s.w[j + 1] if w in ("-c", "--config-env") and j < b and s.k[j + 1] == "w" else "")
            hooks_path = hooks_path or v.split("=", 1)[0].lower() == "core.hookspath"
        if hooks_path:
            n += 1
        elif i <= b and s.k[i] == "w" and sw.git_verb(s.w[g], s.w[i]) in VALUE and _skips(sw.git_verb(s.w[g], s.w[i]), s.w[i + 1:b + 1]):
            n += 1
    return n, loop


def check(doc):
    cmd = doc.text
    if not cmd or not cmd.strip():
        return None
    runs, looped = _runs(doc)
    if not runs:
        return None
    if looped:
        return deny(say("loop_hooks", guard=NAME))
    approved, done = yield from approve(
        {APPROVE_LABEL: runs},
        lambda e: say("transcript_unreadable", guard=NAME, err=e, cmd=quote(doc),
                      then="Fix what the blocking hook reported, or ask the user to run it themselves."))
    if done:
        return done[0]
    have = len(approved[APPROVE_LABEL])
    return deny(say("hooks_skipped", guard=NAME, cmd=quote(doc), runs=runs, runs_s="s" * (runs > 1),
                    have=have, have_s="s" * (have != 1), label=APPROVE_LABEL))
