"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard (the hooks.json wiring runs each
Python guard alone this way). Fails closed: an unreadable payload is a deny,
a Bash command the parser refuses is a deny (guard-unparsable; the other guards
skip it), and a guard that raises is a deny naming the guard. No guard
matched, or none objected, is exit 0 with no output; a deny outranks an ask.
Standard library only.

The shape: a guard is a pure function of the payload and env. A fact it can't
read from them (a git ref, GitHub's rules for a branch, a file, the clock, the
user's approvals) it asks for: its check is then a generator that yields a
languette.verdict.Need and gets the answer back, and returns its finding. This
runner answers every Need through languette.world, the only module that does
I/O, and throws world's exception into the guard when the fact can't be had.
A guard whose check returns a finding directly needs no change.
"""

import inspect
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _out(event, fields):
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, separators=(",", ":")) + "\n"


# A guard that cannot even be imported is a deny too, not a traceback and a
# non-zero exit that only the hooks.json wrapper would turn into one.
try:
    from languette.guards import (ask_first, guard_bypass_hooks, guard_bypass_labels, guard_bypass_ruleset,
                                  guard_cross_session_send, guard_disk, guard_host_availability, guard_infra,
                                  guard_permissions, guard_pipe_to_shell, guard_recursive_delete, guard_scheduled_jobs,
                                  guard_unparsable)
    from languette import record
    from languette.verdict import ask, context, deny
    from languette.world import World
except Exception as e:  # noqa: BLE001
    sys.stdout.write(_out("PreToolUse", {"permissionDecision": "deny",
                                         "permissionDecisionReason": f"languette: a guard failed to load ({type(e).__name__}: {e})"}))
    sys.exit(0)

# (hook event, tool name pattern or None for an event with no tool, guards in
# the order they judge). guard-cross-session-send judges SendMessage; on the
# other events it only keeps its per-session state, and never objects.
_SEND_STATE_TOOLS = re.compile(r"(?:WebFetch|WebSearch|Bash|Agent|mcp__.+)\Z")
GUARDS = (
    ("PreToolUse", re.compile(r"Bash\Z"), (guard_unparsable, guard_recursive_delete, ask_first, guard_bypass_hooks,
                                           guard_infra, guard_bypass_labels, guard_bypass_ruleset,
                                           guard_permissions, guard_pipe_to_shell, guard_disk,
                                           guard_host_availability, guard_scheduled_jobs)),
    ("PreToolUse", re.compile(r"mcp__.+"), (guard_bypass_labels,)),
    ("PreToolUse", re.compile(r"SendMessage\Z"), (guard_cross_session_send,)),
    ("PostToolUse", _SEND_STATE_TOOLS, (guard_cross_session_send,)),
    ("PostToolUseFailure", _SEND_STATE_TOOLS, (guard_cross_session_send,)),
    ("SubagentStart", None, (guard_cross_session_send,)),
    ("SessionStart", None, (guard_cross_session_send,)),
)


def _drive(r, world):
    """A guard's finding: `r` itself, or what generator `r` returns once every Need it
    yields is answered."""
    if not inspect.isgenerator(r):
        return r
    answer, err = None, None
    while True:
        try:
            need = r.throw(err) if err else r.send(answer)
        except StopIteration as stop:
            return stop.value
        try:
            answer, err = world.answer(need), None
        except Exception as e:  # noqa: BLE001 -- the guard decides what a missing fact means
            answer, err = None, e


def respond(stdin_text, env, only=None):
    """The hook's whole stdout for one payload: "" (no objection) or one
    JSON line. `env` is what the guards read in place of os.environ. With
    record_decisions on, the call is recorded after the verdict (record.py)."""
    out, judged = _respond(stdin_text, env, only)
    if judged and record.wanted(env):
        try:
            world, payload, findings = judged
            world.keep(record.build(payload, env, only, findings, _verdict(out)))
        except Exception:  # noqa: BLE001 -- a record never changes the verdict
            pass
    return out


def _verdict(out):
    if not out:
        return "silent"
    hso = json.loads(out)["hookSpecificOutput"]
    return hso.get("permissionDecision") or "context"


def _respond(stdin_text, env, only):
    """(stdout, (world, payload, [(guard, result, crashed)]) or None)."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as e:  # noqa: BLE001 -- a gate fails closed on anything
        return _out("PreToolUse", deny(f"languette: unreadable hook payload ({e})")), (World(env, {}), {}, [])
    # The shell guards never read the event; a payload without one is judged
    # as PreToolUse, the only event they are wired to.
    event = payload.get("hook_event_name") or "PreToolUse"
    tool = payload.get("tool_name")
    guards = [g for ev, rx, gs in GUARDS if ev == event and (rx is None or isinstance(tool, str) and rx.match(tool))
              for g in gs if only in (None, g.NAME)]
    ti = payload.get("tool_input")
    command = ti.get("command") if tool == "Bash" and isinstance(ti, dict) else None
    judged_once = None   # guard-unparsable's verdict, when this reading got one
    if (guards and event == "PreToolUse" and isinstance(command, str)
            and env.get("CLAUDE_PLUGIN_OPTION_GUARD_UNPARSABLE") != "false"):
        # A command that does not parse is guard-unparsable's to deny; the others
        # would only read it again through a weaker parser. With guard-unparsable
        # off, nothing would deny it, so the others read it on the awk rung.
        # guard-unparsable's verdict is this one reading, never a second parse:
        # a parser that timed out here may finish there, and pass what it denied.
        try:
            judged_once = (guard_unparsable.judge(command),)
        except Exception:  # noqa: BLE001 -- guard-unparsable's own run reports the crash
            pass
        if judged_once and judged_once[0]:
            guards = [g for g in guards if g is guard_unparsable]
    world = World(env, payload)
    reasons, asks, notes, findings = [], [], [], []
    for g in guards:
        crashed = False
        try:
            r = judged_once[0] if judged_once and g is guard_unparsable else _drive(g.check(payload, env), world)
        except Exception as e:  # noqa: BLE001
            r, crashed = deny(f"{g.NAME}: guard crashed ({type(e).__name__}: {e}), cannot inspect the command"), True
        findings.append((g.NAME, r, crashed))
        if not r:
            continue
        if r.get("permissionDecision") == "deny":
            reasons.append(r["permissionDecisionReason"])
        if r.get("permissionDecision") == "ask":
            asks.append(r["permissionDecisionReason"])
        if r.get("additionalContext"):
            notes.append(r["additionalContext"])
    judged = (world, payload, findings)
    if reasons:
        return _out(event, deny("\n\n".join(reasons))), judged
    if asks:
        return _out(event, ask("\n\n".join(asks))), judged
    if notes:
        return _out(event, context("\n\n".join(notes))), judged
    return "", judged


def main(argv):
    only = argv[argv.index("--guard") + 1] if "--guard" in argv[:-1] else None
    try:
        stdin_text = sys.stdin.buffer.read()
    except OSError:
        stdin_text = b""                       # judged as an unreadable payload
    sys.stdout.write(respond(stdin_text, os.environ, only))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
