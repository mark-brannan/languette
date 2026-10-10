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

VERSION = 1
ON = "CLAUDE_PLUGIN_OPTION_RECORD_DECISIONS"
RAW = "CLAUDE_PLUGIN_OPTION_RECORD_RAW_COMMANDS"


MASK = "<secret>"
MIN_MASKED = 8      # a shorter secret is not swapped in place; the text is dropped


def mask(text):
    """(text with each secret in it replaced by MASK, how many distinct ones),
    by the detector guard-secrets uses. The text is the command as written, so
    quoting, spacing and heredocs survive: each word a finding names is swapped
    for its redacted form where it stands, or, when the shell unquoted it so it
    does not stand as read, just the secret in it is. Text is None when a
    secret is nowhere in the command as spelled (`"gh""p_..."`, `\\g`), or is
    shorter than MIN_MASKED (swapping "a" would rewrite every "a" in the
    command): it cannot be placed, so a record with a hole beats one with a
    secret or a command that no longer reads as it ran."""
    out, secret, lost = text, set(), False
    for s in secrets.scans(text):
        found = secrets.findings(s, mask_only=True)
        redacted = secrets.redact(s, found, MASK)
        for i in sorted({f.index for f in found}):
            word = secrets.word_text(s, i)
            if any(f.index == i and f.span[1] - f.span[0] < MIN_MASKED for f in found):
                continue
            if word in out:
                out = out.replace(word, redacted[i])
                secret.update(secrets.word_text(s, f.index)[slice(*f.span)] for f in found if f.index == i)
        for f in found:
            value = secrets.word_text(s, f.index)[slice(*f.span)]
            if value in secret:
                continue
            secret.add(value)
            if len(value) < MIN_MASKED:
                lost = True
            elif value in out:
                out = out.replace(value, MASK)
            else:
                lost = True
    return (None if lost else out), len(secret)


def _mask_prose(text):
    """A guard's reason, masked: read as lines of data, not as shell."""
    s = secrets.Text(text)
    return "\n".join(secrets.redact(s, secrets.findings(s, mask_only=True), MASK))


def wanted(env):
    return env.get(ON) == "true"


def _finding(guard, r, crashed, raw):
    """One guard's finding: what it decided, and its words when raw."""
    r = r or {}
    f = {"guard": guard, "decision": r.get("permissionDecision") or ("context" if r.get("additionalContext") else "none")}
    if crashed:
        f["crashed"] = True
    why = r.get("permissionDecisionReason") or r.get("additionalContext")
    if why:
        if raw:
            f["reason"] = why
        else:
            try:
                f["reason"] = _mask_prose(why)
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
            try:
                text, n = mask(command)
            except Exception:  # noqa: BLE001 -- a command that cannot be masked is left out
                text, n = None, None
            rec["command"] = {"text": text, "masked": n, "programs": progs}
    elif raw and ti is not None:
        rec["input"] = ti
    rec["findings"] = [_finding(g, r, crashed, raw) for g, r, crashed in findings]
    rec["verdict"] = verdict
    return rec
