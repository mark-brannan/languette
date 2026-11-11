"""guard-cross-session-send's walks and its handlers (languette/rules/guard_cross_session_send.py
is the rule set). The spec is features/guard-cross-session-send.feature.

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
still in its context. Only SessionStart for a new or cleared session writes a
closed door; a missing or unreadable file is unknown, which denies where no
prompt can fire and asks elsewhere. A resumed or compacted session keeps the
file it has, and with none stays unknown. PostToolUse on Agent records the subagent's
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
from languette.paths import config_dir
from languette.messages import say
from languette.verdict import NO_PROMPT, NO_QUESTION, Act, Need, ask, deny

FIRST_LINE = 80
_FETCH = re.compile(r"(?:^|/)fetch\Z")      # BSD fetch, at command position only: never `git fetch`
_FETCHERS = frozenset({"curl", "wget"})
# gh issue and gh pr subcommands that only write; every other one reads.
_GH_WRITES = frozenset("create new edit close reopen delete transfer comment merge review ready lock unlock pin "
                       "unpin develop".split())
# Other gh subcommands whose named verbs show what others wrote: a run's log
# echoes PR text, a release or gist its body, a repo its README.
_GH_VIEWS = {"run": ("view", "download"), "release": ("view", "download"), "gist": ("view",),
             "repo": ("view",), "workflow": ("view",)}
# glab's, on GitLab (docs/design/forges.md): issue and mr verbs that only write, and the
# other groups' verbs that show what others wrote: a job's log, a pipeline, a release, a
# project's README. A note verb writes, but for its `list`.
_GLAB_WRITES = frozenset("create new edit update close reopen delete del note comment subscribe unsubscribe "
                         "approve revoke merge accept rebase todo".split())
_GLAB_VIEWS = {"ci": ("view", "trace", "get", "artifact"), "pipe": ("view", "trace", "get", "artifact"),
               "pipeline": ("view", "trace", "get", "artifact"),
               "release": ("view", "download"), "repo": ("view",), "project": ("view",)}
# An MCP tool is a read unless its name is clearly a write: a write verb and no read verb.
_MCP_READ = frozenset("read get list search fetch query find view download export retrieve".split())
_MCP_WRITE = frozenset("write create update delete add remove push merge set edit post send submit close assign "
                       "request fork transfer lock unlock move rename upload put patch insert reply resolve "
                       "dismiss approve label star unstar archive restore withdraw".split())
# Modes where an ask would pass the call unseen. dontAsk is left out: it falls
# through to the ask path, where verdict turns the ask into a deny.
_UNSEEN_ASK = NO_PROMPT - NO_QUESTION
# SessionStart sources that begin a context without what an earlier one read.
_FRESH = frozenset({"startup", "clear"})
_REF = re.compile(r" \[[^\]\n]*\]\Z")

_WAY_OUT = say("cross_session_way_out")


def _gh_reads(s, lo, hi, cli="gh"):
    """Does `gh` with words lo..hi read issue, PR, search or API content, or view a run, release, gist, repo or
    workflow? `glab`'s (cli "glab"): issue, merge request or API content, or a pipeline, job log, release or repo."""
    i = sw.gh_verb(s, lo, hi)
    if i is None:
        return False
    sub, rest = sw.word(s, i), [sw.word(s, j) for j in range(i + 1, hi + 1)]
    groups, writes, views = (("issue", "mr", "incident"), _GLAB_WRITES, _GLAB_VIEWS) if cli == "glab" else \
        (("issue", "pr"), _GH_WRITES, _GH_VIEWS)
    if sub == "search" and cli == "gh":
        return True
    if sub in groups or sub in views:
        verbs = [w for j, w in enumerate(rest) if not w.startswith("-") and not (j and rest[j - 1] in sw.GH_REPO_FLAGS)]
        verb = verbs[0] if verbs else None
        if cli == "glab" and verb in ("note", "comment") and verbs[1:2] == ["list"]:
            return True
        return verb not in writes if sub in groups else verb in views[sub]
    if sub == "api":
        api = sw.gh_api(s, i + 1, hi, cli)
        if api.method in ("POST", "PUT", "PATCH", "DELETE"):
            return False
        graphql = api.path == "graphql"
        if api.method == "" and api.sends and not graphql:
            return False                       # gh api sends fields as a POST
        return not (graphql and any("mutation" in w for w in rest))
    return False


def bash_read(doc):
    """What the Bash command fetched from the network, or None: a curl or wget
    anywhere among its words, fetch as the command run, or a `gh` or `glab` read."""
    for text, nested in doc.texts():
        s = doc.scan(text)
        for i, w in enumerate(s.w):
            if s.k[i] == "w" and sw.basename(w) in _FETCHERS:
                return f"`{sw.basename(w)}`"
        for a, b in s.segments():
            if a <= b and sw.cmd_index(s, a, b, _FETCH, True) is not None:
                return "`fetch`"
            g = sw.cmd_index(s, a, b, sw.CLIENTS, nested) if a <= b else None
            if g is None:
                continue
            cli = sw.client(s.w[g])
            if _gh_reads(s, g + 1, b, cli):
                words = [sw.word(s, i) for i in range(g + 1, b + 1)]
                return f"`{cli} " + " ".join(sw.operands(words, sw.GH_API_VALUE)[:2]) + "`"
    return None


