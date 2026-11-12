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
past paths.MAX_READ, stdin with no heredoc) is a deny that says why. Where a
body comes from is read as guard-signed-comments and guard-private-terms read
it (languette.bodies).
"""

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
_GL_NAME = rf"{_NAME}(?:/(?!-/){_NAME})+"
_GL_REF = (rf"(?:(?P<repo>{_GL_NAME})?#(?P<num>[0-9]+)"
           rf"|https?://(?P<uhost>[^/\s]+)/(?P<urepo>{_GL_NAME})/(?:-/)?(?:issues|work_items)/(?P<unum>[0-9]+))"
           rf"(?![A-Za-z0-9_/])")
_GL_KEYS = r"(?:clos(?:e[sd]?|ing)|fix(?:e[sd]|ing)?|resolv(?:e[sd]?|ing)|implement(?:s|ed|ing)?)"
CLOSES_GL = re.compile(rf"(?<![A-Za-z0-9_-]){_GL_KEYS}(?:[ \t]*:[ \t]*|[ \t]+)(?:issues?[ \t]+)?{_GL_REF}",
                       re.IGNORECASE)
# GitLab reads "Closes #1, #2" and "Closes #1 and #2" as closing both.
_GL_MORE = re.compile(rf"(?:[ \t]*,?[ \t]+and[ \t]+|[ \t]*,[ \t]*){_GL_REF}", re.IGNORECASE)
_GL_MR = (rf"(?:(?P<repo>{_GL_NAME})?!(?P<num>[0-9]+)"
          rf"|https?://(?P<uhost>[^/\s]+)/(?P<urepo>{_GL_NAME})/(?:-/)?merge_requests/(?P<unum>[0-9]+))(?![A-Za-z0-9_/])")
SUPERSEDES_GL = re.compile(rf"(?<![A-Za-z0-9_-])(?:supersedes|replaces)(?:[ \t]*:[ \t]*|[ \t]+){_GL_MR}",
                           re.IGNORECASE)
_GL_WEB = re.compile(rf"https?://[^/]+/({_GL_NAME})/(?:-/)?merge_requests/[0-9]+")
# glab mr create's flags that take a value (-b is the target branch, never a body).
_GL_VALUED = frozenset("-a --assignee -H --head -l --label -m --milestone --reviewer -s --source-branch "
                       "-b --target-branch --template -t --title --attach".split())
_GL_PROJECT = re.compile(r"(?:api/v4/)?projects/([^/]+)/merge_requests")

def _deny(guard, why):
    return deny(say("judged", guard=guard, why=why))


def refs(rx, text, repo, host=None, more=None):
    """[(owner/name, N)] for each reference `rx` finds in `text`, in order; a
    bare #N is on `repo` (None when unknown). A URL on another host than `host` is
    prose, not a reference, as GitLab itself reads it."""
    out = []
    for m in rx.finditer(text):
        while m:
            uh = m.groupdict().get("uhost")
            if not (host and uh and uh.lower() != host.lower()):
                r = m.group("repo") or m.group("urepo")
                r = sw.norm_repo(r) if r else repo
                n = int(m.group("num") or m.group("unum"))
                if (r, n) not in out:
                    out.append((r, n))
            m = more.match(text, m.end()) if more else None
    return out


class _Post:
    """One PR a command opens: its repo as written (None = the cwd's), the forge
    it opens on (a scan.FORGES key), and its body as sources (languette.bodies)."""

    def __init__(self, repo=None, forge="github"):
        self.repo, self.forge, self.parts = repo, forge, []


def _related(post, v, live):
    """-i/--related-issue N: the MR is for issue N, read as a body that closes it."""
    if not live and re.fullmatch(r"#?[0-9]+", v):
        post.parts.append(("text", f"Closes #{v.lstrip('#')}"))


# Per client, the flags that carry the body, the body file, and the flags whose value is no body.
_PR_FLAGS = {"gh": (("-b", "--body"), ("-F", "--body-file"), ()),
             "glab": (("-d", "--description"), ("--description-file",), ("-i", "--related-issue"))}


def _create(r, s, lo, g, hi, repo, cli):
    """`gh pr create|new` or `glab mr create|new`: the body from its body flag or body file;
    for glab, -i/--related-issue too, an MR for that issue, read as closing it."""
    post = _Post(repo, "gitlab" if cli == "glab" else "github")
    body, files, related = _PR_FLAGS[cli]
    valued = _GL_VALUED if cli == "glab" else _VALUED
    for f in sw.flag_words(s, g + 3, hi, body + files + related + sw.GH_REPO_FLAGS + tuple(valued)):
        if f.name is None or f.value is None:
            continue
        if f.name in sw.GH_REPO_FLAGS:
            post.repo = f.value
        elif f.name in body:
            post.parts.append(r.value(f.value, f.live))
        elif f.name in files:
            post.parts.append(r.file(f.value, f.live, f.tilde, s, lo, hi))
        elif f.name in related:
            _related(post, f.value, f.live)
    return post


def _api_body(r, s, lo, g, hi, cli, key):
    """The post a `gh api` or `glab api` call's `key` field sends, and its GhApi."""
    api, post = sw.gh_api(s, g + 2, hi, cli), _Post(forge="gitlab" if cli == "glab" else "github")
    for a in api.args:
        if a.key == key:
            if a.value.startswith("@") and a.typed:
                post.parts.append(r.file(a.value[1:], a.live, True, s, lo, hi))
            else:
                post.parts.append(r.value(a.value, a.live))
    return api, post


def _glab_api(r, s, lo, g, hi):
    api, post = _api_body(r, s, lo, g, hi, "glab", "description")
    m = _GL_PROJECT.fullmatch(api.path)
    if not m or not api.writes:
        return None
    # glab fills :id from the cwd's project: None sends _slug to git; a numeric id is "?".
    repo = sw.gl_project(unquote(m.group(1)))
    post.repo = None if repo == "-" else repo
    return post


def _api(r, s, lo, g, hi):
    api, post = _api_body(r, s, lo, g, hi, "gh", "body")
    m = re.fullmatch(rf"repos/({_NAME}|\{{owner\}})/({_NAME}|\{{repo\}})/pulls", api.path)
    if not m or not api.writes:
        return None
    # gh fills {owner}/{repo} from the cwd's repo: None sends _slug to git.
    post.repo = None if "{" in m.group(1) + m.group(2) else f"{m.group(1)}/{m.group(2)}"
    return post


def posts(doc, r):
    """(posts, cd): each PR the command opens, read against its Bodies `r`, and whether it runs a cd."""
    out, cd = [], False
    for text, nested in r.texts():
        s = doc.scan(text)
        if sw.cd_present(s):
            cd = True
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, sw.CLIENTS, nested)
            if g is None or g + 2 > b:
                continue
            cli = sw.client(s.w[g])
            repo = sw.gh_env_repo(s, a, g, cli)
            if s.w[g + 1] == ("mr" if cli == "glab" else "pr") and s.w[g + 2] in _CREATE:
                out.append(_create(r, s, a, g, b, repo, cli))
            elif s.w[g + 1] == "api":
                p = _glab_api(r, s, a, g, b) if cli == "glab" else _api(r, s, a, g, b)
                if p:
                    out.append(p)
    return out, cd


