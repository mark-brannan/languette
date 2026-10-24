"""guard-git-stacked-base: deleting a remote branch that an open pull request
still names as its base or its head is denied. The spec is
features/guard-git-stacked-base.feature.

GitHub retargets a stacked PR only when its base disappears because the base
PR merged; deleted any other way, every PR on it closes, silently. So this
fires on remote-branch deletion only (`git push [<remote>] --delete|-d <ref>`,
`git push <remote> :<ref>`, `gh api -X DELETE .../git/refs/heads/<ref>`), and
asks GitHub, through `gh pr list` under `timeout 20`, whether an open PR names
the branch. `gh pr merge --delete-branch` names no branch and never fires;
local `git branch -d/-D` takes nothing from a PR.

  an open PR found                -> deny
  gh absent, failing or timed out -> ask
  no timeout or gtimeout          -> ask; gh is never run unbounded
  a branch named by a variable or a glob, or git pointed at another
  repository (-C, --git-dir, GIT_DIR=)  -> ask
"""

import json
import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import Need, ask, deny

NAME = "guard-git-stacked-base"
GH = re.compile(r"(?:^|/)(?:gh|glab)\Z")
_UNRESOLVED = re.compile(r"[$`*?\[]")
_REPO = re.compile(r"(?:^|/)repos/[^/]+/[^/]+/")
_PUSH_VALUED = ("--push-option", "--repo", "--receive-pack", "--exec")   # --exec is --receive-pack
_SHORT_O = re.compile(r"-[^o=-]*o\Z")   # -o, or a cluster ending in it (-fo): the value is the next word
TIMEOUT = 20
LIST = "  gh pr list --state open --json number,baseRefName,headRefName"


def _emit(out, repo, ref):
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if ref in ("", "HEAD"):
        return
    out.append((repo, "?" if _UNRESOLVED.search(ref) else ref))


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
    words, skip = [], False
    for i in range(p + 1, b + 1):
        if s.k[i] != "w":
            continue
        w = s.w[i]
        if skip:                               # the value of -o, --repo, ...: not the remote, not a ref
            skip = False
        elif _SHORT_O.match(w) or (len(w) >= 3 and "=" not in w and any(v.startswith(w) for v in _PUSH_VALUED)):
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
    g = sw.cmd_index(s, a, b, GH, nested)
    if g is None:
        return
    is_api = is_del = False
    for i in range(g + 1, b + 1):
        if s.k[i] != "w":
            continue
        w = s.w[i]
        is_api = is_api or w == "api"
        if w in ("-X", "--method") and i + 1 <= b and s.k[i + 1] == "w" and s.w[i + 1].upper() == "DELETE":
            is_del = True
        if w.upper() in ("-XDELETE", "--METHOD=DELETE"):
            is_del = True
    if not (is_api and is_del):
        return
    for i in range(g + 1, b + 1):
        if s.k[i] != "w" or "refs/heads/" not in s.w[i]:
            continue
        w = s.w[i]
        # The endpoint names its repository; {owner}/{repo} is the cwd's.
        repo = "?"
        if "{owner}/{repo}/" in w:
            repo = "-"
        else:
            m = _REPO.search(w)
            if m:
                rest = re.sub(r"^/?repos/", "", m.group(0)).rstrip("/")
                if not _UNRESOLVED.search(rest):
                    repo = rest
        _emit(out, repo, w[w.index("refs/heads/") + len("refs/heads/"):])


def deletions(doc):
    """[(repo, branch)] for each remote-branch deletion in the command, in order: repo
    is "-" for the cwd's repository, "owner/name" when the command names one,
    "?" when git is pointed elsewhere; a branch of "?" is not a literal name."""
    out = []
    for text, nested in doc.texts():
        s = doc.scan(text)
        for a, b in s.segments():
            if a <= b:
                _git_push(s, a, b, nested, out)
                _gh_api(s, a, b, nested, out)
    return out


def _unreadable(b):
    return ask(say("sb_unreadable", guard=NAME, b=b, list=LIST))


def check(doc):
    payload = doc.payload
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd or ("push" not in cmd and "refs/heads/" not in cmd):
        return None
    found = deletions(doc)
    if not found:
        return None
    if any(b == "?" for _, b in found):
        return ask(say("sb_unresolved", guard=NAME, list=LIST))
    if any(r == "?" for r, _ in found):
        return ask(say("sb_other_repo", guard=NAME))
    if not (yield Need("which", "gh")):
        return ask(say("sb_no_gh", guard=NAME))
    bound = None
    for t in ("timeout", "gtimeout"):          # GNU coreutils' name, then Homebrew's
        if (yield Need("which", t)):
            bound = t
            break
    if not bound:
        return ask(say("sb_no_timeout", guard=NAME, list=LIST))
    cwd = payload["cwd"]
    for repo, b in dict.fromkeys(found):
        for side, field in (("--base", "baseRefName"), ("--head", "headRefName")):
            argv = [bound, str(TIMEOUT), "gh", "pr", "list", "--state", "open"]
            argv += [side, b] if repo == "-" else ["-R", repo, side, b]
            out = yield Need("pr-list", cwd, *argv, "--json", "number,title,baseRefName,headRefName")
            if not out:
                return _unreadable(b)
            try:
                prs = [f"#{p['number']} {p['title']}" for p in json.loads(out) if p.get(field) == b]
            except (ValueError, TypeError, KeyError, AttributeError):
                return ask(say("sb_unparsed", guard=NAME, b=b))
            if prs and side == "--base":
                return deny(say("sb_base_open", guard=NAME, b=b, prs="\n".join(prs), advice=say("sb_advice", b=b)))
            if prs:
                return deny(say("sb_head_open", guard=NAME, b=b, prs="\n".join(prs)))
    return None
