"""Hook entry point: read the payload once from stdin, run every guard
registered for its hook event and tool, print one decision.

    python3 -I languette/run.py [--guard NAME]

--guard restricts the run to one guard whatever its option says (hooks/hooks.json
names none: one run judges every guard wired for the event and tool whose option
allows it). Fails closed: an unreadable payload is a deny,
a Bash command the parser refuses is a deny (require-well-formed; the other guards
skip it), and a guard that raises is a deny naming the guard. No guard
matched, or none objected, is exit 0 with no output; a deny outranks an ask.
Standard library only.

The shape: the payload is parsed once into one read-only
languette.document.Document, and every guard's check(doc) reads that one
parse. A fact it can't read from the document (a git ref, GitHub's rules for
a branch, a file, the clock, the user's approvals) it asks for: its check is
then a generator that yields a languette.verdict.Need and gets the answer
back, and returns its finding. This runner answers every Need through
languette.world, the only module that does I/O, and throws world's exception
into the guard when the fact can't be had. A write it wants it yields as a
languette.verdict.Act: the runner sends None back, and does every Act through
world once the verdict is out. A guard that needs the user's approval spends
nothing: it reads the approval and returns an ask finding
(languette.verdict.spend), and the runner spends every guard's ask once, after
the verdict, only when the verdict lets the call through (_spend). Guards run
one at a time, in one loop.
Every guard sees the payload as sent: the runner never fills in a cwd, and
denies a PreToolUse payload without an absolute one before any guard runs.
"""

import inspect
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.version_info < (3, 11):                 # the guards read re's parser; name the floor before they fail to import
    sys.stdout.write('{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",'
                     '"permissionDecisionReason":"languette needs python3 3.11 or newer, and this is older. '
                     'This is a gate and fails closed: install a newer python3."}}\n')
    sys.exit(0)


def _out(event, fields):
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}, separators=(",", ":")) + "\n"


# A guard that cannot even be imported is a deny too, not a traceback and a
# non-zero exit that only the hooks.json wrapper would turn into one.
try:
    import importlib.util
    from languette.messages import say
    from languette import comment_posts, engine, issue_writes, opened_prs, posts, record, secrets
    from languette.document import Document
    from languette.verdict import LOST, SPEND, Act, deny, verdict
    from languette.world import ACTS, World

    def _load(name):
        """The guard `name`: a rule set in languette/rules/ (languette/engine.py), else a guard
        module in languette/guards/."""
        mod = name.replace("-", "_")
        if importlib.util.find_spec("languette.rules." + mod) is not None:
            g = engine.Guard(importlib.import_module("languette.rules." + mod))
        else:
            g = importlib.import_module("languette.guards." + mod)
        if g.NAME != name:
            raise ImportError(f"{name} loads a guard named {g.NAME}")
        return g

    # (hook event, tool name pattern or None for an event with no tool, guards in
    # the order they judge). guard-cross-session-send judges SendMessage; on the
    # other events it only keeps its per-session state, and never objects.
    STATE_EVENTS = engine.STATE_EVENTS
    _SEND_STATE_TOOLS = re.compile(r"(?:WebFetch|WebSearch|Bash|Agent|mcp__.+)\Z")
    _WIRING = (
        ("PreToolUse", re.compile(r"Bash\Z"), ("require-well-formed", "guard-git-work-loss", "guard-recursive-delete",
                                               "ask-first", "deny-always", "guard-bypass-hooks", "guard-infra",
                                               "guard-bypass-labels", "guard-bypass-ruleset", "guard-permissions",
                                               "guard-pipe-to-shell", "guard-disks", "guard-host-availability",
                                               "guard-protected-services", "guard-scheduled-jobs", "guard-sudo",
                                               "guard-git-stacked-base", "guard-review-threads", "guard-secrets",
                                               "prose-budget-commit")),
        ("PreToolUse", re.compile(r"mcp__.+"), ("guard-bypass-labels",)),
        ("PreToolUse", issue_writes.TOOLS, ("guard-github-issues",)),
        ("PreToolUse", posts.TOOLS, ("guard-private-terms",)),
        ("PreToolUse", opened_prs.TOOLS, ("guard-duplicate-prs",)),
        ("PreToolUse", comment_posts.TOOLS, ("guard-signed-comments",)),
        ("PreToolUse", re.compile(r"(?:Bash|Edit|Write|MultiEdit|NotebookEdit|EnterWorktree)\Z"), ("guard-worktrees",)),
        ("PreToolUse", re.compile(r"SendMessage\Z"), ("guard-cross-session-send",)),
        ("PostToolUse", _SEND_STATE_TOOLS, ("guard-cross-session-send",)),
        ("PostToolUseFailure", _SEND_STATE_TOOLS, ("guard-cross-session-send",)),
        ("SubagentStart", None, ("guard-cross-session-send",)),
        ("SessionStart", None, ("guard-cross-session-send", "guard-private-terms")),
        # guard-github-issues' door: a human turn opens it, a write that ran spends it.
        ("UserPromptSubmit", None, ("guard-github-issues",)),
        ("PostToolUse", issue_writes.TOOLS, ("guard-github-issues",)),
        ("PostToolUseFailure", issue_writes.TOOLS, ("guard-github-issues",)),
    )
    # Every guard by name, loaded once: the wiring above is the one list of them.
    GUARD = {n: _load(n) for n in dict.fromkeys(n for _, _, ns in _WIRING for n in ns)}
    GUARDS = tuple((ev, rx, tuple(GUARD[n] for n in ns)) for ev, rx, ns in _WIRING)
    require_well_formed, guard_cross_session_send = GUARD["require-well-formed"], GUARD["guard-cross-session-send"]
