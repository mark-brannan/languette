"""The decision record (#82): one JSON line per hook call, built after the
verdict, never read by it. Pure: World.keep writes it.

Off unless record_decisions is on. The command is redacted to the programs
its segments run and its length; record_raw_commands keeps it whole, with
each guard's reason, which may quote it. `v` names the format, so a reader
can refuse one it does not know.

    {"v": 1, "t": "2026-10-07T23:09:07Z", "session": "a78b...", "call": "toolu_...",
     "event": "PreToolUse", "tool": "Bash", "run": "guard-disk", "rung": "shfmt",
     "command": {"redacted": true, "programs": ["git", "rm"], "length": 31},
     "findings": [{"guard": "guard-disk", "decision": "none"}], "verdict": "silent"}

Standard library only.
"""

import os
import time

from languette import scan

VERSION = 1
ON = "CLAUDE_PLUGIN_OPTION_RECORD_DECISIONS"
RAW = "CLAUDE_PLUGIN_OPTION_RECORD_RAW_COMMANDS"


def wanted(env):
    return env.get(ON) == "true"


def _finding(guard, r, crashed, raw):
    """One guard's finding: what it decided, and its words when raw."""
    r = r or {}
    f = {"guard": guard, "decision": r.get("permissionDecision") or ("context" if r.get("additionalContext") else "none")}
    if crashed:
        f["crashed"] = True
    why = r.get("permissionDecisionReason") or r.get("additionalContext")
    if raw and why:
        f["reason"] = why
    return f


# Shell words that lead a segment without being a program; past them is the program.
KEYWORDS = frozenset("if then else elif fi while until do done !".split())
# Words whose segment runs nothing: the rest of it is a name and a list (`for f in *.py`).
HEADERS = frozenset("for select case esac".split())


def programs(command):
    """The program each top-level segment runs, as its basename: the first word
    after assignments and shell keywords."""
    s = scan.Scan(command)
    out = []
    for a, b in s.segments():
        c = scan.seg_cmd(s, a, b) if a <= b else None
        while c is not None and c <= b and s.k[c] == "w" and s.w[c] in KEYWORDS:
            c += 1
        if c is None or c > b or s.k[c] != "w" or s.w[c] in HEADERS:
            continue
        out.append(os.path.basename(s.w[c]) or s.w[c])
    return out


def _rung(command):
    try:
        return scan.parse(command)[0], False
    except scan.Unparseable as e:
        return e.rung, True
    except Exception:  # noqa: BLE001 -- a record never fails the call
        return None, False


def build(payload, env, only, findings, verdict, clock=time.time):
    """The record of one hook call. findings: [(guard name, its result, crashed)]."""
    raw = env.get(RAW) == "true"
    ti = payload.get("tool_input")
    command = ti.get("command") if payload.get("tool_name") == "Bash" and isinstance(ti, dict) else None
    rec = {"v": VERSION, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock())),
           "session": payload.get("session_id"), "call": payload.get("tool_use_id"),
           "event": payload.get("hook_event_name") or "PreToolUse", "tool": payload.get("tool_name"),
           "run": only}
    if isinstance(command, str):
        rec["rung"], refused = _rung(command)
        if refused:
            rec["refused"] = True
        if raw:
            rec["command"] = {"raw": command}
        else:
            try:
                progs = [] if refused else programs(command)
            except Exception:  # noqa: BLE001
                progs = None
            rec["command"] = {"redacted": True, "programs": progs, "length": len(command)}
    elif raw and ti is not None:
        rec["input"] = ti
    rec["findings"] = [_finding(g, r, crashed, raw) for g, r, crashed in findings]
    rec["verdict"] = verdict
    return rec
