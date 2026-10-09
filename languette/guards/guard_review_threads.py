"""guard-review-threads: a review bot's thread is resolved only on a fix or a
record. The spec is features/guard-review-threads.feature.

A Bash call that resolves a review thread (`gh api graphql` whose query, in
its fields, in a file a field or --input names, or in a heredoc fed to
--input, holds a resolveReviewThread mutation) names each thread by its
PRRT_ id. The guard reads every such thread from GitHub, through `gh api
graphql`, and denies unless the current gh login replied after the bot's last
comment, and that reply names a commit or a link. It checks that a record is
named, not that the commit exists. A thread no bot commented on passes. A
query that opens with `{` or `query` is a read whatever it holds, since
GraphQL runs no mutation from it. A `gh api graphql` whose query it cannot
read otherwise (a run-time word, a file it cannot open or another command
could rewrite, stdin with no heredoc), an id it cannot read, or a `gh api`
whose endpoint is built at run time and could be graphql, is a deny that says
so; GitHub that cannot answer is an ask. Only gh is read: a POST to the
GraphQL endpoint by another client (curl, a script) is not.
"""

import json
import re

from languette import paths
from languette import scan as sw
from languette.guards.guard_bypass_labels import _alone
from languette.verdict import Need, ask, deny

NAME = "guard-review-threads"
GH = re.compile(r"(?:^|/)gh\Z")
RESOLVE = re.compile(r"(?<![A-Za-z0-9_])resolveReviewThread(?![A-Za-z0-9_])")
THREAD = re.compile(r"PRRT_[A-Za-z0-9_-]+")
BOTS = frozenset("coderabbitai claude copilot-pull-request-reviewer github-actions".split())
SHA = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])", re.I)
LINK = re.compile(r"https://\S+|(?<![\w./-])[\w.-]+/[\w.-]+#[0-9]+\b")
GRAPHQL = re.compile(r"(?:https?://[^/]+)?/*(?:api/(?:v3/)?)?graphql")
VAR = re.compile(r"\$(?:\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])|\$\([^)]*\)|`[^`]*`")
# A query GraphQL can only run as a read: the shorthand `{` must be the lone
# operation, and a named `query` takes a second operation only by operationName.
READ = re.compile(r"\s*(?:\{|query(?![A-Za-z0-9_]))")
FLAGS = {"-f": False, "-F": True, "--field": True, "--raw-field": False}   # flag -> reads @file
TIMEOUT = 10
# The last 100 comments: the bot's last word and every reply after it.
QUERY = ("query($id: ID!) { viewer { login } node(id: $id) { ... on PullRequestReviewThread { "
         "comments(last: 100) { nodes { author { login __typename } body createdAt } } } } }")
DO = ("Reply on the thread with the fix commit, or with a link to the ruling, decision record or issue the "
      "dismissal rests on, then resolve it. A dismissal with nothing behind it leaves the thread open for a person.")


def _maybe_graphql(word):
    """A word built at run time could spell the graphql endpoint: the literal
    text before its first expansion starts some spelling of it, and the text
    after its last could end one."""
    pieces = VAR.split(re.sub(r"[\"']", "", word))
    if len(pieces) < 2:
        return False
    head, tail = pieces[0], pieces[-1]
    ends = tail.rsplit("/", 1)[-1] == "graphql" if "/" in tail else "graphql".endswith(tail)
    starts = (any(head.startswith(p) or p.startswith(head) for p in ("http://", "https://"))
              or any(p.startswith(head.lstrip("/")) for p in ("graphql", "api/graphql", "api/v3/graphql")))
    return ends and starts


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def _decoded(body):
    """A text, and, when it is JSON, its decoded text too: a \\u escape can
    spell the mutation's name."""
    try:
        return body + "\n" + json.dumps(json.loads(body), ensure_ascii=False)
    except ValueError:
        return body


