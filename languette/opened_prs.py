"""guard-duplicate-prs' walk and its handler (languette/rules/guard_duplicate_prs.py is the
rule set): a second open PR on an issue an open PR already references is denied. The spec
is features/guard-duplicate-prs.feature.

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
the cwd's remote (the only one, else the one gh resolves), unless the command runs a `cd`.

On GitLab: `glab mr create|new` (the description from -d/--description or
--description-file, and -i/--related-issue N read as closing N) and `glab api`
writing to projects/:id/merge_requests (a `description` field). GitLab's
closing pattern adds implement and the -ing tenses, references a group/project#N
or an issue or work item URL, and each issue's related merge requests stand for
the timeline; `Supersedes` names a merge request as !M, group/project!M or its URL.
A -R that is no URL is on GITLAB_HOST's host, else gitlab.com.

GitHub that cannot answer (gh missing, signed out, offline, an error), a
timeline page filled with no open PR on it (an older one may sit past it),
or a repo that cannot be told asks, as the other guards that ask GitHub do. A
body the guard cannot read (built at run time, a file it cannot open or
past paths.MAX_READ, stdin with no heredoc) is a deny that says why.
"""

import os
import re
from urllib.parse import quote, unquote

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.refs import remote_url
from languette.verdict import Need, Refuse, ask, deny

# The tools hooks.json wires this guard to; the MCP one by its name's tail.
TOOLS = re.compile(r"(?:Bash|mcp__.*__(?:create_pull_request))\Z")
_MCP = re.compile(r"mcp__.*__create_pull_request\Z")
PAGE = 100                                     # timeline events per lookup; one page is read
_CREATE = frozenset("create new".split())
# gh pr create's flags that take a value, so the value is never read as a flag.
_VALUED = frozenset("-a --assignee -B --base -H --head -l --label -m --milestone -p --project -r --reviewer "
                    "-T --template -t --title --recover".split())
_NAME = r"[A-Za-z0-9_.-]+"
_REF = (rf"(?:(?P<repo>{_NAME}/{_NAME})?#(?P<num>[0-9]+)"
        rf"|https?://github\.com/(?P<urepo>{_NAME}/{_NAME})/issues/(?P<unum>[0-9]+))(?![A-Za-z0-9_/])")
CLOSES = re.compile(rf"(?<![A-Za-z0-9_-])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?:[ \t]*:[ \t]*|[ \t]+){_REF}",
                    re.IGNORECASE)
SUPERSEDES = re.compile(rf"(?<![A-Za-z0-9_-])(?:supersedes|replaces)(?:[ \t]*:[ \t]*|[ \t]+){_REF}", re.IGNORECASE)
_HTML = re.compile(rf"github\.com/({_NAME}/{_NAME})/(?:pull|issues)/[0-9]+")
# GitLab's closing pattern (docs/design/forges.md): close, fix, resolve or implement in any
# tense, then #N, group/project#N or an issue or work item URL; its MRs are !M.
_GL_NAME = rf"{_NAME}(?:/{_NAME})+"
_GL_REF = (rf"(?:(?P<repo>{_GL_NAME})?#(?P<num>[0-9]+)"
           rf"|https?://[^/\s]+/(?P<urepo>{_GL_NAME})/-/(?:issues|work_items)/(?P<unum>[0-9]+))(?![A-Za-z0-9_/])")
_GL_KEYS = r"(?:clos(?:e[sd]?|ing)|fix(?:e[sd]|ing)?|resolv(?:e[sd]?|ing)|implement(?:s|ed|ing)?)"
CLOSES_GL = re.compile(rf"(?<![A-Za-z0-9_-]){_GL_KEYS}(?:[ \t]*:[ \t]*|[ \t]+){_GL_REF}", re.IGNORECASE)
_GL_MR = (rf"(?:(?P<repo>{_GL_NAME})?!(?P<num>[0-9]+)"
          rf"|https?://[^/\s]+/(?P<urepo>{_GL_NAME})/-/merge_requests/(?P<unum>[0-9]+))(?![A-Za-z0-9_/])")
