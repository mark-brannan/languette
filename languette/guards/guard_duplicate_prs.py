"""guard-duplicate-prs: a second open PR on an issue an open PR already
references is denied. The spec is features/guard-duplicate-prs.feature.

Two sessions working one issue each open a PR for it, minutes apart, and
neither reads the issue first: the work is done twice and the review is
split. So the check sits at the moment the second PR is opened.

Fires on `gh pr create|new` (the body from -b/--body, -F/--body-file <path>,
or `--body-file -` fed by a heredoc in the command), `gh api` writing to
repos/o/r/pulls (a `body` field, or `body=@<path>`), and the MCP tool
create_pull_request (its `body`). `--fill` or no body has nothing to judge.
A `gh api --input` payload is not read.

Every closing reference in the body (close, closes, closed, fix, fixes,
fixed, resolve, resolves, resolved; an optional colon; then `#N`,
`owner/repo#N` or an issue URL) is looked up in the issue's timeline. A
`cross-referenced` event whose source is an open pull request is an open PR
already on that issue: deny, naming both, unless this body says
`Supersedes` or `Replaces` that PR, in the same reference forms. The repo of
a bare `#N` is --repo/-R, GH_REPO=, or the MCP owner/repo; failing those,
the origin of the cwd, unless the command runs a `cd`.

GitHub that cannot answer (gh missing, signed out, offline, an error), a
timeline page filled with no open PR on it (an older one may sit past it),
or a repo that cannot be told asks, as the other guards that ask GitHub do. A
body the guard cannot read (built at run time, a file it cannot open or
past MAX_READ, stdin with no heredoc) is a deny that says why.
"""

import os
import re

from languette import scan as sw
from languette.guards.guard_private_terms import norm_repo, writes
from languette.verdict import Need, Refuse, ask, deny

NAME = "guard-duplicate-prs"
# The tools hooks.json wires this guard to; the MCP one by its name's tail.
TOOLS = re.compile(r"(?:Bash|mcp__.*__(?:create_pull_request))\Z")
_MCP = re.compile(r"mcp__.*__create_pull_request\Z")
GH = re.compile(r"(?:^|/)gh\Z")
MAX_READ = 1 << 20
PAGE = 100                                     # timeline events per lookup; one page is read
_CREATE = frozenset("create new".split())
# gh pr create's flags that take a value, so the value is never read as a flag.
_VALUED = frozenset("-a --assignee -B --base -H --head -l --label -m --milestone -p --project -r --reviewer "
                    "-T --template -t --title --recover".split())
_API_VALUED = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
_NAME = r"[A-Za-z0-9_.-]+"
_REF = (rf"(?:(?P<repo>{_NAME}/{_NAME})?#(?P<num>[0-9]+)"
        rf"|https?://github\.com/(?P<urepo>{_NAME}/{_NAME})/issues/(?P<unum>[0-9]+))(?![A-Za-z0-9_/])")
CLOSES = re.compile(rf"(?<![A-Za-z0-9_-])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?:[ \t]*:[ \t]*|[ \t]+){_REF}",
                    re.IGNORECASE)
SUPERSEDES = re.compile(rf"(?<![A-Za-z0-9_-])(?:supersedes|replaces)(?:[ \t]*:[ \t]*|[ \t]+){_REF}", re.IGNORECASE)
_GITHUB = re.compile(rf"github\.com(?::\d+)?[:/]+({_NAME})/({_NAME}?)(?:\.git)?/?\Z", re.IGNORECASE)
_HTML = re.compile(rf"github\.com/({_NAME}/{_NAME})/(?:pull|issues)/[0-9]+")


def _deny(why):
    return deny(f"{NAME}: {why}")


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def refs(rx, text, repo):
    """[(owner/name, N)] for each reference `rx` finds in `text`, in order; a
    bare #N is on `repo` (None when unknown)."""
    out = []
    for m in rx.finditer(text):
        r = m.group("repo") or m.group("urepo")
        r = norm_repo(r) if r else repo
        n = int(m.group("num") or m.group("unum"))
        if (r, n) not in out:
            out.append((r, n))
    return out


class _Post:
    """One PR a command opens: its repo as written (None = the cwd's), and its
    body as parts, (kind, value): text, file (a path), stdin, opaque."""

    def __init__(self, repo=None):
        self.repo, self.parts = repo, []


def _value(post, v, live):
    """A body value: text, or opaque when built at run time and no heredoc on
    the value itself feeds it."""
    if not live:
        post.parts.append(("text", v))
    elif "<<" in v or "HEREDOC" in v:
        post.parts.append(("stdin", v))        # $(cat <<EOF ...): the heredoc is the text
    else:
        post.parts.append(("opaque", v))


def _file(post, v, live):
    if live:
        post.parts.append(("opaque", v))
    elif v == "-":
        post.parts.append(("stdin", v))
    else:
        post.parts.append(("file", v))