def _args(s, g, b):
    """gh's words in g..b as (fields, inputs, words): fields are (reads @file,
    name, value, live); inputs are (source, live)."""
    fields, inputs, words = [], [], []
    idx = [i for i in range(g + 1, b + 1) if s.k[i] in ("w", "q")]
    j = 0
    while j < len(idx):
        i = idx[j]
        t = _wv(s, i)
        words.append(t)
        nxt = (_wv(s, idx[j + 1]), s.live[idx[j + 1]]) if j + 1 < len(idx) else ("", False)
        kv = None
        if t in FLAGS:
            (kv, live), typed = nxt, FLAGS[t]
            words.append(kv)
            j += 1
        elif t[:2] in ("-f", "-F") and len(t) > 2:
            kv, live, typed = t[3:] if t[2:3] == "=" else t[2:], s.live[i], t[1] == "F"
        elif t.startswith(("--field=", "--raw-field=")):
            kv, live, typed = t.split("=", 1)[1], s.live[i], t.startswith("--field=")
        elif t == "--input":
            inputs.append(nxt)
            words.append(nxt[0])
            j += 1
        elif t.startswith("--input="):
            inputs.append((t[len("--input="):], s.live[i]))
        if kv is not None:
            name, _, value = kv.partition("=")
            fields.append((typed, name, value, live))
        j += 1
    return fields, inputs, words


def _calls(command, cwd, home):
    """One record per gh call that may reach the GraphQL endpoint and is not
    a plain read: its literal text, its query's text, the files it reads
    (the query's apart), and why it cannot be read, or None. The files are
    read by _resolves, through the runner."""
    buf = command + "\n"
    hd = "\n".join(_decoded(b) for b in sw.heredoc_bodies(buf))
    scans = [(sw.Scan(t), nested) for t, nested in sw.texts_of(sw.strip_heredocs(buf))]
    alone, moved = _alone(scans), paths.moves_directory(scans)
    out = []
    for s, nested in scans:
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, GH, nested) if a <= b else None
            if g is None:
                continue
            fields, inputs, words = _args(s, g, b)
            live_at = [i for i in range(g + 1, b + 1) if s.k[i] in ("w", "q") and s.live[i]]
            first = next((i for i in range(g + 1, b + 1) if s.k[i] in ("w", "q")), None)
            if "api" not in words and first not in live_at:
                continue
            if not any(GRAPHQL.fullmatch(w) for w in words):
                if any(_maybe_graphql(_wv(s, i)) for i in live_at):
                    out.append({"why": "the endpoint is built at run time"})
                continue
            rec = {"text": "\n".join(words), "qfiles": [], "files": [], "stdin": False, "live": bool(live_at),
                   "why": None}

            def file(p, key):
                if p == "-":
                    rec["stdin"] = True
                    return
                try:
                    ok = alone and (p.startswith("/") or bool(home if p.startswith("~") else cwd))
                    rec[key].append(paths.resolve(p, False, cwd, home, moved) if ok else None)
                except paths.Unresolved:
                    rec[key].append(None)

            query = [f for f in fields if f[1] == "query"]
            if any(VAR.search(f[1]) for f in fields if f[3]):
                rec["why"] = "a field's name is built at run time"
            elif any(live and not (READ.match(v) and not any(f[1] == "operationName" for f in fields))
                     for _, _, v, live in query):
                rec["why"] = "the query is built at run time"
            elif query and not inputs and all(live for *_, live in query):
                continue                                   # a read whose values are filled at run time
            for typed, name, value, live in fields:
                if typed and value.startswith("@"):
                    file(value[1:], "qfiles" if name == "query" else "files")
            for src, live in inputs:
                if live:
                    rec["why"] = rec["why"] or "the --input path is built at run time"
                else:
                    file(src, "qfiles")
            if rec["stdin"] and "HEREDOC" not in words:     # scan's mark for a heredoc fed to gh
                rec["why"] = rec["why"] or "stdin feeds it and no heredoc of its own does"
            rec["query"] = "\n".join(v for _, _, v, _ in query) + ("\n" + hd if rec["stdin"] else "")
            rec["text"] += "\n" + rec["query"]
            out.append(rec)
    return out


def _read(p):
    """A file's text, decoded too when it is JSON, or None when it cannot be read."""
    if p is None or not (yield Need("path", "isfile", p)):
        return None
    try:
        return _decoded((yield Need("read", p)))
    except Exception:  # noqa: BLE001 -- unreadable or not text: the caller denies
        return None