SUPERSEDES_GL = re.compile(rf"(?<![A-Za-z0-9_-])(?:supersedes|replaces)(?:[ \t]*:[ \t]*|[ \t]+){_GL_MR}",
                           re.IGNORECASE)
_GL_WEB = re.compile(rf"https?://[^/]+/({_GL_NAME})/-/merge_requests/[0-9]+")
# glab mr create's flags that take a value (-b is the target branch, never a body).
_GL_VALUED = frozenset("-a --assignee -H --head -l --label -m --milestone --reviewer -s --source-branch "
                       "-b --target-branch --template -t --title --attach".split())
_GL_PROJECT = re.compile(r"(?:api/v4/)?projects/([^/]+)/merge_requests")
# A path the command appends to: the file is its old text plus what is appended, never
# a heredoc's text alone. Over-matches a `>>` inside a heredoc body, which only costs a deny.
_APPEND = re.compile(r""">>[ \t]*(["']?)([^\s;|&<>"']+)\1""")


def _deny(guard, why):
    return deny(say("judged", guard=guard, why=why))


def refs(rx, text, repo):
    """[(owner/name, N)] for each reference `rx` finds in `text`, in order; a
    bare #N is on `repo` (None when unknown)."""
    out = []
    for m in rx.finditer(text):
        r = m.group("repo") or m.group("urepo")
        r = sw.norm_repo(r) if r else repo
        n = int(m.group("num") or m.group("unum"))
        if (r, n) not in out:
            out.append((r, n))
    return out


class _Post:
    """One PR a command opens: its repo as written (None = the cwd's), the forge
    it opens on (a scan.FORGES key), and its body as parts, (kind, value): text,
    file (a path), stdin, opaque."""

    def __init__(self, repo=None, forge="github"):
        self.repo, self.forge, self.parts = repo, forge, []


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
        t, live = sw.word(s, i), s.live[i]
        if r := sw.gh_repo_flag(s, i, hi, post.repo):
            post.repo, i = r
        elif t in ("-b", "--body"):
            if i < hi:
                i += 1
                _value(post, sw.word(s, i), s.live[i])
        elif t.startswith("--body="):
            _value(post, t[7:], live)
        elif t.startswith("-b") and len(t) > 2:
            _value(post, t[2:], live)
        elif t in ("-F", "--body-file"):
            if i < hi:
                i += 1
                _file(post, sw.word(s, i), s.live[i])
        elif t.startswith("--body-file="):
            _file(post, t[12:], live)
        elif t.startswith("-F") and len(t) > 2:
            _file(post, t[2:], live)
        elif t in _VALUED:
            i += 1
        i += 1
    return post


def _related(post, v, live):
    """-i/--related-issue N: the MR is for issue N, read as a body that closes it."""
    if not live and re.fullmatch(r"#?[0-9]+", v):
        post.parts.append(("text", f"Closes #{v.lstrip('#')}"))


def _mr_create(s, g, hi, repo):
    """`glab mr create|new`: the description from -d/--description or --description-file,
    and -i/--related-issue, an MR for that issue, read as closing it."""
    post = _Post(repo, "gitlab")
    i = g + 3
    while i <= hi:
        t, live = sw.word(s, i), s.live[i]
        if r := sw.gh_repo_flag(s, i, hi, post.repo):
            post.repo, i = r
        elif t in ("-d", "--description"):
            if i < hi:
                i += 1
                _value(post, sw.word(s, i), s.live[i])
        elif t.startswith("--description="):
            _value(post, t[14:], live)
        elif t.startswith("-d") and len(t) > 2:
            _value(post, t[2:], live)
        elif t == "--description-file":
            if i < hi:
                i += 1
                _file(post, sw.word(s, i), s.live[i])
        elif t.startswith("--description-file="):
            _file(post, t[19:], live)
        elif t in ("-i", "--related-issue"):
            if i < hi:
                i += 1
                _related(post, sw.word(s, i), s.live[i])
        elif t.startswith("--related-issue="):
            _related(post, t[16:], live)
        elif t.startswith("-i") and len(t) > 2:
            _related(post, t[2:], live)
        elif t in _GL_VALUED:
            i += 1
        i += 1
    return post