def _pr_create(s, g, hi, repo):
    post = _Post(repo)
    i = g + 3
    while i <= hi:
        t, live = _wv(s, i), s.live[i]
        if t in ("-R", "--repo"):
            if i < hi:
                i += 1
                post.repo = _wv(s, i)
        elif t.startswith("--repo="):
            post.repo = t[7:]
        elif t.startswith("-R") and len(t) > 2:
            post.repo = t[2:]
        elif t in ("-b", "--body"):
            if i < hi:
                i += 1
                _value(post, _wv(s, i), s.live[i])
        elif t.startswith("--body="):
            _value(post, t[7:], live)
        elif t.startswith("-b") and len(t) > 2:
            _value(post, t[2:], live)
        elif t in ("-F", "--body-file"):
            if i < hi:
                i += 1
                _file(post, _wv(s, i), s.live[i])
        elif t.startswith("--body-file="):
            _file(post, t[12:], live)
        elif t.startswith("-F") and len(t) > 2:
            _file(post, t[2:], live)
        elif t in _VALUED:
            i += 1
        i += 1
    return post


def _api(s, g, hi):
    path, method, post = "", "", _Post()
    fields = False
    i = g + 2
    while i <= hi:
        t, live = _wv(s, i), s.live[i]
        if t in ("-X", "--method"):
            if i < hi:
                i += 1
                method = _wv(s, i).upper()
        elif t.startswith("--method="):
            method = t[9:].upper()
        elif t.startswith("-X") and len(t) > 2:
            method = t[2:].upper()
        elif t in ("-f", "-F", "--field", "--raw-field") or re.match(r"-[fF].|--(?:field|raw-field)=", t):
            fields = True
            if t in ("-f", "-F", "--field", "--raw-field"):
                if i >= hi:
                    break
                i += 1
                kv, live = _wv(s, i), s.live[i]
            else:
                kv = t.split("=", 1)[1] if t.startswith("--") else t[2:]
            key, _, v = kv.partition("=")
            if key == "body":
                if v.startswith("@") and not t.startswith(("-f", "--raw-field")):
                    _file(post, v[1:], live)
                else:
                    _value(post, v, live)
        elif t == "--input" or t.startswith("--input="):
            fields = True
            if t == "--input":
                i += 1
        elif t in _API_VALUED:
            i += 1
        elif not t.startswith("-") and path == "":
            path = t
        i += 1
    p = re.sub(r"^/+", "", re.sub(r"^https?://[^/]+/", "", path, count=1), count=1)
    m = re.fullmatch(rf"repos/({_NAME}|\{{owner\}})/({_NAME}|\{{repo\}})/pulls/?", p)
    if not m or method in ("GET", "HEAD") or (method == "" and not fields):
        return None
    # gh fills {owner}/{repo} from the cwd's repo: None sends _slug to git.
    post.repo = None if "{" in m.group(1) + m.group(2) else f"{m.group(1)}/{m.group(2)}"
    return post


def posts(command):
    """(posts, cd, heredocs): each PR the command opens, whether it runs a cd,
    and its heredoc bodies with whether any is built at run time."""
    buf = command + "\n"
    out, cd = [], False
    for text, nested in sw.texts_of(sw.strip_heredocs(buf)):
        s = sw.Scan(text)
        if any(s.k[i] == "w" and s.w[i] in ("cd", "pushd", "popd") for i in range(len(s.w))):
            cd = True
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, GH, nested)
            if g is None or g + 2 > b:
                continue
            repo = next((s.w[i][8:] for i in range(a, g) if s.k[i] == "w" and s.w[i].startswith("GH_REPO=")), None)
            if s.w[g + 1] == "pr" and s.w[g + 2] in _CREATE:
                out.append(_pr_create(s, g, b, repo))
            elif s.w[g + 1] == "api":
                p = _api(s, g, b)
                if p:
                    out.append(p)
    return out, cd, sw.heredocs(buf)


def _fetch(p):
    """The text of the file `p`, as the runner reads it, or the Refuse it comes to."""
    try:
        return (yield Need("read", p, MAX_READ))
    except UnicodeDecodeError as e:
        return Refuse(f"cannot be read ({e})")
    except OSError as e:
        return Refuse(f"cannot be read ({e.strerror or e})")
    except ValueError as e:                    # not a regular file, or past MAX_READ
        return Refuse(str(e))


def _body(post, cwd, cd, docs, fed, env):
    """The text of the body `post` sends, or the deny that says why it cannot be read."""
    text = ""
    for kind, v in post.parts:
        if kind == "text":
            text += v + "\n"
        elif kind == "opaque":
            return _deny(f"the body is built at run time ({v}) and no heredoc in this command feeds it, so its "
                         "text cannot be checked for an issue it closes. Write it literally, in a heredoc in the "
                         "same command, or in a file and pass --body-file <path>.")
        elif kind == "stdin":
            if not docs:
                return _deny("the body comes from stdin (--body-file -) and there is no heredoc in the command, so "
                             "it cannot be checked. Put the text in a heredoc in the same command, or in a file and "
                             "pass --body-file <path>.")
            text += "".join(body + "\n" for body, _ in docs)
        elif v in fed:                         # this command writes it from a heredoc: that text, not the file's
            text += "".join(body + "\n" for body, _ in docs)
        else:
            p = v
            if p == "~" or p.startswith("~/"):
                p = (env.get("HOME") or "") + p[1:] if env.get("HOME") else None
            elif not os.path.isabs(p):
                p = os.path.join(cwd, p) if cwd and not cd else None
            got = Refuse("is a relative path after a cd, and the guard cannot tell where the command stands") \
                if p is None else (yield from _fetch(p))
            if isinstance(got, Refuse):
                return _deny(f"--body-file {v} {got}, so the body cannot be checked for an issue it closes. Write "
                             "it to that path from a heredoc in this same command, or create the file in an "
                             "earlier command and retry; spell the path out, since a variable set in an earlier "
                             "command is invisible here.")
            text += got + "\n"
    return text


