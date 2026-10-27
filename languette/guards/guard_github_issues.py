"""guard-github-issues: one GitHub issue create, transfer or delete per human
turn; never two in one call, never one in a loop. An issue number is an
identifier things link to where no agent can see, so minting or moving one is
a one-way door. The spec is features/guard-github-issues.feature.

The human's turn opens the door (UserPromptSubmit); a write claims it before
the call (PreToolUse) and spends it once the call has run (PostToolUse,
PostToolUseFailure). Each guard is its own hook process and cannot see the
others' verdicts, so a claim whose call has an error result in the transcript
but was never spent belongs to a call another guard denied: it never ran, and
the next write takes the claim over. A claim with no result yet is in flight.

A shut door has a second key: the user's yes, through AskUserQuestion, to an
option labelled exactly as `_label` names the write: its verb, and the issue
when the call names one, with its repo when the call does too ("File this
issue", "Delete issue o/r#7", "Delete issue 7"). A yes
to file opens no delete, and a yes to delete issue 7 opens no other. Each yes
allows one write and is spent the way ask-first spends one
(languette.verdict.claim), so several in a row take one question
each.

Counts as an identifier write: `gh issue create|new|transfer|delete`; `gh api`
POST to repos/o/r/issues; a graphql createIssue, transferIssue or deleteIssue;
the MCP create_issue, transfer_issue, delete_issue, and issue_write with
method create. `sh -c`, `eval` and `xargs` bodies are read; a script file is
not. The door file carries a languette- prefix (languette.world.DOOR), so
another plugin's copy of this guard never spends it.
"""

import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import Act, Need, approve, deny

NAME = "guard-github-issues"
# The tools hooks.json wires this guard to; the MCP ones by their name's tail.
TOOLS = re.compile(r"(?:Bash|mcp__.*__(?:create_issue|issue_write|transfer_issue|delete_issue))\Z")
_MCP_WRITE = re.compile(r"mcp__.*__(?:create_issue|transfer_issue|delete_issue)\Z")
_MCP_ISSUE_WRITE = re.compile(r"mcp__.*__issue_write\Z")
_REPEATS = re.compile(r"(?:^|/)(?:xargs|parallel|find)\Z")
_LOOP = frozenset("for while until select".split())
_LEAD = frozenset("do then else elif ! time { (".split())
_MUTATION = re.compile(r"(create|transfer|delete)Issue\s*\(")
SHUT = ("the door is shut. One issue create, transfer or delete per human turn, and this turn's is spent or "
        "the human has not spoken since.")
_NUMBER = re.compile(r"#?(\d+)|https?://[^/\s]+/([^/\s]+/[^/\s]+)/issues/(\d+)/?")


def _label(verb, number, repo=None):
    """The option a yes to this write must carry: its verb, and its issue (repo#number) when known."""
    if verb == "create":
        return "File this issue"
    if not number:
        return f"{verb.title()} this issue"
    return f"{verb.title()} issue {repo}#{number}" if repo else f"{verb.title()} issue {number}"


def _repo_flag(s, lo, hi):
    """The repo a -R/--repo flag names between lo and hi, the last one as gh
    reads them; or None."""
    repo, i = None, lo
    while i <= hi:
        if r := sw.gh_repo_flag(s, i, hi, repo):
            repo, i = r
        i += 1
    return repo


class _Writes:
    """Walks a command for identifier writes: `found`, a (verb, issue number or
    None, repo or None) per write, and `loop` when one sits in a loop body or after a word that
    repeats it."""

    def __init__(self, doc):
        self.found, self.loop = [], False
        self.hd = "".join(b + "\n" for b in doc.heredoc_bodies())
        for text, nested in doc.texts():
            s = doc.scan(text)
            self.depth = 0
            for a, b in s.segments():
                if a <= b:
                    self._segment(s, a, b, nested)

    def _emit(self, rep, verb, number=None, repo=None):
        self.found.append((verb, number, repo))
        if self.depth > 0 or rep:
            self.loop = True

    def _segment(self, s, lo, hi, nested):
        i = lo
        while i <= hi and s.k[i] == "w":
            if sw._ASSIGN.match(s.w[i]):
                i += 1
                continue
            if s.w[i] in _LOOP:
                self.depth += 1
                break
            if s.w[i] not in _LEAD:
                break
            i += 1
        if s.k[lo] == "w" and s.w[lo] == "done" and self.depth > 0:
            self.depth -= 1
        g = sw.cmd_index(s, lo, hi, sw.GH, nested)
        if g is None or g + 1 > hi:
            return
        rep = any(s.k[i] == "w" and _REPEATS.search(s.w[i]) for i in range(lo, g))
        sub1 = sw.gh_verb(s, g + 1, hi)
        if sub1 is None:
            return
        if s.w[sub1] == "issue":
            sub2 = sw.gh_verb(s, sub1 + 1, hi)
            if sub2 is not None and s.w[sub2] in ("create", "new"):
                self._emit(rep, "create")
            elif sub2 is not None and s.w[sub2] in ("transfer", "delete"):
                arg = sw.gh_verb(s, sub2 + 1, hi)
                hit = _NUMBER.fullmatch(sw.word(s, arg)) if arg is not None else None
                number = hit and (hit[1] or hit[3])
                repo = number and ((hit[2] if hit else None) or _repo_flag(s, g + 1, hi))
                self._emit(rep, s.w[sub2], number, repo)
            return
        if s.w[sub1] != "api":
            return
        api = sw.gh_api(s, sub1 + 1, hi)
        m = [x for i in range(sub1 + 1, hi + 1) if i not in api.skipped for x in _MUTATION.findall(sw.word(s, i))]
        if re.fullmatch(r"repos/[^/]+/[^/]+/issues", api.path) and (
                api.method == "POST" or (api.method == "" and api.sends)):
            self._emit(rep, "create")
        if api.path == "graphql":
            m += _MUTATION.findall(self.hd)
            self.hd = ""
            for verb in m:
                self._emit(rep, verb)


