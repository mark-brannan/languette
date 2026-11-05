"""guard-git-stacked-base's walk and its handler (languette/rules/guard_git_stacked_base.py
is the rule set): deleting a remote branch that an open pull request
still names as its base or its head is denied. The spec is
features/guard-git-stacked-base.feature.

GitHub retargets a stacked PR only when its base disappears because the base
PR merged; deleted any other way, every PR on it closes, silently. So this
fires on remote-branch deletion only (`git push [<remote>] --delete|-d <ref>`,
`git push <remote> :<ref>`, `gh api -X DELETE .../git/refs/heads/<ref>`), and
asks GitHub, through `gh pr list` under `timeout 20`, whether an open PR names
the branch. `gh pr merge --delete-branch` names no branch and never fires;
local `git branch -d/-D` takes nothing from a PR.

GitLab retargets open merge requests only when their target is deleted as part
of its merge, so the same holds there: `glab api -X DELETE
projects/:id/repository/branches/<ref>` is a deletion too, and a deletion on a
project whose remote is a GitLab one asks `glab mr list` for an open merge
request whose target or source is the branch.

  an open PR found                -> deny
  gh absent, failing or timed out -> ask
  no timeout or gtimeout          -> ask; gh is never run unbounded
  a branch named by a variable or a glob, or git pointed at another
  repository (-C, --git-dir, GIT_DIR=)  -> ask
"""

import json
import re
from urllib.parse import unquote

from languette import scan as sw
from languette.refs import remote_url
from languette.messages import say
from languette.verdict import Need, ask, deny

_UNRESOLVED = re.compile(r"[$`*?\[]")
_REPO = re.compile(r"(?:^|/)repos/[^/]+/[^/]+/")
_SHORT_O = re.compile(r"-[^o=-]*o\Z")   # -o, or a cluster ending in it (-fo): the value is the next word
TIMEOUT = 20
LIST = "  gh pr list --state open --json number,baseRefName,headRefName"
# Each forge's client, a row (docs/design/forges.md): how it lists open PRs on a branch,
# by (its flag, the field it answers in) for the base side, then the head side.
_LISTS = {
    "github": {"cli": "gh", "argv": ("pr", "list", "--state", "open"),
               "json": ("--json", "number,title,baseRefName,headRefName"),
               "sides": (("--base", "baseRefName"), ("--head", "headRefName")), "number": ("number", "#"),
               "list": LIST},
    "gitlab": {"cli": "glab", "argv": ("mr", "list"), "json": ("-F", "json"),
               "sides": (("--target-branch", "target_branch"), ("--source-branch", "source_branch")),
               "number": ("iid", "!"), "list": "  glab mr list --target-branch <branch> -F json"},
}
# A GitLab REST branch deletion: the project in group 1, the branch, URL-encoded, in group 2.
_GL_BRANCH = re.compile(r"(?:api/v4/)?projects/([^/]+)/repository/branches/(.+)")


def _emit(out, repo, ref, forge=None):
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref in ("", "HEAD"):
        return
    out.append((repo, "?" if _UNRESOLVED.search(ref) else ref, forge))


def _git_push(s, a, b, nested, out):
    g = sw.cmd_index(s, a, b, sw.GIT, nested)
    if g is None:
        return
    p = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and s.w[i] == "push"), None)
    if p is None:
        return
    repo = "-"
    if any(s.k[i] == "w" and s.w[i].startswith("GIT_DIR=") for i in range(a, g)):
        repo = "?"
    if any(s.k[i] == "w" and (s.w[i] == "-C" or s.w[i].startswith("--git-dir")) for i in range(g + 1, p)):
        repo = "?"
    words, skip, valued = [], False, sw.PROGRAMS["git push"]["valued"]
    for i in range(p + 1, b + 1):
        if s.k[i] != "w":
            continue
        w = s.w[i]
        if skip:                               # the value of -o, --repo, ...: not the remote, not a ref
            skip = False
        elif _SHORT_O.match(w) or (len(w) >= 3 and "=" not in w and any(v.startswith(w) for v in valued)):
            skip = True                        # git takes any unambiguous prefix of a long option
        else:
            words.append(w)
    delete = any(w in ("--delete", "-d") for w in words)
    seen_remote = False
    for w in words:
        if w.startswith(":"):                  # a deletion with or without --delete, never the remote
            _emit(out, repo, w[1:])
            continue
        if w.startswith("-"):
            continue
        if not seen_remote:
            seen_remote = True                 # the remote name
            continue
        if delete:
            _emit(out, repo, w)