except Exception as e:  # noqa: BLE001
    try:
        _why = say("guard_load_failed", kind=type(e).__name__, err=e)
    except NameError:                          # messages itself would not import: the floor sentence, no `say`
        _why = ("languette could not load (%s). This is a gate and fails closed: reinstall languette." % type(e).__name__)
    sys.stdout.write(_out("PreToolUse", {"permissionDecision": "deny", "permissionDecisionReason": _why}))
    sys.exit(0)


def option(g):
    """The environment variable holding guard g's on/off option."""
    return getattr(g, "OPT_IN", None) or "CLAUDE_PLUGIN_OPTION_" + g.NAME.upper().replace("-", "_")


def _on(g, env):
    """Whether g runs when no guard is named: an opt-in guard (OPT_IN) only when its
    option is exactly "true", any other guard unless its option is exactly "false"."""
    if hasattr(g, "OPT_IN"):
        return env.get(g.OPT_IN) == "true"
    return env.get(option(g)) != "false"


def gates():
    """Option name -> its gate, `=` (on unless false) or `!=` (on only if true), for every guard."""
    return {option(g)[len("CLAUDE_PLUGIN_OPTION_"):].lower(): "!=" if hasattr(g, "OPT_IN") else "="
            for _, _, gs in GUARDS for g in gs}


def wired(event, tool):
    """Every guard registered for `event` and `tool`, in the order they judge. An
    entry with no tool pattern matches an event with no tool."""
    return [g for ev, rx, gs in GUARDS if ev == event and (rx is None or isinstance(tool, str) and rx.match(tool))
            for g in gs]


def drive(r, world, acts):
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


def _finding(g, doc, world, acts):
    """(g's finding on `doc`, whether it crashed)."""
    try:
        return drive(g.check(doc), world, acts), False
    except Exception as e:  # noqa: BLE001
        return deny(say("guard_crashed", guard=g.NAME, kind=type(e).__name__, err=e)), True


def respond(stdin_text, env, only=None):
    """The hook's whole stdout for one payload: "" (no objection) or one
    JSON line. `env` is what the guards read in place of os.environ. The
    guards' Acts are done after the verdict, and with record_decisions on, the
    call is recorded (record.py)."""
    return _answer(_read(stdin_text), env, only)[0]


def _read(stdin_text):
    """The payload object, or the exception that kept it from reading."""
    try:
        payload = json.loads(stdin_text)
    except Exception as e:  # noqa: BLE001 -- a gate fails closed on anything, RecursionError too
        return e
    return payload if isinstance(payload, dict) else ValueError("payload is not an object")