def _fetch(p):
    """The text of the file `p`, as the runner reads it, or the Refuse it comes to."""
    try:
        return (yield Need("read", p, paths.MAX_READ))
    except (OSError, ValueError) as e:
        return paths.read_refusal(e)


def _body(post, r, cwd, cd, env, guard):
    """The text of the body `post` sends, or the deny that says why it cannot be read."""
    home = env.get("HOME") or ""
    resolve = lambda p, live, tilde: paths.word_path(p, None if cd else cwd, home, live, tilde)
    text = ""
    for src in post.parts:
        if src[0] == "file":
            v, src = src[1], r.where(src, resolve)
            if src[0] == "read":
                got = yield from _fetch(src[1])
                if isinstance(got, Refuse):
                    return _deny(guard, say("dup_body_file", v=v, got=got))
                text += got + "\n"
                continue
            if src[0] == "unread":
                return _deny(guard, say("dup_body_file", v=v, got=src[1]))
        if src[0] == "text":
            text += src[1] + "\n"
        elif src[0] == "doc":
            text += r.docs[src[1]][0] + "\n"
        else:
            return _deny(guard, say("dup_body_opaque", why=src[1]))
    return text


def _gl_host(env):
    """The host a GitLab group/project with no host of its own is on: GITLAB_HOST's,
    else gitlab.com, as glab picks."""
    return (env.get("GITLAB_HOST") or sw.FORGES["gitlab"]["host"]).lower()


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
        host = _gl_host(env)
        parts = r.split("/")
        if forge == "gitlab" and len(parts) >= 3 and re.search(r"[.:]", parts[0]):
            host, r = parts[0], "/".join(parts[1:])      # [HOST/]GROUP/PROJECT, as glab splits it
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
                            f"repos/{slug}/issues/{n}/timeline?per_page={sw.PAGE}")
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
    return out if out or len(body) < sw.PAGE else None