def _writes(doc):
    """([(verb, issue number or None, repo or None)] for this call's identifier writes, whether one is in a loop)."""
    tool = doc.tool
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    if tool == "Bash":
        command = ti.get("command")
        if not isinstance(command, str):
            return [], False
        w = _Writes(doc)
        return w.found, w.loop
    if isinstance(tool, str) and _MCP_WRITE.match(tool):
        verb = re.search(r"(create|transfer|delete)_issue\Z", tool)[1]
        number = ti.get("issue_number")
        number = str(number) if isinstance(number, int) or (isinstance(number, str) and number.isdigit()) else None
        owner, name = ti.get("owner"), ti.get("repo")
        repo = f"{owner}/{name}" if isinstance(owner, str) and isinstance(name, str) and owner and name else None
        return [(verb, number, number and repo)], False
    if isinstance(tool, str) and _MCP_ISSUE_WRITE.match(tool):
        return ([("create", None, None)] if ti.get("method") == "create" else []), False
    return [], False


def _session(payload):
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) and sid else "none"
    return re.sub(r"[^A-Za-z0-9_\n-]", "_", sid)


def _never_ran(transcript, call):
    """The transcript holds an error result for `call`: refused, never run."""
    pat = re.compile(r'"tool_use_id": ?"' + re.escape(call) + '"')
    return any(pat.search(line) and re.search(r'"is_error": ?true', line) for line in transcript.splitlines())


def check(doc):
    payload = doc.payload
    event = payload.get("hook_event_name") or "PreToolUse"
    session = _session(payload)
    if event == "UserPromptSubmit":
        yield Act("door-open", session)        # a door that cannot open stays shut
        return None
    if event in ("PostToolUse", "PostToolUseFailure"):
        # The call ran (or tried to): spend the door whatever the verdict was, so a
        # failed create cannot be followed by a second in the same turn. A call
        # that cannot be read spends it too.
        try:
            found, _ = _writes(doc)
        except Exception:  # noqa: BLE001
            found = [None]
        if found:
            yield Act("door-spend", session)
        return None
    try:
        found, loop = _writes(doc)
    except Exception as e:  # noqa: BLE001 -- fails closed
        return deny(say("gi_unreadable", guard=NAME, kind=type(e).__name__))
    n = len(found)
    if n == 0:
        return None
    if n > 1:
        return deny(say("gi_batch", guard=NAME, n=n))
    if loop:
        return deny(say("gi_loop", guard=NAME))
    why = yield from _door(payload, session)
    if why is None:
        return None
    label = _label(*found[0])
    _, done = yield from approve(
        {label: 1}, lambda e: say("gi_transcript", guard=NAME, err=e, why=why, ask=say("gi_ask", label=label)))
    return done[0] if done else deny(say("gi_door", guard=NAME, why=why, ask=say("gi_ask", label=label)))


def _door(payload, session):
    """None when this call took the human turn's door; else why it could not."""
    call = payload.get("tool_use_id")
    call = re.sub(r"[^A-Za-z0-9_-]", "", call) if isinstance(call, str) else ""
    try:
        got = yield Need("door", "claim", session, call)
    except Exception:  # noqa: BLE001
        return SHUT
    if got is True:
        return None
    if got is False:
        return f"an issue create, transfer or delete is already in flight this turn. {SHUT}"
    # A standing claim: its call ran if it was spent; still holding with an error
    # result means it was refused and never ran. No result yet: in flight. A
    # result that is not an error ran, whatever its post hook did.
    tp = payload.get("transcript_path")
    if not got or not isinstance(tp, str) or not tp:
        return SHUT
    try:
        transcript = yield Need("read", tp)
    except Exception:  # noqa: BLE001
        return SHUT
    if not _never_ran(transcript, got):
        return SHUT
    try:
        took = yield Need("door", "take", session, call)
    except Exception:  # noqa: BLE001
        took = False
    return None if took else SHUT