def _resolves(command, cwd, home=""):
    """(thread ids, why): the PRRT_ ids each resolving gh call in `command`
    names, in order, and why one of them cannot be read, or None."""
    ids = []
    for rec in _calls(command, cwd, home):
        if rec["why"]:
            return ids, rec["why"]
        text, query = rec["text"], rec["query"]
        for p in rec["qfiles"]:
            got = yield from _read(p)
            if got is None:
                return ids, "it reads its query from a file the guard cannot open, or that another command in the call could rewrite"
            query += "\n" + got
        if not RESOLVE.search(query):         # only the query can hold the mutation, not a reply's text
            continue
        text += "\n" + query
        for p in rec["files"]:
            got = yield from _read(p)
            if got is None:
                return ids, "a field reads a file the guard cannot open, or that another command in the call could rewrite"
            text += "\n" + got
        found = THREAD.findall(text)
        if not found or rec["live"]:
            return ids, "the thread id is built at run time or not in the command"
        ids += found
    return list(dict.fromkeys(ids)), None


def _norm(login):
    """A login as both APIs spell it: GraphQL gives an app's login without the
    `[bot]` that its token's viewer, and REST, may carry."""
    return re.sub(r"\[bot\]\Z", "", str(login or "")).casefold()


def _login(c):
    return _norm((c.get("author") or {}).get("login"))


def _bot(c):
    a = c.get("author") or {}
    return a.get("__typename") == "Bot" or str(a.get("login") or "").endswith("[bot]") or _login(c) in BOTS


def _judge(tid, viewer, comments):
    """deny for one thread, or None. The viewer's own comments are replies,
    even when the viewer is itself a bot."""
    me = _norm(viewer)
    bots = [i for i, c in enumerate(comments) if _bot(c) and _login(c) != me]
    if not bots:
        return None
    mine = [c for c in comments[bots[-1] + 1:] if _login(c) == me]
    if not mine:
        return deny(f"{NAME}: review thread {tid} has no reply from {viewer} after the bot's last comment, so "
                    f"resolving it would close a finding nobody answered. {DO}")
    if not any(SHA.search(str(c.get("body") or "")) or LINK.search(str(c.get("body") or "")) for c in mine):
        return deny(f"{NAME}: the reply on review thread {tid} after the bot's last comment names no commit and no "
                    f"link (a sha of 7 to 40 hex characters, an https:// URL, or owner/repo#n), so the dismissal "
                    f"rests on nothing. {DO}")
    return None


def _thread(cwd, tid):
    """(viewer login, comments), or a reason GitHub could not be read."""
    try:
        rc, out, err = yield Need("run", cwd, TIMEOUT, "gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"id={tid}")
    except Exception as e:  # noqa: BLE001 -- gh missing or hung: the reason is the ask
        return f"gh did not run ({type(e).__name__})"
    if rc != 0:
        return f"gh exited {rc}: {(err or out).strip()[:200]}"
    try:
        data = json.loads(out)["data"]
        viewer = data["viewer"]["login"]
        comments = data["node"]["comments"]["nodes"]
    except (ValueError, KeyError, TypeError):
        return "GitHub returned no review thread by that id"
    if not isinstance(viewer, str) or not isinstance(comments, list):
        return "GitHub returned no review thread by that id"
    return viewer, [c for c in comments if isinstance(c, dict)]


def check(payload, env=None):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str):
        return None
    cwd = payload.get("cwd")
    cwd = cwd if isinstance(cwd, str) and cwd.startswith("/") else ""
    ids, why = yield from _resolves(cmd, cwd, (env or {}).get("HOME") or "")
    if why:
        return deny(f"{NAME}: this graphql call may resolve a review thread, and the guard cannot tell which review "
                    f"thread ({why}), so it cannot check that a bot's finding was answered. Put the query and any "
                    "thread's PRRT_ id in the command literally, pass run-time values as GraphQL variables "
                    "(-f name=value), or run gh alone with an absolute path to the query file. " + DO)
    if ids and not cwd:
        cwd = yield Need("cwd")
    for tid in ids:
        got = yield from _thread(cwd, tid)
        if isinstance(got, str):
            return ask(f"{NAME}: this resolves review thread {tid}, and GitHub could not be read to check that a "
                       f"bot's finding on it was answered ({got}). Approve only if the thread was answered with "
                       "the fix commit or a link to the record the dismissal rests on.")
        v = _judge(tid, *got)
        if v:
            return v
    return None