def _gh_api(s, a, b, nested, out):
    g = sw.cmd_index(s, a, b, sw.CLIENTS, nested)
    v = sw.gh_verb(s, g + 1, b) if g is not None else None
    if v is None or sw.word(s, v) != "api":
        return
    cli = sw.client(s.w[g])
    api = sw.gh_api(s, v + 1, b, cli)
    m = _GL_BRANCH.fullmatch(api.path) if cli == "glab" else None
    if api.method == "DELETE" and m:
        # :id is the cwd's project; anything else names one glab -R reads.
        project = unquote(m.group(1))
        repo = "-" if project == ":id" else "?" if project.isdigit() or _UNRESOLVED.search(project) else project
        _emit(out, repo, unquote(m.group(2)), "gitlab")
        return
    if cli == "glab" or api.method != "DELETE" or "refs/heads/" not in api.path:
        return
    # The endpoint names its repository; {owner}/{repo} is the cwd's.
    repo, w = "?", api.path
    if "{owner}/{repo}/" in w:
        repo = "-"
    else:
        m = _REPO.search(w)
        if m:
            rest = re.sub(r"^/?repos/", "", m.group(0)).rstrip("/")
            if not _UNRESOLVED.search(rest):
                repo = rest
    _emit(out, repo, w[w.index("refs/heads/") + len("refs/heads/"):], "github")


def deletions(doc):
    """[(repo, branch, forge)] for each remote-branch deletion in the command, in order: repo
    is "-" for the cwd's repository, "owner/name" when the command names one,
    "?" when git is pointed elsewhere; a branch of "?" is not a literal name; forge is the
    scan.FORGES key a forge client's API call names, None for git's, the cwd's remote's."""
    out = []
    for text, nested in doc.texts():
        s = doc.scan(text)
        for a, b in s.segments():
            if a <= b:
                _git_push(s, a, b, nested, out)
                _gh_api(s, a, b, nested, out)
    return out


def _unreadable(guard, b, listed=LIST):
    return ask(say("sb_unreadable", guard=guard, b=b, list=listed))


def deleted(doc):
    """The `branch-deletions` test: {"deleted": deletions(doc)}, or None when there are none."""
    cmd = doc.text
    if not cmd or ("push" not in cmd and "refs/heads/" not in cmd and "repository/branches" not in cmd):
        return None
    out = deletions(doc)
    return {"deleted": out} if out else None


def open_prs(doc, guard, found):
    """The `open-prs` handler: asks the forge, through its client's PR list under a timeout
    (`gh pr list`, `glab mr list`), whether an open PR names a deleted branch as its base or
    its head; asks when it cannot tell. git's deletion is on the cwd's remote's forge,
    GitHub's unless that remote is a GitLab one."""
    deleted = found["deleted"]
    if any(b == "?" for _, b, _ in deleted):
        forges = {f for _, b, f in deleted if b == "?"}
        lists = [row["list"] for k, row in _LISTS.items() if None in forges or k in forges]   # the cwd's forge is unread
        return ask(say("sb_unresolved", guard=guard, list="\n".join(lists)))
    if any(r == "?" for r, _, _ in deleted):
        return ask(say("sb_other_repo", guard=guard))
    cwd = doc.payload["cwd"]
    here = None
    if any(f is None for _, _, f in deleted):
        r = sw.remote((yield from remote_url(cwd)) or "")
        here = r.forge if r and r.forge in _LISTS else None
    deleted = [(r, b, f or here or "github") for r, b, f in deleted]
    for forge in dict.fromkeys(f for _, _, f in deleted):
        if not (yield Need("which", _LISTS[forge]["cli"])):
            return ask(say("sb_no_gh", guard=guard, cli=_LISTS[forge]["cli"]))
    bound = None
    for t in ("timeout", "gtimeout"):          # GNU coreutils' name, then Homebrew's
        if (yield Need("which", t)):
            bound = t
            break
    if not bound:
        return ask(say("sb_no_timeout", guard=guard, list=_LISTS[deleted[0][2]]["list"]))
    for repo, b, forge in dict.fromkeys(deleted):
        row = _LISTS[forge]
        key, sigil = row["number"]
        for (side, field), base in zip(row["sides"], (True, False)):
            argv = [bound, str(TIMEOUT), row["cli"], *row["argv"]]
            argv += [side, b] if repo == "-" else ["-R", repo, side, b]
            out = yield Need("pr-list", cwd, *argv, *row["json"])
            if not out:
                return _unreadable(guard, b, row["list"])
            try:
                prs = [f"{sigil}{p[key]} {p['title']}" for p in json.loads(out) if p.get(field) == b]
            except (ValueError, TypeError, KeyError, AttributeError):
                return ask(say("sb_unparsed", guard=guard, b=b))
            listed, gl = "\n".join(prs), forge == "gitlab"
            if prs and base and gl:
                return deny(say("sb_base_open_gl", guard=guard, b=b, prs=listed, advice=say("sb_advice_gl", b=b)))
            if prs and base:
                return deny(say("sb_base_open", guard=guard, b=b, prs=listed, advice=say("sb_advice", b=b)))
            if prs and gl:
                return deny(say("sb_head_open_gl", guard=guard, b=b, prs=listed))
            if prs:
                return deny(say("sb_head_open", guard=guard, b=b, prs=listed))
    return None
