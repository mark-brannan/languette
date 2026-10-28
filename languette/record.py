"""The decision record (#82): one JSON line per hook call, built after the
verdict, never read by it. Pure: World.keep writes it.

Off unless record_decisions is on. The command and each guard's reason are
kept whole except for what secrets.findings names as a secret (a known token
shape, a value a credential's name, option or URL gives away, or, in its
mask-only tier, a mysql -p password or a long random-looking run), which mask()
replaces. When a secret cannot be masked cleanly the text is null.
record_raw_commands masks nothing. `v`
names the format, so a reader can refuse one it does not know.

    {"v": 1, "t": "2026-10-07T23:09:07Z", "session": "a78b...", "call": "toolu_...",
     "event": "PreToolUse", "tool": "Bash", "run": "guard-disks", "rung": "shfmt",
     "command": {"text": "GH_TOKEN=<secret> git push", "masked": 1, "programs": ["git"]},
     "findings": [{"guard": "guard-disks", "decision": "none"}], "verdict": "silent"}

Standard library only.
"""

import os
import time

from languette import scan, secrets
from languette.secrets import MASK, MIN_MASKED, mask  # noqa: F401 -- the record's masking lives with the detector

VERSION = 1
ON = "CLAUDE_PLUGIN_OPTION_RECORD_DECISIONS"
RAW = "CLAUDE_PLUGIN_OPTION_RECORD_RAW_COMMANDS"


def _mask_prose(text, extra=()):
    """A guard's reason, masked: read as lines of data, not as shell."""
    s = secrets.Text(text)
    return "\n".join(secrets.redact(s, secrets.findings(s, extra, mask_only=True), MASK))


def wanted(env):
    return env.get(ON) == "true"


def _finding(guard, r, crashed, raw, extra=()):
    """One guard's finding: what it decided, and its words when raw."""
    r = r or {}
    f = {"guard": guard, "decision": r.get("permissionDecision") or ("context" if r.get("additionalContext") else "none")}
    if crashed:
        f["crashed"] = True
    why = r.get("permissionDecisionReason") or r.get("additionalContext")
    if why:
        if raw:
            f["reason"] = why
        elif extra is not None:
            try:
                f["reason"] = _mask_prose(why, extra)
            except Exception:  # noqa: BLE001 -- a reason that cannot be masked is left out, not the call
                pass
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


def build(payload, env, only, findings, verdict, doc, clock=time.time, extra=()):
    """The record of one hook call. findings: [(guard name, its result, crashed)].
    doc: the run's Document, whose one parse gives the rung.
    extra: the project's secret rules, gathered by the caller (run.py); None
    when they could not be, and then no command text or reason is written."""
    raw = env.get(RAW) == "true"
    ti = payload.get("tool_input")
    command = ti.get("command") if payload.get("tool_name") == "Bash" and isinstance(ti, dict) else None
    rec = {"v": VERSION, "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock())),
           "session": payload.get("session_id"), "call": payload.get("tool_use_id"),
           "event": payload.get("hook_event_name") or "PreToolUse", "tool": payload.get("tool_name"),
           "run": only}
    if isinstance(command, str):
        try:
            rec["rung"], refusal = doc.reading()
        except Exception:  # noqa: BLE001 -- a record never fails the call
            rec["rung"], refusal = None, None
        refused = refusal is not None
        if refused:
            rec["refused"] = True
        if raw:
            rec["command"] = {"raw": command}
        else:
            try:
                progs = [] if refused else programs(command)
            except Exception:  # noqa: BLE001
                progs = None
            try:
                text, n = (None, None) if extra is None else mask(command, extra)
            except Exception:  # noqa: BLE001 -- a command that cannot be masked is left out
                text, n = None, None
            rec["command"] = {"text": text, "masked": n, "programs": progs}
    elif raw and ti is not None:
        rec["input"] = ti
    rec["findings"] = [_finding(g, r, crashed, raw, extra) for g, r, crashed in findings]
    rec["verdict"] = verdict
    return rec
