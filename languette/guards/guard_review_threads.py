"""guard-review-threads: a review bot's thread is resolved only on a fix or a
record. The spec is features/guard-review-threads.feature.

A Bash call that resolves a review thread (`gh api graphql` whose query, in
its fields or in a heredoc fed to --input, holds a resolveReviewThread
mutation) names each thread by its PRRT_ id. The guard reads every such
thread from GitHub, through `gh api graphql`, and denies unless the current
gh login replied after the bot's last comment, and that reply names a commit
or a link. It checks that a record is named, not that the commit exists. A
thread no bot commented on passes. A `gh api graphql` whose query it cannot
read (a run-time word, a file, stdin with no heredoc), an id it cannot read,
or GitHub that cannot answer, is a deny that says so.
"""

import json
import re

from languette import scan as sw
from languette.verdict import Need, deny

NAME = "guard-review-threads"
GH = re.compile(r"(?:^|/)gh\Z")
RESOLVE = re.compile(r"(?<![A-Za-z0-9_])resolveReviewThread(?![A-Za-z0-9_])")
THREAD = re.compile(r"PRRT_[A-Za-z0-9_-]+")
BOTS = frozenset("coderabbitai claude copilot-pull-request-reviewer github-actions".split())
SHA = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![0-9A-Za-z])", re.I)
LINK = re.compile(r"https://\S+|(?<![\w./-])[\w.-]+/[\w.-]+#[0-9]+\b")
GRAPHQL = re.compile(r"(?:https?://[^/]+)?/*(?:api/v3/)?graphql")
QUERY_FIELD = re.compile(r"(?:-[fF]|--(?:raw-)?field=)?query=")
TIMEOUT = 10
# The last 100 comments: the bot's last word and every reply after it.
QUERY = ("query($id: ID!) { viewer { login } node(id: $id) { ... on PullRequestReviewThread { "
         "comments(last: 100) { nodes { author { login __typename } body createdAt } } } } }")
DO = ("Reply on the thread with the fix commit, or with a link to the ruling, decision record or issue the "
      "dismissal rests on, then resolve it. A dismissal with nothing behind it leaves the thread open for a person.")


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def _input(words):
    """The --input value among gh's words ("-" is stdin), or None."""
    for j, w in enumerate(words):
        if w == "--input":
            return words[j + 1] if j + 1 < len(words) else ""
        if w.startswith("--input="):
            return w[len("--input="):]
    return None


def _resolves(command):
    """(thread ids, unreadable): the PRRT_ ids each resolving gh call in
    `command` names, in order; unreadable when one names none or builds a
    word at run time, or when any graphql call's query is out of sight (built
    at run time, read from a file, or stdin with no heredoc), since that
    query cannot be shown not to resolve a thread."""
    buf = command + "\n"
    hd = "\n".join(sw.heredoc_bodies(buf))
    ids, unreadable = [], False
    for text, nested in sw.texts_of(sw.strip_heredocs(buf)):
        s = sw.Scan(text)
        for a, b in s.segments():
            g = sw.cmd_index(s, a, b, GH, nested) if a <= b else None
            if g is None:
                continue
            words = [_wv(s, i) for i in range(g + 1, b + 1) if s.k[i] in ("w", "q")]
            if "api" not in words or not any(GRAPHQL.fullmatch(w) for w in words):
                continue
            src = _input(words)
            body = "\n".join(words) + ("\n" + hd if src == "-" else "")
            live = any(s.live[i] for i in range(g + 1, b + 1))
            query = [i for i in range(g + 1, b + 1) if s.k[i] in ("w", "q") and QUERY_FIELD.match(_wv(s, i))]
            if (any(s.live[i] or QUERY_FIELD.sub("", _wv(s, i)).startswith("@") for i in query)
                    or src is not None and (src != "-" or not hd)):
                unreadable = True
                continue
            if not RESOLVE.search(body):
                continue
            found = THREAD.findall(body)
            ids += found
            unreadable = unreadable or not found or live
    return list(dict.fromkeys(ids)), unreadable


def _bot(c):
    a = c.get("author") or {}
    login = str(a.get("login") or "")
    return a.get("__typename") == "Bot" or login.endswith("[bot]") or login.casefold() in BOTS


def _login(c):
    return str((c.get("author") or {}).get("login") or "")


def _judge(tid, viewer, comments):
    """deny for one thread, or None. The viewer's own comments are replies,
    even when the viewer is itself a bot."""
    bots = [i for i, c in enumerate(comments) if _bot(c) and _login(c).casefold() != viewer.casefold()]
    if not bots:
        return None
    mine = [c for c in comments[bots[-1] + 1:] if _login(c).casefold() == viewer.casefold()]
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
    except Exception as e:  # noqa: BLE001 -- gh missing or hung: the reason is the deny
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
    if not isinstance(cmd, str) or "graphql" not in cmd:
        return None
    ids, unreadable = _resolves(cmd)
    if unreadable:
        return deny(f"{NAME}: this graphql call may resolve a review thread, and the guard cannot tell which review "
                    "thread (the query or the id is built at run time, read from a file or stdin, or not in the "
                    "command), so it cannot check that a bot's finding was answered. Put the query and any thread's "
                    f"PRRT_ id in the command literally. {DO}")
    if not ids:
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        cwd = yield Need("cwd")
    for tid in ids:
        got = yield from _thread(cwd, tid)
        if isinstance(got, str):
            return deny(f"{NAME}: this resolves review thread {tid}, and GitHub could not be read to check that a "
                        f"bot's finding on it was answered ({got}). Resolve it once GitHub answers; until then "
                        "the thread stays open.")
        v = _judge(tid, *got)
        if v:
            return v
    return None