def _slug(repo, cd, cwd):
    """owner/name of the repo a bare #N is on, or None."""
    if repo:
        r = norm_repo(repo)
        return r if re.fullmatch(rf"{_NAME}/{_NAME}", r) else None
    if cd or not cwd:
        return None
    url = yield Need("git", "git", cwd, "remote", "get-url", "origin")
    m = _GITHUB.search(url or "")
    return norm_repo(f"{m.group(1)}/{m.group(2)}") if m else None


def _open_prs(slug, n):
    """[(owner/name, M, title)] of the open PRs cross-referenced on issue n,
    or None when GitHub can't answer, or fills the page with none: an older
    one may sit past it."""
    code, body = yield Need("gh-api", f"repos/{slug}/issues/{n}/timeline?per_page={PAGE}")
    if code != 200 or not isinstance(body, list):
        return None
    out = []
    for e in body:
        src = e.get("source") if isinstance(e, dict) and e.get("event") == "cross-referenced" else None
        iss = src.get("issue") if isinstance(src, dict) else None
        if not (isinstance(iss, dict) and iss.get("pull_request") and iss.get("state") == "open"
                and isinstance(iss.get("number"), int)):
            continue
        r = iss.get("repository")
        r = r.get("full_name") if isinstance(r, dict) else None
        if not isinstance(r, str):
            m = _HTML.search(str(iss.get("html_url") or ""))
            r = m.group(1) if m else slug
        pr = (norm_repo(r), iss["number"], str(iss.get("title") or ""))
        if pr[:2] not in [p[:2] for p in out]:
            out.append(pr)
    return out if out or len(body) < PAGE else None


def _judge(text, slug):
    """deny or ask for one body, or None."""
    closes = refs(CLOSES, text, slug)
    if not closes:
        return None
    gone = refs(SUPERSEDES, text, slug)
    asked = None
    for repo, n in closes:
        if repo is None:
            asked = asked or ask(f"{NAME}: this PR would close #{n}, and the hook can't tell which repo it is opened "
                                 "on (no --repo, and the working directory's origin is not on github.com, or a cd "
                                 f"moves it), so it can't check whether an open PR already references #{n}. Pass "
                                 "--repo owner/name, or read the issue first.")
            continue
        prs = yield from _open_prs(repo, n)
        if prs is None:
            asked = asked or ask(f"{NAME}: this PR would close {repo}#{n}, and GitHub couldn't say whether an open PR "
                                 "already references it (gh missing, signed out, offline, an error, or a "
                                 f"timeline past {PAGE} events):\n"
                                 f"  gh api repos/{repo}/issues/{n}/timeline\n"
                                 "Read the issue before opening a second PR on it.")
            continue
        for pr_repo, m, title in prs:
            if (pr_repo, m) in gone:
                continue
            here = lambda r, x: f"#{x}" if r == repo else f"{r}#{x}"
            named = here(pr_repo, m) + (f" ({title})" if title else "")
            return _deny(f"PR {named} is open and already references {here(repo, n)}, which this PR would close "
                         "too, so this command is blocked. If this PR replaces it, close "
                         f"{here(pr_repo, m)} first or say `Supersedes {here(pr_repo, m)}` in this body. If both "
                         "are wanted, drop the closing keyword here and link the issue in prose.")
    return asked


def check(payload, env):
    tool = payload.get("tool_name")
    if not isinstance(tool, str):
        return None
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    cwd = payload.get("cwd")
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or ("gh" not in cmd):
            return None
        found, cd, docs = posts(cmd.rstrip("\n"))
        fed = set(writes(cmd + "\n", True))
    elif _MCP.match(tool):
        body, owner, repo = ti.get("body"), ti.get("owner"), ti.get("repo")
        post = _Post(f"{owner}/{repo}" if isinstance(owner, str) and owner and isinstance(repo, str) and repo
                     else None)
        if isinstance(body, str):
            post.parts.append(("text", body))
        found, cd, docs, fed = [post], False, [], set()
    else:
        return None
    if not any(p.parts for p in found):
        return None
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        cwd = yield Need("cwd")
    asked = None
    for post in found:
        if not post.parts:
            continue
        text = yield from _body(post, cwd, cd, docs, fed, env)
        if isinstance(text, dict):
            return text
        if not CLOSES.search(text):
            continue
        slug = yield from _slug(post.repo, cd, cwd)
        v = yield from _judge(text, slug)
        if v and v["permissionDecision"] == "deny":
            return v
        asked = asked or v
    return asked
