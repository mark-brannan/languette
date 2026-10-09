"""guard-host-availability: features/guard-host-availability.feature is the spec.

Blocks the commands that take the machine down: shutdown, reboot, halt and
poweroff, at command position or as the one-word script of `sh -c`, the
fork-bomb shape, and a `systemctl` verb that stops a host service or the host
itself (the user's own `--user` manager and a remote `-H`/`-M` host are not the
host). An unknown first word after systemctl's options fails closed.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-host-availability"

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_CTL = re.compile(r"(?:^|/)systemctl\Z")
_CTL_OTHER = {"--user", "-H", "--host", "-M", "--machine"}
_CTL_DOWN = {"stop", "restart", "try-restart", "reload-or-restart", "try-reload-or-restart", "kill",
             "isolate", "rescue", "emergency", "halt", "poweroff", "reboot", "kexec", "soft-reboot"}
# Options that take a separate value; the value is not the verb. A missing one only fails closed.
_CTL_ARG = {"-t", "--type", "-p", "--property", "-s", "--signal", "-n", "--lines", "-o", "--output",
            "--root", "--state", "--job-mode", "--kill-whom", "--kill-who", "--preset-mode", "--timestamp"}
# Verbs whose own arguments may be any word, so a later `stop` is a unit or pattern, not a verb.
_CTL_READ = {"status", "show", "cat", "help", "list-units", "list-unit-files", "list-sockets", "list-timers",
             "list-jobs", "list-dependencies", "list-automounts", "list-paths", "list-machines",
             "is-active", "is-enabled", "is-failed", "is-system-running", "show-environment", "get-default",
             "start", "reload", "enable", "reenable", "daemon-reload"}
_FORK = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&")
_WAY_USER = "That is the user's to run, not an agent's: say what you need and hand them the exact command."


def _power(s, a, b):
    g = sw.cmd_index(s, a, b, _POWER, True)
    if g is None:                              # `sh -c reboot`: a one-word script is not a nested text
        g = next((i for i in range(a + 1, b + 1) if s.k[i] == "w" and _POWER.search(s.w[i])
                  and re.fullmatch(r"-[A-Za-z]*c", s.w[i - 1])), None)
    return None if g is None else os.path.basename(s.w[g])


def _service_stop(s, a, b):
    """The verb when the segment stops a host service, or the host, with systemctl, else None."""
    g = sw.cmd_index(s, a, b, _CTL, True)
    if g is None:
        return None
    words = [s.w[i] for i in range(g + 1, b + 1) if s.k[i] == "w"]
    if any(w in _CTL_OTHER or w.startswith(("--host=", "--machine=")) for w in words):
        return None
    pos = [w for i, w in enumerate(words) if not w.startswith("-") and (i == 0 or words[i - 1] not in _CTL_ARG)]
    if pos and pos[0] in _CTL_READ:
        return None
    # The verb is the first word past the options, but an option's value looks like a word too
    # (`--root /x stop`), so any down verb in the segment counts unless a read verb leads.
    return next((w for w in pos if w in _CTL_DOWN), None)

def judge(text):
    """The deny reason for `text`, or None."""
    for t, _ in sw.texts_of(sw.strip_heredocs(text)):
        s = sw.Scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        for a, b in segs:
            what = _power(s, a, b)
            if what:
                return f"`{what}` is blocked: it takes the machine down, with the user's session on it. {_WAY_USER}"
        for a, b in segs:
            verb = _service_stop(s, a, b)
            if verb:
                return (f"`systemctl {verb}` is blocked: it takes a host service or the host down, with the "
                        f"user's session possibly on it. {_WAY_USER}")
        # The fork bomb is raw text, so a commit message that quotes it must not trip it:
        # only a text with a segment that is not led by a prose consumer is read.
        if any(sw.seg_cmd(s, a, b) is None or s.w[sw.seg_cmd(s, a, b)] not in sw.PROSE or s.shellseg
               for a, b in segs) and _FORK.search(t):
            return ("`:(){ :|:& };:` is blocked: that is the fork-bomb shape, a function that pipes itself into "
                    f"itself in the background, and it freezes the machine. {_WAY_USER}")
    return None


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    why = judge(cmd + "\n")
    return deny(f"{NAME}: {why}") if why else None