def _glab_api(s, g, hi):
    api, post = sw.gh_api(s, g + 2, hi, "glab"), _Post(forge="gitlab")
    for a in api.args:
        if a.key == "description":
            if a.value.startswith("@") and a.typed:
                _file(post, a.value[1:], a.live)
            else:
                _value(post, a.value, a.live)
    m = _GL_PROJECT.fullmatch(api.path)
    if not m or api.method in ("GET", "HEAD") or (api.method == "" and not api.sends):
        return None
    # glab fills :id from the cwd's project: None sends _slug to git.
    post.repo = None if m.group(1) == ":id" else unquote(m.group(1))
    return post


def _api(s, g, hi):
    api, post = sw.gh_api(s, g + 2, hi), _Post()
    for a in api.args:
        if a.key == "body":
            if a.value.startswith("@") and a.typed:
                _file(post, a.value[1:], a.live)
            else:
                _value(post, a.value, a.live)
    m = re.fullmatch(rf"repos/({_NAME}|\{{owner\}})/({_NAME}|\{{repo\}})/pulls", api.path)
    if not m or api.method in ("GET", "HEAD") or (api.method == "" and not api.sends):
        return None
    # gh fills {owner}/{repo} from the cwd's repo: None sends _slug to git.
    post.repo = None if "{" in m.group(1) + m.group(2) else f"{m.group(1)}/{m.group(2)}"
    return post


def posts(doc):
    """(posts, cd, heredocs): each PR the command opens, whether it runs a cd,
    and its heredoc bodies with whether any is built at run time."""
    out, cd = [], False
    for text, nested in doc.texts():
        s = doc.scan(text)
        if sw.cd_present(s):
            cd = True
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, sw.CLIENTS, nested)
            if g is None or g + 2 > b:
                continue
            glab = sw.client(s.w[g]) == "glab"
            env = "GITLAB_REPO=" if glab else "GH_REPO="
            repo = next((s.w[i][len(env):] for i in range(a, g) if s.k[i] == "w" and s.w[i].startswith(env)), None)
            if glab:
                p = _mr_create(s, g, b, repo) if s.w[g + 1] == "mr" and s.w[g + 2] in _CREATE else \
                    _glab_api(s, g, b) if s.w[g + 1] == "api" else None
                if p:
                    out.append(p)
            elif s.w[g + 1] == "pr" and s.w[g + 2] in _CREATE:
                out.append(_pr_create(s, g, b, repo))
            elif s.w[g + 1] == "api":
                p = _api(s, g, b)
                if p:
                    out.append(p)
    return out, cd, doc.heredocs()


def _fetch(p):
    """The text of the file `p`, as the runner reads it, or the Refuse it comes to."""
    try:
        return (yield Need("read", p, paths.MAX_READ))
    except UnicodeDecodeError as e:
        return Refuse(say("unreadable_file", err=e))
    except OSError as e:
        return Refuse(say("unreadable_file", err=e.strerror or e))
    except ValueError as e:                    # not a regular file, or past MAX_READ
        return Refuse(say("passed", text=e))


def _abs(p, cwd, cd, env):
    """The absolute, collapsed path `p` names, or None when this command's own cd hides where it stands."""
    if p == "~" or p.startswith("~/"):
        p = (env.get("HOME") or "") + p[1:] if env.get("HOME") else None
    elif not os.path.isabs(p):
        p = os.path.join(cwd, p) if cwd and not cd else None
    return os.path.normpath(p) if p else p