def _answer(payload, env, only):
    """(respond's stdout, whether guard-cross-session-send crashed or objected) for
    `payload`, _read's result. Its state handlers never object, so a finding is a failure."""
    out, judged = _respond(payload, env, only)
    world, payload, findings, acts, doc = judged
    for a in acts:
        world.act(a)
    if record.wanted(env):
        try:
            world.keep(record.build(doc, only, findings, _verdict(out), extra=_project_rules(world, payload, env)))
        except Exception:  # noqa: BLE001 -- a record never changes the verdict
            pass
    return out, any(crashed or r is not None for name, r, crashed in findings if name == guard_cross_session_send.NAME)


def _project_rules(world, payload, env):
    """The project's secret rules for the record's mask, gathered through the
    world as guard-secrets gathers them; None when they cannot be read, and the
    record then drops what it cannot mask."""
    if env.get(record.RAW) == "true":
        return ()
    try:
        return drive(secrets.project_rules(payload, env), world, [])
    except Exception:  # noqa: BLE001 -- a malformed list costs the record its text, never the verdict
        return None


def _verdict(out):
    if not out:
        return "silent"
    hso = json.loads(out)["hookSpecificOutput"]
    return hso.get("permissionDecision") or "context"


def _respond(payload, env, only):
    """(stdout, (world, payload, [(guard, result, crashed)], [Act], Document)) for
    _read's result."""
    if isinstance(payload, Exception):
        return _out("PreToolUse", deny(say("payload_unreadable", err=payload))), (World(env, {}), {}, [], [], Document({}, env))
    # The shell guards never read the event; a payload without one is judged
    # as PreToolUse, the only event they are wired to.
    event = payload.get("hook_event_name") or "PreToolUse"
    # Every guard resolves paths from the payload's cwd, never the hook
    # process's own directory, which no one promises is the session's. The
    # state-keeping events read no cwd, and skipping them would fail open.
    cwd = payload.get("cwd")
    if event == "PreToolUse" and (not isinstance(cwd, str) or not cwd.startswith("/")):
        return _out(event, deny(say("no_cwd"))), (World(env, payload), payload, [], [], Document(payload, env))
    tool = payload.get("tool_name")
    # A hook entry that names no guard here, say one renamed since it was
    # copied, would otherwise judge nothing and pass every command.
    if only is not None and only not in {g.NAME for _, _, gs in GUARDS for g in gs}:
        return _out("PreToolUse", deny(say("unknown_guard", name=only))), (World(env, payload), payload, [], [], Document(payload, env))
    # A guard runs alone by name whatever its option says, or with the rest when
    # its option allows it (_on): the one hooks.json command names no guard.
    guards = [g for g in wired(event, tool) if only == g.NAME or (only is None and _on(g, env))]
    doc = Document(payload, env)
    if (guards and event == "PreToolUse" and doc.command is not None
            and _on(require_well_formed, env)):
        # A command that does not parse is require-well-formed's to deny; the others
        # would only read it again through a weaker parser. With require-well-formed
        # off, nothing would deny it, so the others read it on the awk rung. The
        # document keeps this one reading: a parser that timed out here never
        # gets a second run that might pass what it denied.
        try:
            refused = doc.refusal
        except Exception:  # noqa: BLE001 -- require-well-formed's own check reports the crash
            refused = None
        if refused:
            guards = [g for g in guards if g is require_well_formed]
    world = World(env, payload)
    world.wants_of = _past_wants(world, env)
    world.door_tools = issue_writes.TOOLS
    findings, acts = [], []
    for g in guards:
        r, crashed = _finding(g, doc, world, acts)
        findings.append((g.NAME, r, crashed))
    judged = (world, payload, findings, acts, doc)
    fields = _spend(world, event, findings, verdict(event, findings, doc.mode, lambda: doc.chained))
    return (_out(event, fields) if fields else ""), judged


# What a past call judged again may ask of the world: read-only facts of this
# machine. Anything else (a program, a forge, languette's own state) is refused,
# so a replay starts nothing and reads nothing back.
_REPLAY_FACTS = frozenset(("read", "path", "physical", "which", "clock", "hostname"))


