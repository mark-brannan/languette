"""guard-signed-comments: a comment an agent posts to GitHub is signed as an
agent's. The spec is features/guard-signed-comments.feature.

An agent posts under the user's own login, so without a mark a review bot and
the next agent read its reply as the user's ruling. The body's first line
begins with `🤖 ` and its last non-empty line is `🤖 <model> · <effort> ·
<eight hex>`; the hex is the payload's session id's, when it has one.

Fires on Bash `gh pr comment`, `gh issue comment`, `gh pr review` with a body,
`gh pr|issue close|reopen --comment`, `gh api` writing a body to a path with a
comments or reviews segment, and `gh api graphql` whose query adds, edits or
submits a comment, review or thread reply; and on the GitHub MCP tools that
post one, where every `body` in the input is judged. The body is read where it
is written: --body/-b, --body-file/-F, a gh api body field (literal or -F
@file), --input JSON, a heredoc in the command, `$(cat <<EOF)` around one, or
a $VAR this command assigns from one. Off by default: the signature is a
convention a workflow sets, so the guard runs only when its option is true.
Anything else built at run time is a deny, read as guard-private-terms reads
it, with the fix in the reason.
"""

import json
import os
import re

from languette import scan as sw
from languette.guards.guard_private_terms import writes
from languette.verdict import Need, deny

NAME = "guard-signed-comments"
_MCP = ("add_issue_comment|add_reply_to_pull_request_comment|add_comment_to_pending_review|"
        "pull_request_review_write|update_issue_comment|add_pull_request_review_comment|create_pull_request_review|"
        "create_and_submit_pull_request_review|submit_pending_pull_request_review")
# The tools hooks.json wires this guard to; the MCP ones by their name's tail.
TOOLS = re.compile(rf"(?:Bash|mcp__.*__(?:{_MCP}))\Z")
_MCP_TOOL = re.compile(rf"mcp__.*__(?:{_MCP})\Z")
GH = re.compile(r"(?:^|/)gh\Z")
FIRST = "🤖 "
SIGNATURE = re.compile(r"🤖 \S+ · (?:low|medium|high|xhigh|max|-) · ([0-9a-f]{8})")
_MUTATION = re.compile(r"\b(?:addComment|addPullRequestReviewComment|addPullRequestReviewThreadReply|"
                       r"addPullRequestReview|submitPullRequestReview|updateIssueComment|"
                       r"updatePullRequestReviewComment|updatePullRequestReview|addDiscussionComment|"
                       r"updateDiscussionComment)\b")
_COMMENTS = re.compile(r"(?:^|/)(?:comments|reviews)(?:/|\Z)")
_SKIP_VALUE = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
_FROM_DOC = re.compile(r"\$\(\s*cat\s+(?:-\s+)?HEREDOC(\d+)\s*\)")
_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_HOME = re.compile(r"(?:~|\$HOME|\$\{HOME\})(?=/|\Z)")
_MARK = " HEREDOC "
# The two lines a body needs, shown in every reason, with the payload's session hex.
_EXAMPLE = "🤖 Fixed in a03793a: …\n\n🤖 claude-opus-5-5 · high · {hex}"
# gh's verbs that post a comment, and the flags that carry its body.
_VERBS = {("pr", "comment"): "b", ("issue", "comment"): "b", ("pr", "review"): "b",
          ("pr", "close"): "c", ("pr", "reopen"): "c", ("issue", "close"): "c", ("issue", "reopen"): "c"}


class _Unread(Exception):
    """A body this guard cannot see before it is posted; the message is the fix."""


def _short(v):
    v = v.replace("\n", " ")
    return v if len(v) <= 80 else v[:77] + "..."


