"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard (the hooks.json wiring runs each
Python guard alone this way). Fails closed: an unreadable payload is a deny,
a Bash command the parser refuses is a deny (require-well-formed; the other guards
skip it), and a guard that raises is a deny naming the guard. No guard
matched, or none objected, is exit 0 with no output; a deny outranks an ask.
Standard library only.

The shape: a guard is a pure function of the payload and env. A fact it can't
read from them (a git ref, GitHub's rules for a branch, a file, the clock, the
user's approvals) it asks for: its check is then a generator that yields a
languette.verdict.Need and gets the answer back, and returns its finding. This
runner answers every Need through languette.world, the only module that does
I/O, and throws world's exception into the guard when the fact can't be had.
A write it wants it yields as a languette.verdict.Act: the runner sends None
back, and does every Act through world once the verdict is out.
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
                                  guard_cross_session_send, guard_disks, guard_git_stacked_base,
                                  guard_git_work_loss, guard_github_issues, guard_host_availability,
                                  guard_infra, guard_permissions, guard_pipe_to_shell, guard_private_terms,
                                  guard_recursive_delete, guard_scheduled_jobs, guard_secrets, require_well_formed,
                                  guard_worktrees, prose_budget_commit)
    from languette import record
    from languette.verdict import Act, allow, ask, context, deny
    from languette.world import ACTS, World
except Exception as e:  # noqa: BLE001
    sys.stdout.write(_out("PreToolUse", {"permissionDecision": "deny",
                                         "permissionDecisionReason": f"languette: a guard failed to load ({type(e).__name__}: {e})"}))
    sys.exit(0)

# (hook event, tool name pattern or None for an event with no tool, guards in
# the order they judge). guard-cross-session-send judges SendMessage; on the
# other events it only keeps its per-session state, and never objects.
_SEND_STATE_TOOLS = re.compile(r"(?:WebFetch|WebSearch|Bash|Agent|mcp__.+)\Z")
GUARDS = (
    ("PreToolUse", re.compile(r"Bash\Z"), (require_well_formed, guard_git_work_loss, guard_recursive_delete, ask_first,
                                           guard_bypass_hooks, guard_infra, guard_bypass_labels,
                                           guard_bypass_ruleset, guard_permissions, guard_pipe_to_shell,
                                           guard_disks, guard_host_availability, guard_scheduled_jobs,
                                           guard_git_stacked_base, guard_secrets, prose_budget_commit)),
    ("PreToolUse", re.compile(r"mcp__.+"), (guard_bypass_labels,)),
    ("PreToolUse", guard_github_issues.TOOLS, (guard_github_issues,)),
    ("PreToolUse", guard_private_terms.TOOLS, (guard_private_terms,)),
    ("PreToolUse", re.compile(r"(?:Bash|Edit|Write|MultiEdit|NotebookEdit|EnterWorktree)\Z"), (guard_worktrees,)),
    ("PreToolUse", re.compile(r"SendMessage\Z"), (guard_cross_session_send,)),
    ("PostToolUse", _SEND_STATE_TOOLS, (guard_cross_session_send,)),
    ("PostToolUseFailure", _SEND_STATE_TOOLS, (guard_cross_session_send,)),
    ("SubagentStart", None, (guard_cross_session_send,)),
    ("SessionStart", None, (guard_cross_session_send,)),
    # guard-github-issues' door: a human turn opens it, a write that ran spends it.
    ("UserPromptSubmit", None, (guard_github_issues,)),
    ("PostToolUse", guard_github_issues.TOOLS, (guard_github_issues,)),
    ("PostToolUseFailure", guard_github_issues.TOOLS, (guard_github_issues,)),
)


def _on(g, env):
    opt = getattr(g, "OPT_IN", None)
    return not opt or env.get(opt) == "true"


def _drive(r, world, acts):
    """A guard's finding: `r` itself, or what generator `r` returns once every Need it
    yields is answered. Each Act it yields goes on `acts`."""
    if not inspect.isgenerator(r):
        return r
    answer, err = None, None
    while True:
        try:
            need = r.throw(err) if err else r.send(answer)
        except StopIteration as stop:
            return stop.value
        if isinstance(need, Act):
            if need.kind in ACTS:
                acts.append(need)
                answer, err = None, None
            else:
                answer, err = None, ValueError(f"no such act: {need!r}")
            continue
        try:
            answer, err = world.answer(need), None
        except Exception as e:  # noqa: BLE001 -- the guard decides what a missing fact means
            answer, err = None, e


