"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard (the hooks.json wiring runs ask-first
alone this way). Fails closed: an unreadable payload is a deny,
and a guard that raises is a deny naming the guard. No guard matched, or none
objected, is exit 0 with no output. Standard library only.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _out(event, fields):
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, separators=(",", ":")) + "\n"


# A guard that cannot even be imported is a deny too, not a traceback and a
# non-zero exit that only the hooks.json wrapper would turn into one.
try:
    from languette.guards import ask_first, no_rm_tree
    from languette.verdict import context, deny
except Exception as e:  # noqa: BLE001
    sys.stdout.write(_out("PreToolUse", {"permissionDecision": "deny",
                                         "permissionDecisionReason": f"languette: a guard failed to load ({type(e).__name__}: {e})"}))
    sys.exit(0)

# (hook event, tool name) -> guards, in the order they judge.
GUARDS = {
    ("PreToolUse", "Bash"): (no_rm_tree, ask_first),
}


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
    guards = [g for g in GUARDS.get((event, payload.get("tool_name")), ()) if only in (None, g.NAME)]
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
