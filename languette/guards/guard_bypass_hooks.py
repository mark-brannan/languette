"""guard-bypass-hooks: `git commit --no-verify`, `git commit -n` and `git push
--no-verify` run only after the user said yes to that one run, through
AskUserQuestion; with no approval they are denied.

A hook that blocks a commit or push is telling the agent something, and
skipping the repo's hooks is the user's call, never the agent's. On push, -n
is --dry-run, not no-verify, and passes. `yadm` counts as git. The command is
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
from languette.guards.ask_first import LOOP, claim
from languette.verdict import deny

NAME = "guard-bypass-hooks"
APPROVE_LABEL = "Skip hooks once"

GIT = re.compile(r"(?:^|/)(?:git|yadm)\Z")
# git's global options that take a value as the next word.
GLOBAL_VALUE = frozenset("-C -c --git-dir --work-tree --namespace --config-env --attr-source".split())
# Options that take the next word as a value, so a message that is just
# `--no-verify` is a message. Short ones are the letters, tried in a cluster.
VALUE = {
    "commit": (frozenset("mFCct"), frozenset(
        "--message --file --reuse-message --reedit-message --author --date --template "
        "--cleanup --fixup --squash --trailer".split())),
    "push": (frozenset("o"), frozenset("--push-option --repo --receive-pack --exec".split())),
}
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
                if ch == "n" and sub == "commit":
                    return True
    return False


def _runs(text):
    """(how many times `text` skips the hooks, whether any of it is in a loop)."""
    n, loop = 0, False
    for t, nested in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        loop = loop or any(k == "w" and w in LOOP for k, w in zip(s.k, s.w))
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, GIT, nested)
            if g is None:
                continue
            i = g + 1
            while i <= b and s.k[i] == "w" and s.w[i].startswith("-"):
                i += 1 + (s.w[i] in GLOBAL_VALUE)
            if i > b or s.k[i] != "w" or s.w[i] not in VALUE:
                continue
            if _skips(s.w[i], s.w[i + 1:b + 1]):
                n += 1
    return n, loop


def check(payload, env=None):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    runs, looped = _runs(cmd + "\n")
    if not runs:
        return None
    if looped:
        return deny(f"{NAME}: --no-verify inside a loop, xargs, parallel or watch skips the hooks an "
                    "unknown number of times, and each run needs its own approval. Fix what the blocking "
                    "hook reported, or run it once, on its own, after asking.")
    try:
        approved, spent = claim(payload, {APPROVE_LABEL: runs})
    except (OSError, ValueError) as e:
        return deny(f"{NAME}: cannot read the session transcript to look for the user's approval, or "
                    f"record it as spent ({e}), so `{cmd.strip()}` is denied. Fix what the blocking "
                    "hook reported, or ask the user to run it themselves.")
    if spent:
        return None
    have = len(approved[APPROVE_LABEL])
    return deny(f"{NAME}: --no-verify skips this repo's hooks, and that is the user's call, not "
                f"yours: a hook that blocks a commit or push is telling you something. "
                f"`{cmd.strip()}` skips them {runs} time{'s' * (runs > 1)} and has {have} "
                f"unspent approval{'s' * (have != 1)}. "
                f"Better, fix what the blocking hook reported and run it without the flag. "
                f"If the user must have the hooks skipped, call AskUserQuestion: give the exact "
                f"command and why it cannot pass the hooks, with one option labelled exactly "
                f"\"{APPROVE_LABEL}\" and one to decline. One approval is one run; ask again "
                f"before skipping the hooks again.")