def _open_mrs(host, slug, n):
    """[(group/project, M, title)] of the open merge requests GitLab relates to issue n,
    or None when GitLab can't answer, or fills the page with none."""
    code, body = yield Need("forge-api", "gitlab", host,
                            f"projects/{quote(slug, safe='')}/issues/{n}/related_merge_requests?per_page={sw.PAGE}")
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
    return out if out or len(body) < sw.PAGE else None


def _judge(text, where, guard, forge="github", default=None):
    """deny or ask for one body, or None. `where` is (host, owner/name) of a bare #N, or None;
    `default` the host an explicit group/project#N is on when `where` gives none."""
    gitlab = forge == "gitlab"
    host, slug = where or (None, None)
    on = (host or default or sw.FORGES[forge]["host"]) if gitlab else None
    closes = refs(CLOSES_GL if gitlab else CLOSES, text, slug, on, _GL_MORE if gitlab else None)
    if not closes:
        return None
    gone = refs(SUPERSEDES_GL if gitlab else SUPERSEDES, text, slug, on)
    asked = None
    for repo, n in closes:
        if repo is None:
            asked = asked or ask(say("dup_repo_unknown", guard=guard, n=n))
            continue
        if gitlab:
            prs = yield from _open_mrs(on, repo, n)
        else:
            prs = yield from _open_prs(repo, n)
        if prs is None and gitlab:
            asked = asked or ask(say("dup_gitlab_silent", guard=guard, repo=repo, n=n, page=sw.PAGE,
                                     path=quote(repo, safe="")))
            continue
        if prs is None:
            asked = asked or ask(say("dup_github_silent", guard=guard, repo=repo, n=n, page=sw.PAGE))
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
    cd, "read": the command's Bodies, None for the MCP tool}, or None when no PR it opens
    carries a body."""
    tool = doc.tool
    if not isinstance(tool, str):
        return None
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or ("gh" not in cmd and "glab" not in cmd):
            return None
        r = sw.Bodies(doc, cmd)
        found, cd = posts(doc, r)
    elif _MCP.match(tool):
        body, owner, repo = ti.get("body"), ti.get("owner"), ti.get("repo")
        post = _Post(f"{owner}/{repo}" if isinstance(owner, str) and owner and isinstance(repo, str) and repo
                     else None)
        if isinstance(body, str):
            post.parts.append(("text", body))
        found, cd, r = [post], False, None
    else:
        return None
    if not any(p.parts for p in found):
        return None
    return {"posts": found, "cd": cd, "read": r}


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
        text = yield from _body(post, found["read"], cwd, cd, doc.env, guard)
        if isinstance(text, dict):
            return text
        if not (CLOSES_GL if post.forge == "gitlab" else CLOSES).search(text):
            continue
        where = yield from _slug(post, cd, cwd, doc.env)
        v = yield from _judge(text, where, guard, post.forge, _gl_host(doc.env))
        if v and v["permissionDecision"] == "deny":
            return v
        asked = asked or v
    return asked