def _body(post, cwd, cd, docs, writes, env, guard):
    """The text of the body `post` sends, or the deny that says why it cannot be read.
    `writes` maps each path the command writes to (times written, whether a heredoc
    writes it, whether it is appended to); a heredoc's text stands for the file only
    when it is the path's one write and that write replaces the file."""
    text = ""
    for kind, v in post.parts:
        if kind == "text":
            text += v + "\n"
        elif kind == "opaque":
            return _deny(guard, say("dup_body_opaque", v=v))
        elif kind == "stdin":
            if not docs:
                return _deny(guard, say("dup_body_stdin"))
            text += "".join(body + "\n" for body, _ in docs)
        elif got := writes.get(_abs(v, cwd, cd, env) or v):
            n, fed, app = got
            if n != 1:
                return _deny(guard, say("dup_body_rewritten", v=v, n=n))
            if app:
                return _deny(guard, say("dup_body_appended", v=v))
            if not fed:
                return _deny(guard, say("dup_body_not_heredoc", v=v))
            text += "".join(body + "\n" for body, _ in docs)    # its one write is a heredoc: that text, not the file's
        else:
            p = _abs(v, cwd, cd, env)
            got = Refuse(say("dp_relative_cd")) \
                if p is None else (yield from _fetch(p))
            if isinstance(got, Refuse):
                return _deny(guard, say("dup_body_file", v=v, got=got))
            text += got + "\n"
    return text


def _slug(post, cd, cwd, env):
    """(host, owner/name) of the repo a bare #N is on, on the post's forge, or None. A GitLab
    -R that is no URL is on GITLAB_HOST's host, else gitlab.com, as glab picks."""
    repo, forge = post.repo, post.forge
    if repo and forge == "github":
        r = sw.norm_repo(repo)
        return ("github.com", r) if re.fullmatch(rf"{_NAME}/{_NAME}", r) else None
    if repo:
        r = sw.remote(repo) if re.match(r"[A-Za-z][A-Za-z0-9+.-]*://|[^/:@]+@", repo) else None
        if r:
            return (r.host, r.repo.lower()) if r.forge == forge else None
        r = repo.strip("/").lower()
        host = (env.get("GITLAB_HOST") or sw.FORGES[forge]["host"]).lower()
        return (host, r) if sw.FORGES[forge]["repo"].fullmatch(r) else None
    if cd or not cwd:
        return None
    url = yield from remote_url(cwd)
    r = sw.remote(url)
    return (r.host, sw.norm_repo(r.repo)) if r and r.forge == forge else None


def _open_prs(slug, n):
    """[(owner/name, M, title)] of the open PRs cross-referenced on issue n,
    or None when GitHub can't answer, or fills the page with none: an older
    one may sit past it."""
    code, body = yield Need("forge-api", "github", "github.com",
                            f"repos/{slug}/issues/{n}/timeline?per_page={PAGE}")
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
        pr = (sw.norm_repo(r), iss["number"], str(iss.get("title") or ""))
        if pr[:2] not in [p[:2] for p in out]:
            out.append(pr)
    return out if out or len(body) < PAGE else None


def _open_mrs(host, slug, n):
    """[(group/project, M, title)] of the open merge requests GitLab relates to issue n,
    or None when GitLab can't answer, or fills the page with none."""
    code, body = yield Need("forge-api", "gitlab", host,
                            f"projects/{quote(slug, safe='')}/issues/{n}/related_merge_requests?per_page={PAGE}")
    if code != 200 or not isinstance(body, list):
        return None
    out = []
    for mr in body:
        if not (isinstance(mr, dict) and mr.get("state") == "opened" and isinstance(mr.get("iid"), int)):
            continue
        m = _GL_WEB.match(str(mr.get("web_url") or ""))
        pr = (m.group(1).lower() if m else slug, mr["iid"], str(mr.get("title") or ""))
        if pr[:2] not in [p[:2] for p in out]:
            out.append(pr)
    return out if out or len(body) < PAGE else None


