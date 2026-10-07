"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard (the hooks.json wiring runs each
Python guard alone this way). Fails closed: an unreadable payload is a deny,
a Bash command the parser refuses is a deny (guard-unparsable; the other guards
skip it), and a guard that raises is a deny naming the guard. No guard
matched, or none objected, is exit 0 with no output. Standard library only.
"""

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
    from languette.guards import (ask_first, no_skip_hooks, guard_bypass_labels, guard_infra,
                                  guard_recursive_delete, guard_unparsable)
    from languette.verdict import context, deny
except Exception as e:  # noqa: BLE001
    sys.stdout.write(_out("PreToolUse", {"permissionDecision": "deny",
                                         "permissionDecisionReason": f"languette: a guard failed to load ({type(e).__name__}: {e})"}))
    sys.exit(0)

# (hook event, tool name pattern, guards in the order they judge).
GUARDS = (
    ("PreToolUse", re.compile(r"Bash\Z"), (guard_unparsable, guard_recursive_delete, ask_first, no_skip_hooks,
                                           guard_infra, guard_bypass_labels)),
    ("PreToolUse", re.compile(r"mcp__.+"), (guard_bypass_labels,)),
)


def respond(stdin_text, env, only=None):
    """The hook's whole stdout for one payload: "" (no objection) or one
    JSON line. `env` is what the guards read in place of os.environ."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as e:  # noqa: BLE001 -- a gate fails closed on anything
        return _out("PreToolUse", deny(f"languette: unreadable hook payload ({e})"))
    # The shell guards never read the event; a payload without one is judged
    # as PreToolUse, the only event they are wired to.
    event = payload.get("hook_event_name") or "PreToolUse"
    tool = payload.get("tool_name")
    guards = [g for ev, rx, gs in GUARDS if ev == event and isinstance(tool, str) and rx.match(tool)
              for g in gs if only in (None, g.NAME)]
    ti = payload.get("tool_input")
    command = ti.get("command") if tool == "Bash" and isinstance(ti, dict) else None
    if guards and isinstance(command, str) and env.get("CLAUDE_PLUGIN_OPTION_GUARD_UNPARSABLE") != "false":
        # A command that does not parse is guard-unparsable's to deny; the others
        # would only read it again through a weaker parser. With guard-unparsable
        # off, nothing would deny it, so the others read it on the awk rung.
        try:
            unparsed = guard_unparsable.refusal(command)
        except Exception:  # noqa: BLE001 -- guard-unparsable's own run reports the crash
            unparsed = False
        if unparsed:
            guards = [g for g in guards if g is guard_unparsable]
    reasons, notes = [], []
    for g in guards:
        try:
            r = g.check(payload, env)
        except Exception as e:  # noqa: BLE001
            r = deny(f"{g.NAME}: guard crashed ({type(e).__name__}: {e}), cannot inspect the command")
        if not r:
            continue
        if r.get("permissionDecision") == "deny":
            reasons.append(r["permissionDecisionReason"])
        if r.get("additionalContext"):
            notes.append(r["additionalContext"])
    if reasons:
        return _out(event, deny("\n\n".join(reasons)))
    if notes:
        return _out(event, context("\n\n".join(notes)))
    return ""


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