class _Replay:
    """The world a past call is judged again in: today's read-only facts, the user's
    yes taken as given, and guard-github-issues' door as the transcript left it."""

    def __init__(self, world, door):
        self.world, self.door = world, door

    def answer(self, need):
        if need.kind == "approvals":
            return {label: [None] * n for label, n in need.args[0].items()}
        if need.kind == "door":
            return self.door or ""
        if need.kind not in _REPLAY_FACTS:
            raise LookupError(f"not asked again for a past call: {need!r}")
        return self.world.answer(need)


def _past_wants(world, env):
    """World's wants_of, for the approvals replay (languette.world.World._replay):
    given a past call's payload and whether the human turn's door stood open,
    ({label: runs} the runner would have spent for it, whether it took the door).
    Every guard on for the call judges it again, as _spend would gather them; its
    Acts are dropped. It assumes the default wiring: a run under `--guard NAME`
    spent only that guard's labels, which this replay does not know."""
    def wants_of(payload, door):
        doc, replay, wants, took = Document(payload, env), _Replay(world, door), {}, False
        for g in wired("PreToolUse", payload.get("tool_name")):
            if not _on(g, env):
                continue
            r, _ = _finding(g, doc, replay, [])
            for kind, *args in (r.get(SPEND) or ()) if isinstance(r, dict) else ():
                if kind == "approvals":
                    for label, n in args[0].items():
                        wants[label] = max(wants.get(label, 0), n)
                took = took or kind == "door"
        return wants, took
    return wants_of


def _spend(world, event, findings, fields):
    """`fields`, the verdict, once what the ask findings want is spent
    (languette.verdict.spend): once, after the verdict, and only when it lets the
    call through, so a deny spends nothing. Every guard's approval labels go in
    one claim, a label asked for twice spending once, so one click is one run
    whichever guards asked. A spend lost to a parallel call, or one that cannot
    be recorded, makes the call a deny."""
    if event != "PreToolUse" or (fields or {}).get("permissionDecision") == "deny":
        return fields
    wants, names, todo = {}, {}, []
    for name, r, _ in findings:
        for kind, *args in (r.get(SPEND) or ()) if isinstance(r, dict) else ():
            if kind != "approvals":
                todo.append((name, kind, args, r.get(LOST)))
                continue
            for label, n in args[0].items():
                wants[label] = max(wants.get(label, 0), n)
            names[name] = None
    if wants:
        guards = ", ".join(names)
        todo.insert(0, (guards, "approvals", [wants], say("approval_lost", guards=guards)))
    for name, kind, args, lost in todo:
        try:
            if world.spend(kind, *args):
                continue
            why = lost or say("spend_failed", guards=name, err="no deny reason given")
        except Exception as e:  # noqa: BLE001 -- a spend that cannot be made fails closed
            why = say("spend_failed", guards=name, err=e)
        return deny(why)
    return fields


def _state_failed(payload, env):
    """A state-keeping hook (PostToolUse and the rest) that crashed or objected leaves
    guard-cross-session-send's file saying the session has read something unknown, so
    its door stays shut rather than open on a stale record. With that guard's option
    off, nothing reads the file, so none is written (hooks.json's sh fallback agrees)."""
    if not _on(guard_cross_session_send, env):
        return
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if isinstance(sid, str) and sid:
        World(env, payload).act(Act("send-fail", sid))


def main(argv):
    only = argv[argv.index("--guard") + 1] if "--guard" in argv[:-1] else None
    try:
        stdin_text = sys.stdin.buffer.read()
    except OSError:
        stdin_text = b""                       # judged as an unreadable payload
    payload = _read(stdin_text)
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    if event in STATE_EVENTS:
        # These events carry no decision: whatever the guards say is kept off stdout,
        # and guard-cross-session-send crashing or objecting is a failure though the verdict is silence.
        try:
            out, failed = _answer(payload, os.environ, only)
        except Exception:  # noqa: BLE001
            out, failed = "", True
        if out or failed:
            _state_failed(payload, os.environ)
        return 0
    sys.stdout.write(_answer(payload, os.environ, only)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