def _mcp_reads(tool):
    words = set(re.split(r"[_\-]+", tool.rsplit("__", 1)[-1].lower()))
    return bool(words & _MCP_READ) or not words & _MCP_WRITE


def untrusted_read(doc):
    """The tool that read untrusted content, as the deny names it, or None."""
    tool = doc.tool
    if not isinstance(tool, str):
        return None
    if tool in ("WebFetch", "WebSearch"):
        return tool
    if tool.startswith("mcp__"):
        return tool if _mcp_reads(tool) else None
    if tool != "Bash":
        return None
    ti = doc.tool_input
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        return None
    try:
        what = bash_read(doc)
    except Exception:  # noqa: BLE001 -- a command it cannot read may have read anything
        return "Bash (a command this guard could not read)"
    return f"Bash {what}" if what else None


def spawned(doc):
    """The names and ids an Agent call's PostToolUse shows for the subagent it started."""
    ti, tr = doc.tool_input, doc.payload.get("tool_response")
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


# Control characters, invisible joiners and bidi overrides: each can make what
# the dialog shows differ from what is sent. A backtick would end the target's
# quoting in the dialog.
_UNSHOWN = re.compile(r"[\x00-\x1f\x7f-\x9f\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


def _shown(text):
    text = _UNSHOWN.sub("?", text.strip()).replace("`", "'")
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


def _record(doc, event):
    """(op, arg) for World's send-keep, or None when the event changes nothing."""
    payload = doc.payload
    if event == "SessionStart":
        return ("clear", None) if payload.get("source") in _FRESH else None
    if event == "SubagentStart":
        aid = payload.get("agent_id")
        return ("names", [aid]) if isinstance(aid, str) and aid else None
    if doc.tool == "Agent":
        names = spawned(doc)
        return ("names", names) if names else None
    what = untrusted_read(doc)
    return ("read", what) if what else None


def _sid(doc):
    sid = doc.payload.get("session_id")
    return sid if isinstance(sid, str) and sid else None


# --- the state hooks: record, never object ------------------------------------

def keep(doc, guard, found):
    """The `session-keep` handler, on every state event the rule set's `on` names: writes what
    the event records for a known session, and never objects."""
    sid = _sid(doc)
    rec = _record(doc, doc.event) if sid and doc.event != "PreToolUse" else None   # a call yet to run: nothing
    if rec:
        yield Act("send-keep", sid, *rec)      # a write that fails leaves an open door (World._send_keep)
    return None


# --- the send -------------------------------------------------------------------

def sent(doc):
    """The `send-elsewhere` test: a SendMessage to any target but "main", {"to": the target,
    "" when it names none}, or None."""
    if doc.event != "PreToolUse" or doc.tool != "SendMessage":
        return None
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    to = ti.get("to") if isinstance(ti.get("to"), str) else ""
    return None if to == "main" else {"to": to}


def door(doc, guard, found):
    """The `send-door` handler: a send to this session's own subagent or teammate passes; any
    other target is judged by what the session's record says it read, and the permission mode."""
    env, sid, to = doc.env, _sid(doc), found["to"]
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    state, lost = None, sid is None
    if sid is not None:
        try:
            state = yield Need("send-state", sid)
        except Exception:  # noqa: BLE001 -- missing, a link, someone else's, or garbled: the door is unknown
            lost = True
    # A " [ref]" picks one agent among several of a name; none is recorded, so
    # an in-session match is exact: a ref'd name is another session's.
    if to and isinstance(state, dict) and to in state.get("subagents", ()):
        return None
    if to and not _REF.search(to) and sid is not None:
        try:
            team = yield Need("read", os.path.join(config_dir(env), "teams", f"session-{sid[:8]}", "config.json"))
            if to in _teammates(team):
                return None
        except Exception:  # noqa: BLE001 -- no team, or one this guard cannot read: no teammates known
            pass
    closed = not lost and state.get("read") is None
    mode = doc.mode
    target = f"`{_shown(to)}`" if to else "an unnamed target"
    if mode in _UNSEEN_ASK or not isinstance(mode, str):
        if closed:
            return None if mode in _UNSEEN_ASK else _ask_user(guard, target, ti)
        why = (f"this session read untrusted content ({state['read']})" if not lost
               else "this guard cannot tell whether this session read untrusted content")
        return deny(say("cross_session_deny", guard=guard, target=target, why=why,
                        mode=mode or "an unknown permission mode", way_out=_WAY_OUT))
    return _ask_user(guard, target, ti)


def _ask_user(guard, target, ti):
    return ask(say("cross_session_ask", guard=guard, target=target, first_line=_first_line(ti.get("message"))))
