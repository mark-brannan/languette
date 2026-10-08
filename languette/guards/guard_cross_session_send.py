"""guard-cross-session-send: features/guard-cross-session-send.feature is the spec.

A session that has read untrusted content (anything fetched from the network:
a web page, an issue or PR body, an MCP read) must not relay instruction-shaped
text into another of the user's sessions unexamined. No hook fires where a
message is received, so the guard sits on the sender: PreToolUse on
SendMessage. The same tool talks to this session's own subagents and
teammates, and to "main", which is ordinary and passes.

    target is "main", a subagent or a teammate of this session -> no objection
    bypassPermissions, untrusted read this session             -> deny
    bypassPermissions, nothing untrusted read                  -> no objection
    any other mode                                             -> ask, showing target and first line

Per-session state, kept by World under $TMPDIR and keyed by session_id, is fed
by the same guard on other events. PostToolUse (and PostToolUseFailure) on a
network read opens the door, and stays open for the session: the text is
still in its context. SessionStart for a new or cleared session closes it, and
no state file is a closed door. PostToolUse on Agent records the subagent's
name and id (SubagentStart carries the id, not the name); SubagentStart
records the id too. Teammates are read from the session's team config,
~/.claude/teams/session-<first 8 of session_id>/config.json (the agent-teams
docs' layout).

Both files are ones the guarded agent can write, or delete, with an ordinary
file tool: like guard-github-issues' door, this guards against an agent
relaying by accident, not one working to get round it.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import Need, ask, deny

NAME = "guard-cross-session-send"

FIRST_LINE = 80
_FETCHERS = frozenset({"curl", "wget", "fetch"})
_GH = re.compile(r"(?:^|/)gh\Z")
# gh issue and gh pr subcommands that only write; every other one reads.
_GH_WRITES = frozenset("create new edit close reopen delete transfer comment merge review ready lock unlock pin "
                       "unpin develop".split())
_API_METHOD = re.compile(r"(?:-X|--method=?)(.*)")
_API_FIELDS = frozenset("-f -F --field --raw-field --input".split())
_API_FIELDS_GLUED = ("-f", "-F", "--field=", "--raw-field=", "--input=")
# An MCP tool is a read unless its name is clearly a write: a write verb and no read verb.
_MCP_READ = frozenset("read get list search fetch query find view download export retrieve".split())
_MCP_WRITE = frozenset("write create update delete add remove push merge set edit post send submit close assign "
                       "request fork transfer lock unlock move rename upload put patch insert reply resolve "
                       "dismiss approve label star unstar archive restore withdraw pray".split())
# Modes where an ask cannot be shown, so it would pass the call unseen.
_NO_PROMPT = frozenset({"bypassPermissions"})
# SessionStart sources that begin a context without what an earlier one read.
_FRESH = frozenset({"startup", "clear"})
_REF = re.compile(r" \[[^\]\n]*\]\Z")

_WAY_OUT = ("Ask the user to send it themselves, or from a session that has not read untrusted content; "
            "/clear starts this one afresh.")


def _gh_reads(words):
    """Does `gh <words>` read issue, PR, search or API content?"""
    i = 0
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in ("-R", "--repo") else 1
    if i >= len(words):
        return False
    sub, rest = words[i], words[i + 1:]
    if sub == "search":
        return True
    if sub in ("issue", "pr"):
        verb = next((w for j, w in enumerate(rest) if not w.startswith("-")
                     and not (j and rest[j - 1] in ("-R", "--repo"))), None)
        return verb not in _GH_WRITES
    if sub == "api":
        method = None
        for j, w in enumerate(rest):
            m = _API_METHOD.fullmatch(w)
            if m:
                method = (m.group(1) or (rest[j + 1] if j + 1 < len(rest) else "")).upper()
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            return False
        graphql = any(w.lstrip("/") == "graphql" for w in rest)
        fields = any(w in _API_FIELDS or w.startswith(_API_FIELDS_GLUED) for w in rest)
        if method is None and fields and not graphql:
            return False                       # gh api sends fields as a POST
        return not (graphql and any("mutation" in w for w in rest))
    return False


_VALUED = frozenset("-R --repo -X --method -H --header -f -F --field --raw-field --input -q --jq -t --template "
                    "-p --preview --hostname --cache".split())


def _operands(words):
    """The words that are neither options nor an option's value."""
    out, skip = [], False
    for w in words:
        if skip:
            skip = False
        elif w in _VALUED:
            skip = True
        elif not w.startswith("-"):
            out.append(w)
    return out


def bash_read(command):
    """What a Bash command fetched from the network, or None: a curl, wget or
    fetch anywhere among its words, or a `gh` read."""
    for text, nested in sw.texts_of(sw.strip_heredocs(command.rstrip("\n") + "\n")):
        s = sw.Scan(text)
        for i, w in enumerate(s.w):
            if s.k[i] == "w" and os.path.basename(w) in _FETCHERS:
                return f"`{os.path.basename(w)}`"
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, _GH, nested) if a <= b else None
            if g is None:
                continue
            words = [s.q[i] if s.k[i] == "q" else s.w[i] for i in range(g + 1, b + 1)]
            if _gh_reads(words):
                return "`gh " + " ".join(_operands(words)[:2]) + "`"
    return None


