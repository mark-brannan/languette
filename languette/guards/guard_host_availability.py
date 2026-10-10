"""guard-host-availability: features/guard-host-availability.feature is the spec.

Blocks the commands that take the machine down: shutdown, reboot, halt and
poweroff, at command position or as the one-word script of `sh -c`, the
fork-bomb shape, and a `systemctl` verb (or the SysV `service`, `invoke-rc.d`,
`rc-service` and `/etc/init.d/<unit>` stop and restart) that takes the host down
or stops a service the user's session runs on (ssh, login, dbus, the network,
the display manager). The user's own `--user` manager and a remote `-H`/`-M` host are not
the host. Any other service is the agent's to stop, unless the user lists it
in guard-protected-services.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-host-availability"

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_CTL = re.compile(r"(?:^|/)systemctl\Z")
_SYSV = re.compile(r"(?:^|/)(?:service|invoke-rc\.d|rc-service)\Z")
_INITD = re.compile(r"(?:^|/)etc/init\.d/[^/]+\Z")
_SERVICE_STOP = {"stop", "restart", "force-reload", "try-restart", "--full-restart"}
_CTL_OTHER = {"--user", "-H", "--host", "-M", "--machine"}
_CTL_HOST = {"isolate", "rescue", "emergency", "halt", "poweroff", "reboot", "kexec", "soft-reboot"}
_CTL_STOP = {"stop", "restart", "try-restart", "reload-or-restart", "try-reload-or-restart", "kill"}
# The services a session runs on: stopping one cuts the user off the machine.
_CORE = {"ssh", "sshd", "systemd-logind", "dbus", "dbus-broker", "NetworkManager", "systemd-networkd", "networking",
         "display-manager", "gdm", "gdm3", "sddm", "lightdm", "getty", "user",
         "multi-user", "graphical", "default", "network", "network-online", "basic", "sysinit"}
# Options that take a separate value; the value is not the verb. A missing one only fails closed.
_CTL_ARG = {"-t", "--type", "-p", "--property", "-s", "--signal", "-n", "--lines", "-o", "--output",
            "--root", "--state", "--job-mode", "--kill-whom", "--kill-who", "--preset-mode", "--timestamp"}
# Options that take no value. Any option in neither set, before the verb, means the verb cannot be
# known, so a read verb after it does not clear the segment.
_CTL_FLAG = {"-a", "--all", "-l", "--full", "-q", "--quiet", "-r", "--recursive", "-f", "--force", "-i",
             "-T", "--show-transaction", "--now", "--no-pager", "--no-legend", "--no-block", "--no-wall",
             "--no-ask-password", "--failed", "--system", "--reverse", "--after", "--before", "--plain",
             "--value", "--dry-run", "--wait", "--global", "--runtime"}
# Verbs whose own arguments may be any word, so a later `reboot` is a unit or pattern, not a verb.
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


def unit_names(u):
    """The names `u` answers to: as written, without its unit-type suffix, and without its `@instance`."""
    bare = re.sub(r"\.(?:service|socket|target|scope|slice)\Z", "", u)
    return {u, bare, bare.split("@")[0]}


def _core_unit(u):
    """True when the unit is, or may match, one the session runs on. A glob fails closed."""
    if any(c in u for c in "*?["):
        return True
    return any(n in _CORE or n.startswith("session-") for n in unit_names(u))


def service_stop(s, a, b, hit, host_verbs=_CTL_HOST):
    """`<verb>` or `<verb> <unit>` when the segment's host `systemctl` runs one of `host_verbs`,
    or stops a unit `hit` accepts; else None."""
    g = sw.cmd_index(s, a, b, _CTL, True)
    if g is None:
        return None
    words = [s.w[i] for i in range(g + 1, b + 1) if s.k[i] == "w"]
    pos, skip, known = [], False, True
    for w in words:
        if skip:
            skip = False
        elif w in _CTL_OTHER or w.startswith(("--host=", "--machine=")):
            return None                        # tested here, so an option's value (`--root -M`) is not it
        elif w in _CTL_ARG:
            skip = True
        elif w.startswith("-"):
            known = known and (w in _CTL_FLAG or ("=" in w and w.startswith("--")) or bool(pos))
        else:
            pos.append(w)
    if known and pos and pos[0] in _CTL_READ:
        return None
    # The verb is the first word past the options, but an option's value looks like a word too
    # (`--root /x reboot`), so any down verb in the segment counts unless a read verb leads.
    for i, w in enumerate(pos):
        if w in host_verbs:
            return w
        if w in _CTL_STOP or (w in ("disable", "mask") and "--now" in words):
            unit = next((u for u in pos[i + 1:] if hit(u)), None)
            if unit:
                return f"{w} {unit}"
    return None


def sysv_stop(s, a, b):
    """`<command> <unit> <verb>` when the segment's SysV `service`, `invoke-rc.d`, `rc-service` or
    `/etc/init.d/<unit>` stops or restarts a unit the session runs on; else None. The verb is any word
    of the segment (`service ssh --full-restart`, `service -v ssh stop`), not only the second."""
    g = sw.cmd_index(s, a, b, _SYSV, True)
    init = g is None
    if init:
        g = sw.cmd_index(s, a, b, _INITD, True)
        if g is None:
            return None
    words = [s.w[i] for i in range(g + 1, b + 1) if s.k[i] == "w"]
    verb = next((w for w in words if w in _SERVICE_STOP), None)
    if verb is None:
        return None
    units = [os.path.basename(s.w[g])] if init else [w for w in words if not w.startswith("-")]
    unit = next((u for u in units if u != verb and _core_unit(u)), None)
    if unit is None:
        return None
    return f"{os.path.basename(s.w[g])} {unit} {verb}" if not init else f"{s.w[g]} {verb}"


def judge(doc):
    """The deny reason for the command, or None."""
    for t, _ in doc.texts():
        s = doc.scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        for a, b in segs:
            what = _power(s, a, b)
            if what:
                return f"`{what}` is blocked: it takes the machine down, with the user's session on it. {_WAY_USER}"
        for a, b in segs:
            verb = service_stop(s, a, b, _core_unit)
            if verb:
                return (f"`systemctl {verb}` is blocked: it takes down the host or a service the "
                        f"user's session runs on. {_WAY_USER}")
        for a, b in segs:
            verb = sysv_stop(s, a, b)
            if verb:
                return (f"`{verb}` is blocked: it takes down a service the "
                        f"user's session runs on. {_WAY_USER}")
        # The fork bomb is raw text, so a commit message that quotes it must not trip it:
        # only a text with a segment that is not led by a prose consumer is read.
        if any(sw.seg_cmd(s, a, b) is None or s.w[sw.seg_cmd(s, a, b)] not in sw.PROSE or s.shellseg
               for a, b in segs) and _FORK.search(t):
            return ("`:(){ :|:& };:` is blocked: that is the fork-bomb shape, a function that pipes itself into "
                    f"itself in the background, and it freezes the machine. {_WAY_USER}")
    return None


def check(doc):
    payload = doc.payload
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    why = judge(doc)
    return deny(f"{NAME}: {why}") if why else None
