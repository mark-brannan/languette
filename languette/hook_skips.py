"""guard-bypass-hooks' walk and its handler (languette/rules/guard_bypass_hooks.py is the
rule set): `--no-verify` on `git commit`, `push`, `merge`, `pull`,
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

Approval is the mechanism ask-first uses (languette/listed_runs.py): the
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


def _skips(sub, args):
    """Does `git <sub> <args>` skip the hooks?"""
    short, long_ = VALUE[sub]
    i = 0
    while i < len(args):
        w = args[i]
        i += 1
        if w == "--":
            break
        if sw.long_option(w, FLAG, sub):
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
        call = sw.GitCall(s, a, g, b)
        if any(c and c.split("=", 1)[0] == "core.hookspath" for c in call.configs):
            n += 1
        elif call.verb in VALUE and s.k[call.sub] == "w" and _skips(call.verb, s.w[call.sub + 1:b + 1]):
            n += 1
    return n, loop


def skips(doc):
    """The `skips-hooks` test: {"runs": how many times the command skips the hooks, "looped":
    whether any of it is in a loop}, or None when it never does."""
    if not doc.text or not doc.text.strip():
        return None
    runs, looped = _runs(doc)
    return {"runs": runs, "looped": looped} if runs else None


def approval(doc, guard, found):
    """The `hooks-approval` handler: each run that skips the hooks spends one of the user's
    approvals; short of one per run, or in a loop, the call is denied."""
    runs = found["runs"]
    if found["looped"]:
        return deny(say("loop_hooks", guard=guard))
    shown = quote(doc) or say("command_withheld")
    approved, done = yield from approve(
        {APPROVE_LABEL: runs},
        lambda e: say("transcript_unreadable", guard=guard, err=e, cmd=shown,
                      then="Fix what the blocking hook reported, or ask the user to run it themselves."))
    if done:
        return done[0]
    have = len(approved[APPROVE_LABEL])
    return deny(say("hooks_skipped", guard=guard, cmd=shown, runs=runs, runs_s="s" * (runs > 1),
                    have=have, have_s="s" * (have != 1), label=APPROVE_LABEL))