def _mcp_reads(tool):
    words = set(re.split(r"[_\-]+", tool.rsplit("__", 1)[-1].lower()))
    return bool(words & _MCP_READ) or not words & _MCP_WRITE


def untrusted_read(payload):
    """The tool that read untrusted content, as the deny names it, or None."""
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return None
    if tool in ("WebFetch", "WebSearch"):
        return tool
    if tool.startswith("mcp__"):
        return tool if _mcp_reads(tool) else None
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


def spawned(payload):
    """The names and ids an Agent call's PostToolUse shows for the subagent it started."""
    ti, tr = payload.get("tool_input"), payload.get("tool_response")
    out = [ti.get("name")] if isinstance(ti, dict) else []
    if isinstance(tr, dict):
        out += [tr.get("agentId"), tr.get("agent_id")]
    return [x for x in out if isinstance(x, str) and x]


def _teammates(text):
    """Names and agent ids of the members of a team config."""
    cfg = json.loads(text)
    members = cfg.get("members") if isinstance(cfg, dict) else None
    return {v for m in members or () if isinstance(m, dict)
            for v in (m.get("name"), m.get("agentId"), m.get("agent_id")) if isinstance(v, str) and v}


# Control characters and bidi overrides: either can make what the dialog shows
# differ from what is sent.
_UNSHOWN = re.compile(r"[\x00-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")


def _shown(text):
    text = _UNSHOWN.sub("?", text.strip())
    return text if len(text) <= FIRST_LINE else text[:FIRST_LINE - 1].rstrip() + "…"


def _first_line(message):
    """The message's first non-empty line as the dialog shows it, and how many
    non-empty lines follow it unseen."""
    if not isinstance(message, str):
        message = "" if message is None else json.dumps(message)
    lines = [ln for ln in message.splitlines() if ln.strip()]
    if not lines:
        return '"(no message)"'
    more = f" (+{len(lines) - 1} more line{'s' if len(lines) > 2 else ''})" if len(lines) > 1 else ""
    return f'"{_shown(lines[0])}"{more}'


def _record(payload, event):
    """(op, arg) for World's send-keep, or None when the event changes nothing."""
    if event == "SessionStart":
        return ("clear", None) if payload.get("source") in _FRESH else None
    if event == "SubagentStart":
        aid = payload.get("agent_id")
        return ("names", [aid]) if isinstance(aid, str) and aid else None
    if payload.get("tool_name") == "Agent":
        names = spawned(payload)
        return ("names", names) if names else None
    what = untrusted_read(payload)
    return ("read", what) if what else None


def check(payload, env=os.environ):
    event = payload.get("hook_event_name") or "PreToolUse"
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) and sid else None

    # --- the state hooks: record, never object ------------------------------
    if event != "PreToolUse":
        rec = _record(payload, event) if sid else None
        if rec:
            try:
                yield Need("send-keep", sid, *rec)
            except Exception:  # noqa: BLE001 -- World leaves an open door in place of a write that failed
                pass
        return None

    # --- the send -------------------------------------------------------------
    if payload.get("tool_name") != "SendMessage":
        return None
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    to = ti.get("to") if isinstance(ti.get("to"), str) else ""
    bare = _REF.sub("", to)
    if bare == "main":
        return None
    state, lost = None, sid is None
    if sid is not None:
        try:
            state = yield Need("send-state", sid)
        except FileNotFoundError:
            state = {"subagents": [], "read": None}       # no state: nothing read, no subagents known
        except Exception:  # noqa: BLE001 -- a link, someone else's, or garbled: the door is not provably closed
            lost = True
    if bare and isinstance(state, dict) and bare in state.get("subagents", ()):
        return None
    if bare and sid is not None:
        home = env.get("HOME") or ""
        try:
            team = yield Need("read", os.path.join(home, ".claude", "teams", f"session-{sid[:8]}", "config.json"))
            if bare in _teammates(team):
                return None
        except Exception:  # noqa: BLE001 -- no team, or one this guard cannot read: no teammates known
            pass
    closed = not lost and state.get("read") is None
    mode = payload.get("permission_mode")
    target = f"`{_shown(to)}`" if to else "an unnamed target"
    if mode in _NO_PROMPT or not isinstance(mode, str):
        if closed:
            return None if mode in _NO_PROMPT else ask(_ask_reason(target, ti))
        why = (f"this session read untrusted content ({state['read']})" if not lost
               else "this guard cannot tell whether this session read untrusted content")
        return deny(f"{NAME}: a message to {target} is blocked: {why}, and in "
                    f"{mode or 'an unknown permission mode'} no prompt can show the user what leaves the "
                    f"session. {_WAY_OUT}")
    return ask(_ask_reason(target, ti))


def _ask_reason(target, ti):
    return (f"{NAME}: a message to {target}, which may be another of the user's sessions, "
            f"leaves this one: {_first_line(ti.get('message'))}")