class _Read:
    """The command's posts, each a list of body sources:
    (text, s) | (doc, k) heredoc k | (file, path) | (json, src) | (graphql, qsrc, fields, input) |
    (opaque, why)."""

    def __init__(self, command):
        buf = command + "\n"
        self.docs = [b for b, _ in sw.heredocs(buf)]
        stripped = sw.strip_heredocs(buf)
        parts = stripped.split(_MARK)
        # Number each marker so a value, a stdin or a file can name its heredoc.
        if len(parts) - 1 == len(self.docs):
            stripped = "".join(p + (f" HEREDOC{k} " if k < len(parts) - 1 else "") for k, p in enumerate(parts))
        else:
            self.docs = None
        self.text = stripped
        self.fed, self.written = {}, {}
        for line in stripped.split("\n"):
            ks = re.findall(r"\bHEREDOC(\d+)\b", line)
            for p in writes(line, False):
                self.written[p] = self.written.get(p, 0) + 1
                if len(ks) == 1:
                    self.fed[p] = int(ks[0])
        self.cd = False
        self.posts = []
        for text, nested in sw.texts_of(stripped):
            s = self.s = sw.Scan(text)
            self.cd = self.cd or any(s.k[i] == "w" and s.w[i] in ("cd", "pushd", "popd") for i in range(len(s.w)))
            for a, b in s.segments():
                if a <= b:
                    self.segment(a, b, nested)

    def wv(self, i):
        return self.s.q[i] if self.s.k[i] == "q" else self.s.w[i]

    def doc(self, k):
        return ("doc", k) if self.docs is not None else ("opaque", "a heredoc this hook could not pair with its use")

    def val(self, v, live):
        """A posted value, read as guard-private-terms reads one."""
        if not live:
            return ("text", v)
        m = _FROM_DOC.fullmatch(v.strip())
        if m:
            return self.doc(int(m.group(1)))
        if "$(" in v or "`" in v:
            return ("opaque", f"the body is built at run time ({_short(v)})")
        m = _VAR.match(v)
        if m:
            name = m.group(1) or m.group(2)
            # A shell assignment, not a gh field (-f NAME=...) of the same name.
            sets = [a for a in re.finditer(r"(?:^|[\s;&|(])" + name + "=", self.text)
                    if not re.search(r"(?:-[fF]|--field|--raw-field)\s*\Z", self.text[:a.start() + 1])]
            fed = re.compile(r"""["']?\$\(\s*cat\s+(?:-\s+)?HEREDOC(\d+)\s*\)""").match(self.text, sets[0].end()) \
                if len(sets) == 1 else None
            use = re.search(r"\$\{?" + name + r"\b", self.text)
            # Only one assignment, and it comes before the body is used: a second could replace it.
            if m.end() == len(v) and fed and use and sets[0].end() <= use.start():
                return self.doc(int(fed.group(1)))
            return ("opaque", f"the body is built at run time ({_short(v)})")
        return ("text", v)

    def stdin(self, lo, hi):
        ks = [int(w[7:]) for w in self.s.w[lo:hi + 1] if re.fullmatch(r"HEREDOC\d+", w)]
        if len(ks) == 1:
            return self.doc(ks[0])
        return ("opaque", "the body comes from stdin and no heredoc on this command feeds it")

    def file(self, p, lo, hi):
        return self.stdin(lo, hi) if p == "-" else ("file", p)

    def segment(self, lo, hi, nested):
        s = self.s
        g = sw.cmd_index(s, lo, hi, GH, nested)
        if g is None or g + 1 > hi:
            return
        if s.w[g + 1] == "api":
            self.api(g, hi)
            return
        v = g + 2                          # -R/--repo may come before the verb
        while v <= hi and (self.wv(v) in ("-R", "--repo") or re.match(r"--repo=|-R.", self.wv(v))):
            v += 2 if self.wv(v) in ("-R", "--repo") else 1
        verb = _VERBS.get((s.w[g + 1], self.wv(v))) if v <= hi else None
        if verb is None:
            return
        bodies, i = [], v + 1
        while i <= hi:
            t, live = self.wv(i), s.live[i]
            if verb == "c":                 # close / reopen: only --comment/-c posts text
                if t in ("--comment", "-c") and i < hi:
                    i += 1
                    bodies.append(self.val(self.wv(i), s.live[i]))
                elif t.startswith("--comment="):
                    bodies.append(self.val(t[10:], live))
                elif re.match(r"-c.", t):
                    bodies.append(self.val(t[2:], live))
            elif t in ("--body", "-b") and i < hi:
                i += 1
                bodies.append(self.val(self.wv(i), s.live[i]))
            elif t in ("--body-file", "-F") and i < hi:
                i += 1
                bodies.append(self.file(self.wv(i), lo, hi))
            elif t.startswith("--body="):
                bodies.append(self.val(t[7:], live))
            elif t.startswith("--body-file="):
                bodies.append(self.file(t[12:], lo, hi))
            elif re.match(r"-b.", t):
                bodies.append(self.val(t[2:], live))
            elif re.match(r"-F.", t):
                bodies.append(self.file(t[2:], lo, hi))
            elif t.startswith("--body"):
                bodies.append(("opaque", f"the flag `{_short(t)}` carries the body in a shape this hook does not read"))
            i += 1
        if bodies:
            self.posts.append(bodies)

    def api(self, g, hi):
        s = self.s
        path, method, fields, inp, i = "", "", [], None, g + 2
        while i <= hi:
            t = self.wv(i)
            if t in ("-X", "--method") and i < hi:
                i += 1
                method = s.w[i].upper()
            elif t.startswith("--method="):
                method = t[9:].upper()
            elif re.match(r"-X.", t):
                method = t[2:].upper()
            elif t in ("-f", "-F", "--field", "--raw-field") and i < hi:
                i += 1
                fields.append(self.field(self.wv(i), s.live[i], t in ("-F", "--field"), g, hi))
            elif re.match(r"-[fF].", t):
                fields.append(self.field(t[2:], s.live[i], t[1] == "F", g, hi))
            elif re.match(r"--(?:field|raw-field)=", t):
                fields.append(self.field(t.split("=", 1)[1], s.live[i], t.startswith("--field="), g, hi))
            elif t == "--input" and i < hi:
                i += 1
                inp = self.file(self.wv(i), g, hi)
            elif t.startswith("--input="):
                inp = self.file(t[8:], g, hi)
            elif t in _SKIP_VALUE:
                i += 1
            elif not t.startswith("-") and path == "":
                path = t
            i += 1
        p = re.sub(r"^/+", "", re.sub(r"^https?://[^/]+/", "", path, count=1), count=1)
        p = re.split(r"[?#]", p, maxsplit=1)[0]
        if p == "graphql":
            query = next((src for key, src in fields if key == "query"), None)
            if query is not None or inp is not None:
                self.posts.append([("graphql", query, dict(fields), inp)])
            return
        if not _COMMENTS.search(p) or method in ("GET", "HEAD") or (not fields and inp is None):
            return
        bodies = [src for key, src in fields if key == "body" or key.endswith("[body]")]
        if inp is not None:
            bodies.append(("json", inp))
        if bodies:
            self.posts.append(bodies)

    def field(self, v, live, typed, lo, hi):
        key, _, v = v.partition("=")
        if typed and v.startswith("@"):
            return key, self.file(v[1:], lo, hi)
        return key, self.val(v, live)