def _judge(text, where, guard, forge="github"):
    """deny or ask for one body, or None. `where` is (host, owner/name) of a bare #N, or None."""
    gitlab = forge == "gitlab"
    host, slug = where or (None, None)
    closes = refs(CLOSES_GL if gitlab else CLOSES, text, slug)
    if not closes:
        return None
    gone = refs(SUPERSEDES_GL if gitlab else SUPERSEDES, text, slug)
    asked = None
    for repo, n in closes:
        if repo is None:
            asked = asked or ask(say("dup_repo_unknown", guard=guard, n=n))
            continue
        if gitlab:
            prs = yield from _open_mrs(host or sw.FORGES[forge]["host"], repo, n)
        else:
            prs = yield from _open_prs(repo, n)
        if prs is None and gitlab:
            asked = asked or ask(say("dup_gitlab_silent", guard=guard, repo=repo, n=n, page=PAGE,
                                     path=quote(repo, safe="")))
            continue
        if prs is None:
            asked = asked or ask(say("dup_github_silent", guard=guard, repo=repo, n=n, page=PAGE))
            continue
        for pr_repo, m, title in prs:
            if (pr_repo, m) in gone:
                continue
            here = lambda r, x, sig="#": f"{sig}{x}" if r == repo else f"{r}{sig}{x}"
            sig = "!" if gitlab else "#"
            named, pr = here(pr_repo, m, sig) + (f" ({title})" if title else ""), here(pr_repo, m, sig)
            if gitlab:
                return _deny(guard, say("dup_open_mr", named=named, issue=here(repo, n), pr=pr))
            return _deny(guard, say("dup_open", named=named, issue=here(repo, n), pr=pr))
    return asked


def opened(doc):
    """The `pr-opens` test: {"posts": each PR the call opens, "cd": whether the command runs a
    cd, "docs": its heredoc bodies, "writes": each path it writes to, as (times written,
    whether a heredoc writes it, whether it is appended to)}, or None when no PR it opens
    carries a body."""
    env, tool = doc.env, doc.tool
    if not isinstance(tool, str):
        return None
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    cwd = doc.payload.get("cwd")
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or ("gh" not in cmd and "glab" not in cmd):
            return None
        found, cd, docs = posts(doc)
        written, fed = sw.writes(cmd + "\n", False), sw.writes(cmd + "\n", True)
        appended = [m.group(2) for m in _APPEND.finditer(cmd)]
    elif _MCP.match(tool):
        body, owner, repo = ti.get("body"), ti.get("owner"), ti.get("repo")
        post = _Post(f"{owner}/{repo}" if isinstance(owner, str) and owner and isinstance(repo, str) and repo
                     else None)
        if isinstance(body, str):
            post.parts.append(("text", body))
        found, cd, docs, written, fed, appended = [post], False, [], [], [], []
    else:
        return None
    if not any(p.parts for p in found):
        return None
    writes = {}
    for w in written:
        k = _abs(w, cwd, cd, env) or w
        writes[k] = (writes.get(k, (0, False, False))[0] + 1, False, False)
    for w in fed:
        k = _abs(w, cwd, cd, env) or w
        writes[k] = (writes.get(k, (0, False, False))[0], True, False)
    for w in appended:
        k = _abs(w, cwd, cd, env) or w
        if k in writes:
            writes[k] = (writes[k][0], writes[k][1], True)
    return {"posts": found, "cd": cd, "docs": docs, "writes": writes}


def timelines(doc, guard, found):
    """The `issue-timelines` handler: each body the call sends is read, and every issue it
    closes is looked up in that issue's timeline on GitHub; an open PR already there is a deny,
    unless the body supersedes it. It asks when GitHub or the repo cannot tell, and denies a
    body it cannot read."""
    cwd, cd = doc.payload.get("cwd"), found["cd"]
    asked = None
    for post in found["posts"]:
        if not post.parts:
            continue
        text = yield from _body(post, cwd, cd, found["docs"], found["writes"], doc.env, guard)
        if isinstance(text, dict):
            return text
        if not (CLOSES_GL if post.forge == "gitlab" else CLOSES).search(text):
            continue
        where = yield from _slug(post, cd, cwd, doc.env)
        v = yield from _judge(text, where, guard, post.forge)
        if v and v["permissionDecision"] == "deny":
            return v
        asked = asked or v
    return asked
