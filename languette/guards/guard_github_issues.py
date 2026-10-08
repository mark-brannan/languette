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

Counts as an identifier write: `gh issue create|new|transfer|delete`; `gh api`
POST to repos/o/r/issues; a graphql createIssue, transferIssue or deleteIssue;
the MCP create_issue, transfer_issue, delete_issue, and issue_write with
method create. `sh -c`, `eval` and `xargs` bodies are read; a script file is
not. The door is named apart from the claude plugin's own copy of this guard,
so the two never spend each other's (languette.world.DOOR).
"""

import re

from languette import scan as sw
from languette.verdict import Need, deny

NAME = "guard-github-issues"
# The tools hooks.json wires this guard to; the MCP ones by their name's tail.
TOOLS = re.compile(r"(?:Bash|mcp__.*__(?:create_issue|issue_write|transfer_issue|delete_issue))\Z")
_MCP_WRITE = re.compile(r"mcp__.*__(?:create_issue|transfer_issue|delete_issue)\Z")
_MCP_ISSUE_WRITE = re.compile(r"mcp__.*__issue_write\Z")
GH = re.compile(r"(?:^|/)gh\Z")
_REPEATS = re.compile(r"(?:^|/)(?:xargs|parallel|find)\Z")
_LOOP = frozenset("for while until select".split())
_LEAD = frozenset("do then else elif ! time { (".split())
_MUTATION = re.compile(r"(?:create|transfer|delete)Issue\s*\(")
_SKIP_VALUE = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
SHUT = ("the door is shut. One issue create, transfer or delete per human turn, and this turn's is spent or "
        "the human has not spoken since. Show the human the draft and wait for their yes.")


def _deny(why):
    return deny(f"{NAME}: {why}")


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def _skip_r(s, lo, hi):
    """The first word at or after lo that is not a flag, -R/--repo taking its value; or None."""
    i = lo
    while i <= hi:
        t = _wv(s, i)
        if t in ("-R", "--repo"):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        return i
    return None


class _Writes:
    """Walks a command for identifier writes: `n` of them, `loop` when one sits
    in a loop body or after a word that repeats it."""

    def __init__(self, command):
        self.n, self.loop = 0, False
        buf = command + "\n"
        self.hd = "".join(b + "\n" for b in sw.heredoc_bodies(buf))
        for text, nested in sw.texts_of(sw.strip_heredocs(buf)):
            s = sw.Scan(text)
            self.depth = 0
            for a, b in s.segments():
                if a <= b:
                    self._segment(s, a, b, nested)

    def _emit(self, rep):
        self.n += 1
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
        g = sw.cmd_index(s, lo, hi, GH, nested)
        if g is None or g + 1 > hi:
            return
        rep = any(s.k[i] == "w" and _REPEATS.search(s.w[i]) for i in range(lo, g))
        sub1 = _skip_r(s, g + 1, hi)
        if sub1 is None:
            return
        if s.w[sub1] == "issue":
            sub2 = _skip_r(s, sub1 + 1, hi)
            if sub2 is not None and s.w[sub2] in ("create", "new", "transfer", "delete"):
                self._emit(rep)
            return
        if s.w[sub1] != "api":
            return
        path, method, fields, m = "", "", False, 0
        i = sub1 + 1
        while i <= hi:
            t = _wv(s, i)
            m += len(_MUTATION.findall(t))
            if t in ("-X", "--method"):
                if i < hi:
                    i += 1
                    method = s.w[i].upper()
            elif t.startswith("--method="):
                method = t[9:].upper()
            elif t.startswith("-X") and len(t) > 2:
                method = t[2:].upper()
            elif t in ("-f", "-F", "--field", "--raw-field", "--input"):
                fields = True
                if i < hi:
                    i += 1
                    m += len(_MUTATION.findall(_wv(s, i)))
            elif re.match(r"-[fF].|--(?:field|raw-field|input)=", t):
                fields = True
            elif t in _SKIP_VALUE:
                i += 1
            elif not t.startswith("-") and path == "":
                path = t
            i += 1
        path = re.sub(r"^/+", "", re.sub(r"^https?://[^/]+/", "", path, count=1), count=1)
        if re.fullmatch(r"repos/[^/]+/[^/]+/issues/?", path) and (method == "POST" or (method == "" and fields)):
            self._emit(rep)
        if path == "graphql":
            m += len(_MUTATION.findall(self.hd))
            self.hd = ""
            for _ in range(m):
                self._emit(rep)


def _writes(payload):
    """(identifier writes in this call, whether one is in a loop)."""
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    if tool == "Bash":
        command = ti.get("command")
        if not isinstance(command, str):
            return 0, False
        w = _Writes(command)
        return w.n, w.loop
    if isinstance(tool, str) and _MCP_WRITE.match(tool):
        return 1, False
    if isinstance(tool, str) and _MCP_ISSUE_WRITE.match(tool):
        return (1 if ti.get("method") == "create" else 0), False
    return 0, False


def _session(payload):
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) and sid else "none"
    return re.sub(r"[^A-Za-z0-9_\n-]", "_", sid)


def _never_ran(transcript, call):
    """The transcript holds an error result for `call`: refused, never run."""
    pat = re.compile(r'"tool_use_id": ?"' + re.escape(call) + '"')
    return any(pat.search(line) and re.search(r'"is_error": ?true', line) for line in transcript.splitlines())


def check(payload, env):
    event = payload.get("hook_event_name") or "PreToolUse"
    session = _session(payload)
    if event == "UserPromptSubmit":
        try:
            yield Need("door", "open", session)
        except Exception:  # noqa: BLE001 -- a door that cannot open stays shut
            pass
        return None
    if event in ("PostToolUse", "PostToolUseFailure"):
        # The call ran (or tried to): spend the door whatever the verdict was, so a
        # failed create cannot be followed by a second in the same turn. A call
        # that cannot be read spends it too.
        try:
            n, _ = _writes(payload)
        except Exception:  # noqa: BLE001
            n = 1
        if n:
            try:
                yield Need("door", "spend", session)
            except Exception:  # noqa: BLE001
                pass
        return None
    try:
        n, loop = _writes(payload)
    except Exception as e:  # noqa: BLE001 -- fails closed
        return _deny(f"the command could not be read ({type(e).__name__}), so this call could not be checked")
    if n == 0:
        return None
    if n > 1:
        return _deny(f"{n} issue creates, transfers or deletes in one call. One per human turn, never a batch.")
    if loop:
        return _deny("an issue create, transfer or delete inside a loop. One per human turn, never a batch.")
    call = payload.get("tool_use_id")
    call = re.sub(r"[^A-Za-z0-9_-]", "", call) if isinstance(call, str) else ""
    try:
        got = yield Need("door", "claim", session, call)
    except Exception:  # noqa: BLE001
        return _deny(SHUT)
    if got is True:
        return None
    if got is False:
        return _deny(f"an issue create, transfer or delete is already in flight this turn. {SHUT}")
    # A standing claim: its call ran if it was spent; still holding with an error
    # result means it was refused and never ran. No result yet: in flight. A
    # result that is not an error ran, whatever its post hook did.
    tp = payload.get("transcript_path")
    if not got or not isinstance(tp, str) or not tp:
        return _deny(SHUT)
    try:
        transcript = yield Need("read", tp)
    except Exception:  # noqa: BLE001
        return _deny(SHUT)
    if not _never_ran(transcript, got):
        return _deny(SHUT)
    try:
        took = yield Need("door", "take", session, call)
    except Exception:  # noqa: BLE001
        took = False
    return None if took else _deny(SHUT)