def _json_bodies(v):
    """Every string under a "body" key in v, depth first."""
    if isinstance(v, dict):
        return [s for k, x in v.items() for s in ([x] if k == "body" and isinstance(x, str) else _json_bodies(x))]
    if isinstance(v, list):
        return [s for x in v for s in _json_bodies(x)]
    return []


def _graphql_string(t):
    """The GraphQL string literal or block string opening t, decoded, or None."""
    if t.startswith('"""'):
        e = t.find('"""', 3)
        return t[3:e] if e >= 0 else None
    m = re.match(r'"((?:[^"\\\n]|\\.)*)"', t)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def check(payload, env):
    tool = payload.get("tool_name")
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or "gh" not in cmd:
            return None
        r = _Read(cmd)
        posts = r.posts
    elif isinstance(tool, str) and _MCP_TOOL.match(tool):
        r, posts = None, [[("text", b) for b in _json_bodies(ti)]]
    else:
        return None
    if not any(posts):
        return None
    sid = payload.get("session_id")
    hexid = sid[:8] if isinstance(sid, str) and re.fullmatch(r"[0-9a-f]{8}", sid[:8]) else None
    example = _EXAMPLE.format(hex=hexid or "<first 8 hex of the session id>")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = yield Need("cwd")
    home = env.get("HOME") or ""
    files = {}

    def resolve(p):
        p = _HOME.sub(home, p, count=1) if home and _HOME.match(p) else p
        if "$" in p or "`" in p or p.startswith("~"):
            return None
        if p.startswith("/"):
            return os.path.normpath(p)
        return os.path.normpath(os.path.join(cwd, p)) if cwd and not r.cd else None

    def text(src):
        """The body src holds, as a generator yielding Needs; raises _Unread."""
        kind = src[0]
        if kind == "text":
            return src[1]
        if kind == "doc":
            return r.docs[src[1]]
        if kind == "opaque":
            raise _Unread(f"{src[1]}, so its signature cannot be checked before it is posted. Write it literally, "
                          "in a heredoc in the same command, or in a file and pass --body-file <path>.")
        if kind == "json":
            return (yield from text(src[1]))
        p = src[1]
        f = resolve(p)
        hit = [q for q in r.written if resolve(q) == f] if f else []
        if f and len(hit) == 1 and r.written[hit[0]] == 1 and hit[0] in r.fed:
            return r.docs[r.fed[hit[0]]]
        why = None
        if f is None:
            why = f"{p} is not a path this hook can resolve (a $VAR, or a relative path after a cd)"
        elif hit:
            why = f"{p} is written by this same command, not from a heredoc"
        else:
            if f not in files:
                try:
                    files[f] = yield Need("read", f)
                except Exception:  # noqa: BLE001
                    files[f] = None
            if files[f] is None:
                why = f"{p} cannot be read"
        if why:
            raise _Unread(f"the body file {why}, so its signature cannot be checked before it is posted. Spell "
                          "out the path, or write the file from a heredoc in this same command (cat > PATH <<'EOF' "
                          "... EOF), or put the body in a heredoc and pass --body-file -.")
        return files[f]

    def bodies(src):
        """The bodies src posts: a JSON payload may hold several, a graphql query none."""
        if src[0] == "json":
            raw = yield from text(src[1])
            try:
                return _json_bodies(json.loads(raw))
            except ValueError:
                raise _Unread("the --input payload is not JSON this hook can read, so its signature cannot be "
                              "checked. Write the JSON literally in a heredoc fed to --input -.") from None
        if src[0] != "graphql":
            return [(yield from text(src))]
        _, qsrc, fields, inp = src
        variables = {}
        if inp is not None:
            raw = yield from text(inp)
            try:
                obj = json.loads(raw)
            except ValueError:
                obj = None
            if not isinstance(obj, dict):
                raise _Unread("the --input payload is not JSON this hook can read, so its signature cannot be "
                              "checked. Write the JSON literally in a heredoc fed to --input -.")
            query = obj.get("query") if qsrc is None else None
            variables = obj.get("variables") if isinstance(obj.get("variables"), dict) else {}
        if qsrc is not None:
            try:
                query = yield from text(qsrc)
            except _Unread:
                # Not known to post, unless a field or payload travels with it: one may be the body.
                if inp is None and not any(k != "query" for k in fields):
                    return []
                raise
        if not isinstance(query, str) or not _MUTATION.search(query):
            return []
        out = []
        for m in re.finditer(r"\b(body|input)\s*:\s*", query):
            rest = query[m.end():]
            if m.group(1) == "input" and not rest.startswith("$"):
                continue
            if not rest.startswith("$"):
                s = _graphql_string(rest)
                if s is None:
                    raise _Unread("the graphql body is not a string literal this hook can read, so its signature "
                                  "cannot be checked. Pass it as a variable (-f body=..., or from a heredoc).")
                out.append(s)
                continue
            name = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", rest)
            name = name.group(1) if name else ""
            if name in variables:
                v = variables[name]
                out += [v] if isinstance(v, str) else _json_bodies(v)
            elif name in fields and m.group(1) == "body":
                out.append((yield from text(fields[name])))
            else:
                raise _Unread(f"the graphql {m.group(1)} comes from ${name}, which this hook cannot read, so its "
                              "signature cannot be checked. Pass the body as its own variable, -f body=... or "
                              "from a heredoc in the same command.")
        return out

    problems = []
    for post in posts:
        for src in post:
            try:
                got = yield from bodies(src)
            except _Unread as e:
                return deny(f"{NAME}: {e}\n\nA signed body:\n\n{example}")
            for body in got:
                if not body.strip():
                    continue           # nothing posted as text: gh refuses it, or a review posts no comment
                lines = body.split("\n")
                last = ([ln.rstrip() for ln in lines if ln.strip()] or [""])[-1]
                if not lines[0].startswith(FIRST):
                    problems.append(f"the first line does not start with `{FIRST}`: `{_short(lines[0])}`")
                sig = SIGNATURE.fullmatch(last)
                if not sig:
                    problems.append(f"the last line is not the signature: `{_short(last)}`")
                elif hexid and sig.group(1) != hexid:
                    problems.append(f"the last line's hex is not this session's ({hexid}): `{_short(last)}`")
    if not problems:
        return None
    return deny(f"{NAME}: this posts a GitHub comment under the user's login, so it must be signed as an agent's, "
                f"or a reader takes it for the user's own words. Here {'; '.join(problems)}. Start the first line "
                f"with `{FIRST}` and end with the line `🤖 <model id> · <low|medium|high|xhigh|max|-> · <first 8 "
                f"hex of the session id>`:\n\n{example}")
