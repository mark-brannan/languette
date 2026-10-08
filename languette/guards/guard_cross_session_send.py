"""guard-cross-session-send: features/guard-cross-session-send.feature is the spec.

A session that has just read untrusted content (a web page, an issue or PR
body) must not relay instruction-shaped text into another of the user's
sessions unexamined. No hook fires where a message is received, so the guard
sits on the sender: PreToolUse on SendMessage. The same tool talks to this
session's own subagents, which is ordinary and passes.

    target is one of this session's subagents       -> no objection
    bypassPermissions, untrusted read this turn      -> deny
    bypassPermissions, door provably closed          -> no objection
    any other mode                                   -> ask, showing target and first line

Per-session state, kept by World under $TMPDIR and keyed by session_id, is fed
by the same guard on other events: SubagentStart records the subagent's id,
PostToolUse (and PostToolUseFailure) on WebFetch, WebSearch, a Bash `gh` read
of an issue or PR body, or an MCP issue/PR/file read opens the door, and
UserPromptSubmit closes it. No state is "no subagents known, door not
provably closed": an ask where a prompt can fire, a deny where it cannot.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import Need, ask, deny

NAME = "guard-cross-session-send"

FIRST_LINE = 80
_GH = re.compile(r"(?:^|/)gh\Z")
_API_PATH = re.compile(r"(?:https?://[^/]+/)?/*repos/[^/]+/[^/]+/(?:issues|pulls)(?:[/?]|\Z)")
# gh api options that take the next word as their value.
_API_VALUE = frozenset("-X --method -H --header -q --jq -t --template -p --preview --hostname --cache "
                       "-f -F --field --raw-field --input".split())
_MCP_READS = re.compile(r"mcp__.+__(?:issue_read|pull_request_read|get_file_contents|search_issues|search_code)\Z")
# Modes where an ask cannot be shown, so it would pass the call unseen.
_NO_PROMPT = frozenset({"bypassPermissions"})

_WAY_OUT = ("Ask the user to send it from an interactive session, or, once the user has confirmed, "
            "summarize it in this session's own words.")


def _skip_flags(words, i, value_opts=frozenset({"-R", "--repo"})):
    """Index of the first word at or after i that is not an option (nor an
    option's value), or len(words)."""
    while i < len(words):
        x = words[i]
        if x in value_opts:
            i += 2
            continue
        if x.startswith("-") and len(x) > 1:
            i += 1
            continue
        return i
    return i


def _gh_read(words):
    """What `gh <words>` reads that carries an issue or PR body, or None."""
    i = _skip_flags(words, 0)
    if i >= len(words):
        return None
    sub = words[i]
    if sub in ("issue", "pr"):
        j = _skip_flags(words, i + 1)
        return f"`gh {sub} view`" if j < len(words) and words[j] == "view" else None
    if sub == "api":
        j = _skip_flags(words, i + 1, _API_VALUE)
        if j < len(words) and _API_PATH.match(words[j]):
            return f"`gh api {words[j]}`"
    return None


def bash_read(command):
    """The `gh` read in a Bash command that fetched issue, PR or comment bodies, or None."""
    for text, nested in sw.texts_of(sw.strip_heredocs(command.rstrip("\n") + "\n")):
        s = sw.Scan(text)
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, _GH, nested) if a <= b else None
            if g is None:
                continue
            what = _gh_read([s.q[i] if s.k[i] == "q" else s.w[i] for i in range(g + 1, b + 1)])
            if what:
                return what
    return None


def untrusted_read(payload):
    """The tool that read untrusted content, as the deny names it, or None."""
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return None
    if tool in ("WebFetch", "WebSearch") or _MCP_READS.match(tool):
        return tool
    if tool != "Bash":
        return None
    ti = payload.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        return None
    try:
        what = bash_read(cmd)
    except Exception:  # noqa: BLE001 -- a command it cannot read may have read anything
        return "Bash (a command this guard could not read)"
    return f"Bash {what}" if what else None


def _first_line(message):
    if not isinstance(message, str):
        message = "" if message is None else json.dumps(message)
    line = next((ln.strip() for ln in message.splitlines() if ln.strip()), "")
    if not line:
        return "(no message)"
    return line if len(line) <= FIRST_LINE else line[:FIRST_LINE - 1].rstrip() + "…"


def check(payload, env=os.environ):
    event = payload.get("hook_event_name") or "PreToolUse"
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) and sid else None

    # --- the state hooks: record, never object ------------------------------
    if event != "PreToolUse":
        if sid is None:
            return None
        if event == "UserPromptSubmit":
            op, arg = "turn", None
        elif event == "SubagentStart":
            op, arg = "subagent", payload.get("agent_id")
            if not isinstance(arg, str) or not arg:
                return None
        else:
            op, arg = "read", untrusted_read(payload)
            if arg is None:
                return None
        try:
            yield Need("send-keep", sid, op, arg)
        except Exception:  # noqa: BLE001 -- World drops the state it could not write: no state asks or denies
            pass
        return None

    # --- the send -------------------------------------------------------------
    if payload.get("tool_name") != "SendMessage":
        return None
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    to = ti.get("to") if isinstance(ti.get("to"), str) else ""
    state = None
    if sid is not None:
        try:
            state = yield Need("send-state", sid)
        except Exception:  # noqa: BLE001 -- missing or unreadable: no subagents known, door not provably closed
            state = None
    subagents = state.get("subagents", []) if isinstance(state, dict) else []
    if to and (to in subagents or (to == "main" and payload.get("agent_id"))):
        return None
    closed = isinstance(state, dict) and state.get("read") is None
    mode = payload.get("permission_mode")
    target = f"`{to}`" if to else "an unnamed target"
    if mode in _NO_PROMPT or not isinstance(mode, str):
        if closed:
            return None if mode in _NO_PROMPT else ask(_ask_reason(target, ti))
        why = (f"this session read untrusted content this turn ({state['read']})" if isinstance(state, dict)
               else "this guard cannot tell whether this session read untrusted content this turn")
        return deny(f"{NAME}: a message to {target} is blocked: {why}, and in "
                    f"{mode or 'an unknown permission mode'} no prompt can show the user what leaves the "
                    f"session. {_WAY_OUT}")
    return ask(_ask_reason(target, ti))


def _ask_reason(target, ti):
    return (f"{NAME}: a message to {target}, which may be another of the user's sessions, "
            f"leaves this one: \"{_first_line(ti.get('message'))}\"")