def respond(stdin_text, env, only=None):
    """The hook's whole stdout for one payload: "" (no objection) or one
    JSON line. `env` is what the guards read in place of os.environ. The
    guards' Acts are done after the verdict, and with record_decisions on, the
    call is recorded (record.py)."""
    out, judged = _respond(stdin_text, env, only)
    world, payload, findings, acts = judged
    for a in acts:
        world.act(a)
    if record.wanted(env):
        try:
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
    """(stdout, (world, payload, [(guard, result, crashed)], [Act]))."""
    try:
        payload = json.loads(stdin_text)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception as e:  # noqa: BLE001 -- a gate fails closed on anything
        return _out("PreToolUse", deny(f"languette: unreadable hook payload ({e})")), (World(env, {}), {}, [], [])
    # The shell guards never read the event; a payload without one is judged
    # as PreToolUse, the only event they are wired to.
    event = payload.get("hook_event_name") or "PreToolUse"
    tool = payload.get("tool_name")
    # A hook entry that names no guard here, say one renamed since it was
    # copied, would otherwise judge nothing and pass every command.
    if only is not None and only not in {g.NAME for _, _, gs in GUARDS for g in gs}:
        return _out("PreToolUse", deny(f"languette: no guard is named {only}, so this hook checks nothing. "
                                       "This is a gate and fails closed: reinstall the plugin, or copy the "
                                       "entry again from hooks/hooks.json")), (World(env, payload), payload, [], [])
    # An opt-in guard (OPT_IN names its option) runs alone by name, or with the
    # rest only when its option is exactly "true", as hooks.json runs it. An
    # entry with no tool pattern matches an event with no tool.
    guards = [g for ev, rx, gs in GUARDS if ev == event and (rx is None or isinstance(tool, str) and rx.match(tool))
              for g in gs if only == g.NAME or (only is None and _on(g, env))]
    ti = payload.get("tool_input")
    command = ti.get("command") if tool == "Bash" and isinstance(ti, dict) else None
    judged_once = None   # require-well-formed's verdict, when this reading got one
    if (guards and event == "PreToolUse" and isinstance(command, str)
            and env.get("CLAUDE_PLUGIN_OPTION_REQUIRE_WELL_FORMED") != "false"):
        # A command that does not parse is require-well-formed's to deny; the others
        # would only read it again through a weaker parser. With require-well-formed
        # off, nothing would deny it, so the others read it on the awk rung.
        # require-well-formed's verdict is this one reading, never a second parse:
        # a parser that timed out here may finish there, and pass what it denied.
        try:
            judged_once = (require_well_formed.judge(command),)
        except Exception:  # noqa: BLE001 -- require-well-formed's own run reports the crash
            pass
        if judged_once and judged_once[0]:
            guards = [g for g in guards if g is require_well_formed]
    world = World(env, payload)
    reasons, asks, notes, rewrites, findings, acts = [], [], [], [], [], []
    for g in guards:
        crashed = False
        try:
            r = judged_once[0] if judged_once and g is require_well_formed else _drive(g.check(payload, env), world, acts)
        except Exception as e:  # noqa: BLE001
            r, crashed = deny(f"{g.NAME}: guard crashed ({type(e).__name__}: {e}), cannot inspect the command"), True
        findings.append((g.NAME, r, crashed))
        if not r:
            continue
        if r.get("permissionDecision") == "deny":
            reasons.append(r["permissionDecisionReason"])
        if r.get("permissionDecision") == "ask":
            asks.append(r["permissionDecisionReason"])
        if r.get("permissionDecision") == "allow" and "updatedInput" in r:
            rewrites.append(r["updatedInput"])
        if r.get("additionalContext"):
            notes.append(r["additionalContext"])
    judged = (world, payload, findings, acts)
    if event != "PreToolUse":                  # state-keeping events: nothing to decide
        return "", judged
    if reasons:
        return _out(event, deny("\n\n".join(reasons))), judged
    if asks:
        return _out(event, ask("\n\n".join(asks))), judged
    if rewrites:                               # the first rewrite wins; two cannot both apply
        return _out(event, {**allow(rewrites[0]), **(context("\n\n".join(notes)) if notes else {})}), judged
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
