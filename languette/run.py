"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard (the fixture runner judges a verdict
line by the guard it names). Fails closed: an unreadable payload is a deny,
and a guard that raises is a deny naming the guard. No guard matched, or none
objected, is exit 0 with no output. Standard library only.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from languette.guards import no_rm_tree  # noqa: E402

# (hook event, tool name) -> guards, in the order they judge.
GUARDS = {
    ("PreToolUse", "Bash"): (no_rm_tree,),
}


def _out(event, fields):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, separators=(",", ":")))


def main(argv):
    only = argv[argv.index("--guard") + 1] if "--guard" in argv[:-1] else None
    try:
        payload = json.loads(sys.stdin.buffer.read())
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as e:  # noqa: BLE001 -- a gate fails closed on anything
        _out("PreToolUse", {"permissionDecision": "deny",
                            "permissionDecisionReason": f"languette: unreadable hook payload ({e})"})
        return 0
    # The shell guards never read the event; a payload without one is judged
    # as PreToolUse, the only event they are wired to.
    event = payload.get("hook_event_name") or "PreToolUse"
    guards = [g for g in GUARDS.get((event, payload.get("tool_name")), ()) if only in (None, g.NAME)]
    reasons, context = [], []
    for g in guards:
        try:
            r = g.check(payload)
        except Exception as e:  # noqa: BLE001
            r = {"permissionDecision": "deny",
                 "permissionDecisionReason": f"{g.NAME}: guard crashed ({type(e).__name__}: {e}), cannot inspect the command"}
        if not r:
            continue
        if r.get("permissionDecision") == "deny":
            reasons.append(r["permissionDecisionReason"])
        if r.get("additionalContext"):
            context.append(r["additionalContext"])
    if reasons:
        _out(event, {"permissionDecision": "deny", "permissionDecisionReason": "\n\n".join(reasons)})
    elif context:
        _out(event, {"additionalContext": "\n\n".join(context)})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
