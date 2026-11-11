"""guard-bypass-ruleset's walk and its handler (languette/rules/guard_bypass_ruleset.py is
the rule set): a ruleset's bypass is the user's, never the agent's. The spec is
features/guard-bypass-ruleset.feature.

An agent that runs on the user's credentials may bypass a branch's rules
wherever the user may, and GitHub cannot tell them apart. Two
doors are watched:

- a `git push` (or `yadm push`, `vcsh <repo> push`) that lands on the remote's default branch,
  when GitHub says that branch requires a pull request: a ruleset with a
  `pull_request` rule, or classic branch protection with required reviews.
  Only a "requires a pull request" answer is cached, for an hour under
  $XDG_CACHE_HOME/languette/rulesets; a file the agent can write can then
  only make the guard stricter, never silent.
- `gh pr merge --admin`, which exists only to merge past a PR's rules.

On GitLab the rule is a protected branch: one no role below Administrator may
push to takes a merge request, and a user, group or deploy key let push there
anyway is its bypass. glab's `mr merge` has no flag that merges past the
rules, so the push is GitLab's one door. Not protected, by name or by a wildcard, is open.

Both deny. The user's own terminal never reaches a hook, so the user keeps
the bypass. When GitHub cannot answer (no gh, signed out, offline, a 10 s
timeout, an error) or the destination cannot be read (a variable refspec,
GIT_DIR, a detached HEAD), the guard asks, so the user decides. A refspec
whose only run-time part is `$NAME` is read when the same command line set
NAME to a literal earlier, where the push is sure to see it, and is judged
as if that literal were written in its place. GitHub's
"upgrade to Pro" answer is not a failure: a private repo on a free plan
cannot carry rules, so there is nothing to bypass.

The default branch is the remote's HEAD as git last fetched it, and main
and master beside it: that HEAD is a local ref the agent can move, so it may
add a branch to watch, never take one away. A `cd` is followed, `~/` read as
HOME and `-C $NAME/...` read as `-C` takes a literal refspec. A subshell's cd
ends with it. A cd the shell may undo another way (in a group, as an element
of a pipeline, in an and-or list that is backgrounded or carries on past
`||`), a cd an earlier command in its and-or list may skip, and a `popd` leave the
directory unknown, so the guard asks. Not watched: pushes to
any other branch, tags and deletions (guard-git-work-loss and guard-git-stacked-base
judge those), remotes on neither forge or behind an ssh host alias, `gh api`
writes to a ref or a merge endpoint, an alias from the user's own gitconfig
or `gh alias`, and `push.default=matching` (a bare `git push origin` pushing
every matching branch).
"""

import os
import re
from functools import partial
from urllib.parse import quote

from languette import scan as sw
from languette.refs import default_branches, git_asker
from languette.messages import say
from languette.verdict import Act, Need, Refuse, ask, deny

TTL = 3600

_EXPORT = frozenset("export declare typeset".split())
_ALL = frozenset("--all --branches --mirror".split())
# The operators a separator's text is made of, as Scan piles them up (`;}&&` for `; } &&`).
_OPS = re.compile(sw.SEP_OPS.pattern + r"|\{|\}|`")
_PIPE = ("|", "|&")
# The openers among the keywords that lead a segment, and the closers.
_OPEN = {"if": False, "while": True, "until": True, "for": True, "select": True}   # keyword -> a loop
_CLOSE = frozenset("fi done".split())
# Text that can set a variable without naming it literally, or change what an unquoted $NAME
# expands to: ANSI and locale quoting, arithmetic, indirection, IFS, and the builtins that take a
# variable's name as a value.
_SETS_BLIND = re.compile(r"\$['\"]|\(\(|\$\{!|\[\[|\bIFS\b|(?<![\w./-])(?:eval|source|read|mapfile|readarray|"
                         r"printf|getopts|let|declare|typeset|local|readonly|unset|trap|wait|alias|builtin|"
                         r"command|enable|exec|coproc|function|shopt|set)(?![\w./-])")
_RESERVED = frozenset("if then else elif fi case esac for select while until do done in ! time { } [[ ]] .".split())
# Names the shell sets on its own, or will not let a script set.
_SPECIAL = re.compile(r"\A(?:BASH\w*|COMP\w*|HIST\w*|PWD|OLDPWD|RANDOM|SRANDOM|SECONDS|LINENO|UID|EUID|PPID|"
                      r"GROUPS|SHELLOPTS|PIPESTATUS|FUNCNAME|DIRSTACK|EPOCH\w*|REPLY|OPT\w*|SHLVL|_)\Z")
HEAD, ALL, IMPLICIT = object(), object(), object()


class _Push:
    def __init__(self, prog, here, remote, dsts, repo=None):
        self.prog, self.here, self.remote, self.dsts, self.repo = prog, here, remote, dsts, repo


class _Literals:
    """The literal values a top-level command line gives its variables, for reading a refspec
    like `HEAD:$B` after `B=lit;`. Only a plain `NAME=lit` (or `export NAME=lit`) segment
    binds, and only when the push is sure to see it: NAME appears nowhere else in the
    command, nothing can set it blindly, and only `;`, newlines and `&&` lie between."""

    def __init__(self, s, raw):
        self.s, self.raw, self.bind = s, raw, {}
        self.off = bool(_SETS_BLIND.search(raw))
        for a, b in s.segments():
            if a > b:
                continue
            c = sw.seg_cmd(s, a, b)
            if s.w[a] in _RESERVED or (c is not None and s.w[c] in _RESERVED):
                self.off = True
            words = range(a + 1, b + 1) if c == a and s.w[a] == "export" else range(a, b + 1) if c is None else ()
            if words and all(s.k[i] == "w" and sw._ASSIGN.match(s.w[i]) for i in words):
                for i in words:
                    name, _, val = s.w[i].partition("=")
                    # whitespace: an unquoted $NAME splits there into more than one refspec
                    ok = val and not s.live[i] and not sw.UNREADABLE.search(val) and not re.search(r"[~\s]", val)
                    self.bind[name] = (a, val if ok else None)
            elif c is not None and s.w[c] == "export":
                self.off = True

    def _seps(self, lo, hi):
        """The kinds of separator between word indexes lo and hi, ";" and "&&", or None for any other."""
        kinds = set()
        for i in range(lo, hi):
            if self.s.k[i] == ";":
                op = re.sub(r"\s", "", self.s.op[i])
                if op not in ("", ";", "&&"):
                    return None
                kinds.add(op or ";")
        return kinds

    def word(self, j, start):
        """Word j, in the segment that starts at start, with its one $NAME replaced by NAME's
        literal, or None."""
        w = self.s.w[j]
        m = sw.VAR_REF.search(w)
        if self.off or self.s.k[j] != "w" or w.count("$") != 1 or "`" in w or not m:
            return None
        name = m.group(1) or m.group(2)
        a, val = self.bind.get(name, (None, None))
        if val is None or a >= start or _SPECIAL.match(name):
            return None
        reads = len(re.findall(r"\$\{%s\}|\$%s(?![A-Za-z0-9_])" % (name, name), self.raw))
        if len(re.findall(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % name, self.raw)) != reads + 1:
            return None                        # NAME is set, or named, somewhere else as well
        before, between = self._seps(0, a), self._seps(a, start)
        if before is None or between is None or not (before <= {";"} or between <= {"&&"}):
            return None                        # the push may run when the assignment didn't
        r = w[:m.start()] + val + w[m.end():]
        return None if r.startswith("-") else r  # an option (--all, --delete), not a refspec


def _resolve(base, target, live, home=None, quoted=True):
    """The directory `cd target` lands in from base, or None if unreadable. A leading `~` or
    `~/` is HOME when no part of the word is quoted or escaped; `~user` is not read."""
    if target == "~" or target.startswith("~/"):
        if quoted or not (home and home.startswith("/")):
            return None
        target = home + target[1:]
    if base is None or live or sw.UNREADABLE.search(target) or target.startswith("~") or target == "-":
        return None
    return os.path.normpath(target if target.startswith("/") else os.path.join(base, target))


def _ops(op):
    """The operators in a separator's text, a newline read as `;` unless it only continues
    the line (after `&&`, `||`, a pipe or an opening bracket)."""
    out = []
    for o in _OPS.findall(op):
        if o == "\n":
            if out and out[-1] in ("&&", "||", "|", "|&", "(", "{"):
                continue
            o = ";"
        out.append(o)
    return out


def _opt(x, full):
    """Whether x is git push's long option `full`, or an abbreviation git takes for it (`--al` for `--all`)."""
    return sw.long_option(x, full, "push")


def _push(s, a, b, nested, here, lits=None):
    g = sw.cmd_index(s, a, b, sw.GIT, nested)
    if g is None:
        return None
    call = sw.GitCall(s, a, g, b)
    prog, row, repo = call.prog, call.row, call.repo
    for kind, v, j in call.places:
        if kind != "C":
            here = None
        elif v is not None:
            lit = lits and s.live[j] and lits.word(j, a)
            here = _resolve(here, lit, False) if lit else _resolve(here, v, s.live[j])
    if any(c and (c.startswith("alias.") or "insteadof" in c) for c in call.configs):
        raise Refuse(say("br_alias"))
    i = call.sub
    if i > b:
        return None
    x = call.verb
    if row.repo and repo is None and x == "push":
        return _Push(prog, here, None, [IMPLICIT])    # in every repository, a bare push: vcsh push ignores what follows
    if x != "push":
        if s.live[i] or sw.UNREADABLE.search(x):
            raise Refuse(say("br_sub_live", x=x))
        return None                            # another subcommand
    remote, pos, all_, tags, dry, dashdash = None, [], False, False, False, False
    i += 1
    while i <= b:
        x = s.w[i]
        if dashdash or not x.startswith("-") or x == "-":
            pos.append(i)
        elif x == "--":
            dashdash = True
        elif x == "--no-dry-run":
            dry = False                        # the last of -n and --no-dry-run wins
        elif _opt(x, "--repo") and "=" not in x and i + 1 <= b:
            remote = s.w[i + 1]
            if s.live[i + 1]:
                raise Refuse(say("br_remote_live", remote=remote))
        elif _opt(x, "--repo") and "=" in x:
            remote = x.split("=", 1)[1]
            if s.live[i]:
                raise Refuse(say("br_remote_live", remote=remote))
        elif any(_opt(x, f) for f in _ALL):
            all_ = True
        elif _opt(x, "--tags"):
            tags = True
        elif _opt(x, "--delete") or re.match(r"-[^o-]*d", x):
            return None                        # a deletion is other guards'
        elif _opt(x, "--dry-run") or re.match(r"-[^o-]*n", x):
            dry = True                         # a dry run pushes nothing
        if x in sw.PROGRAMS["git push"]["valued"] or (_opt(x, "--repo") and "=" not in x):
            i += 1
        i += 1
    if dry:
        return None
    if remote is None and pos:
        k = pos.pop(0)
        remote = s.w[k]
        if s.live[k]:
            raise Refuse(say("br_remote_live", remote=remote))
    if remote is not None and sw.UNREADABLE.search(remote):
        raise Refuse(say("br_remote_live", remote=remote))
    if all_:
        return _Push(prog, here, remote, [ALL], repo)
    if not pos:
        return None if tags else _Push(prog, here, remote, [IMPLICIT], repo)
    dsts = []
    for j in pos:
        r = (lits and s.live[j] and lits.word(j, a)) or s.w[j]
        if (s.live[j] and r is s.w[j]) or sw.UNREADABLE.search(r):
            raise Refuse(say("br_refspec_live", refspec=s.w[j]))
        src, _, dst = r.lstrip("+").partition(":")
        if ":" in r and not src:
            continue                           # :branch deletes
        dst = dst or src
        if dst in ("HEAD", "@"):
            dsts.append(HEAD)
            continue
        if dst.startswith("refs/heads/"):
            dst = dst[11:]
        elif dst.startswith("refs/"):
            continue                           # a tag or another namespace
        dsts.append(dst)
    return _Push(prog, here, remote, dsts, repo) if dsts else None


def _admin_merge(s, a, b, nested):
    g = sw.cmd_index(s, a, b, sw.GH, nested)
    if g is None:
        return False
    w = s.w[g + 1:b + 1]
    admin = any(x == "--admin" or x.startswith("--admin=") for x in w)
    dyn = [sw.word_live(s, g + 1 + k) for k in range(len(w))]
    first, skip, odd = [], False, False        # the group and its verb; a literal -R value is neither
    for k, x in enumerate(w):
        if skip:
            skip = False
            if dyn[k]:                         # a run-time -R value may split into `pr merge`
                first.append(k)
        elif x.startswith("-"):
            skip = x in sw.GH_REPO_FLAGS or sw.long_option(x, "--repo") and "=" not in x
            odd = odd or len(first) < 2 and not (skip or sw.long_option(x, "--repo"))
        elif len(first) < 2:
            first.append(k)
    # Certain only when no flag ahead of the verb but the repo flag could hide a value.
    if (len(first) >= 2 and not odd and not dyn[first[0]] and not dyn[first[1]]
            and (w[first[0]], w[first[1]]) != ("pr", "merge")):
        return False                           # a literal other verb: `merge` is a flag's value, as in `--add-label merge`
    if "pr" in w and "merge" in w:
        if admin:
            return True
        if any(dyn):
            raise Refuse(say("br_merge_live"))
        return False
    if any(dyn):
        if admin:
            return True                        # a live subcommand beside a literal --admin
        # Only a run-time group, or a run-time verb under a literal `pr`, could spell `pr merge`.
        if first and (dyn[first[0]] or (w[first[0]] == "pr" and len(first) > 1 and dyn[first[1]])):
            raise Refuse(say("br_gh_live"))
    return False


def _compound(s, a, b):
    """(the command word's index or None, the compounds opened, a close): segment a..b read
    past the keywords leading it. `for` and `select` open a loop whose own words are no command."""
    i, opens = a, []
    while i <= b and s.k[i] == "w" and not s.quoted[i] and s.w[i] in sw.KEYWORD_LEADS:
        if s.w[i] in _OPEN:
            opens.append(_OPEN[s.w[i]])
        i += 1
    if i <= b and s.k[i] == "w" and not s.quoted[i]:
        if s.w[i] in ("for", "select"):
            return None, opens + [True], False
        if s.w[i] in _CLOSE:
            return None, opens, True
    return (sw.seg_cmd(s, i, b) if i <= b else None), opens, False


def _loops_moved(s, segs):
    """The segments that open a loop with a cd anywhere in it, to its done or the text's end."""
    stack, out = [], set()
    for n, (c, opens, close) in enumerate(segs):
        stack += [[n, loop, False] for loop in opens]
        if c is not None and sw.CD.match(s.w[c]):
            for f in stack:
                f[2] = True
        if close and stack:
            f = stack.pop()
            if f[1] and f[2]:
                out.add(f[0])
    out.update(f[0] for f in stack if f[1] and f[2])
    return out


def _walk(doc, cmd, cwd, home=None):
    """(pushes, whether an admin merge was seen, the first Refuse). A Refuse ends only its own
    command, so an admin merge or a push on PR-only main later in the line still denies.

    A cd holds for the commands after it unless the shell may undo it first: a subshell
    around it closes (back to the directory before the subshell), a group around it closes,
    it is an element of a pipeline, its and-or list is backgrounded or carries on past `||`,
    it follows `||`, a command before it in its and-or list may have skipped it and the list
    ends, or a backtick follows. The last seven leave the directory unknown. A cd behind
    `then`, `else`, `do` or `!` is seen; past the `else` or `elif` that follows it and past the `fi`
    or `done` that closes it, the directory is unknown, and through a whole loop that holds one, since a later pass starts where it left."""
    pushes, admin, refused = [], False, None
    for text, nested in doc.texts():
        s, here, moved = doc.scan(text), cwd, False
        lits = None if nested else _Literals(s, cmd)
        # Each open bracket: (here, and the and-or list's state) as it opened. Scan keeps no
        # separator before the first word, so brackets that lead the text are read here. The
        # list's state: it held a cd, it held a command, a cd in it may not have run.
        frames, list_cd, list_cmd, cond_cd = [], False, False, False

        def ops(op):
            nonlocal here, list_cd, list_cmd, cond_cd
            for o in _ops(op):
                if o in ("(", "{"):
                    frames.append((here, list_cd, list_cmd, cond_cd))
                    list_cd = list_cmd = cond_cd = False
                elif o in (")", "}"):
                    if not frames:
                        here = None            # a close with no open seen: a case arm, or unread
                        continue
                    before, list_cd, list_cmd, cond_cd = frames.pop()
                    if o == ")":
                        here = before          # a subshell's cd ends with it
                    elif here != before:
                        here = None            # a group may run in a subshell (a pipeline, `&`)
                elif o == "&" and list_cd or o == "||" and list_cd or o == "`" and moved:
                    here = None
                if o in (";", "&"):
                    if cond_cd:
                        here = None            # the list ends; the cd in it may have been skipped
                    list_cd = list_cmd = cond_cd = False

        ops("".join(re.findall(r"[({]", re.match(r"[\s({]*", text).group())))
        segs = [_compound(s, a, b) if a <= b else (None, [], False) for a, b in s.segments()]
        loops, kw = _loops_moved(s, segs), []  # kw: each open if or loop, and whether a cd ran in it
        for n, (a, b) in enumerate(s.segments()):
            c, opens, close = segs[n]
            kw += [False] * len(opens)
            if n in loops:
                here = None                    # a later pass starts wherever the cd left it
            if close and kw and kw.pop():
                here = None                    # the cd inside may not have run
            if kw and a <= b and s.k[a] == "w" and not s.quoted[a] and s.w[a] in ("else", "elif") and kw[-1]:
                here = None                    # a branch that did not run left no cd behind it
            if c is not None and sw.CD.match(s.w[c]):
                kw = [True] * len(kw)
                prev = _ops(s.op[a - 1]) if a > 0 else []
                nxt = _ops(s.op[b + 1]) if b + 1 < len(s) else []
                if (prev and prev[-1] in _PIPE + ("||",)) or (nxt and nxt[0] in _PIPE) or s.w[c] == "popd" or c + 1 > b:
                    here = None                # a pipeline element, after `||`, a popd, or a bare cd
                else:
                    here = _resolve(here, s.w[c + 1], s.live[c + 1], home, s.quoted[c + 1])
                cond_cd = cond_cd or list_cmd
                moved = list_cd = True
            elif c is not None and s.w[c] in _EXPORT and any(sw.git_env(s.w[j]) for j in range(c + 1, b + 1)):
                here = None                    # an exported GIT_DIR moves every later git
            elif a <= b:
                try:
                    admin = admin or _admin_merge(s, a, b, nested)
                    p = _push(s, a, b, nested, here, lits)
                except Refuse as e:
                    refused = refused or e
                    p = None
                if p:
                    pushes.append(p)
            list_cmd = list_cmd or a <= b
            if b + 1 < len(s):
                ops(s.op[b + 1])
    return pushes, admin, refused


def _git(p, env, *args):
    if p.here is None and not sw.GIT_WRAPPERS[p.prog].home:
        return None
    run = sw.wrapper_git(p.prog, p.repo, env)
    if run is None:
        return None                            # a vcsh repository that cannot be told from a verb or a path
    return (yield from git_asker(p.here or env.get("HOME") or "/", *run)(*args))


def _says(body, words):
    return isinstance(body, dict) and words in str(body.get("message", "")).lower()


def _requires_pr(slug, branch):
    """"pr", "open", or None when GitHub can't answer."""
    cached = yield Need("ruleset-cache", slug, branch)
    if cached and cached[1] == "pr" and (yield Need("clock")) - cached[0] < TTL:
        return "pr"
    b = quote(branch, safe="")
    code, body = yield Need("forge-api", "github", "github.com", f"repos/{slug}/rules/branches/{b}")
    if code == 200 and isinstance(body, list) and any(isinstance(r, dict) and r.get("type") == "pull_request"
                                                      for r in body):
        got = "pr"
    elif code == 403 and _says(body, "upgrade"):
        got = "open"                           # this plan can carry no rules and no protection
    elif code != 200:
        return None
    else:
        code, body = yield Need("forge-api", "github", "github.com",
                                f"repos/{slug}/branches/{b}/protection")
        if code == 200 and isinstance(body, dict):
            got = "pr" if body.get("required_pull_request_reviews") else "open"
        elif code == 404 and (_says(body, "not protected") or _says(body, "branch not found")):
            got = "open"                       # no branch, and the rules endpoint already said no ruleset
        else:
            return None
    if got == "pr":
        yield Act("ruleset-keep", slug, branch, got)
    return got


def _gl_pushes(entry):
    """"pr" or "open" for one protected-branch entry, or None when it carries no push levels."""
    if not isinstance(entry, dict) or not isinstance(entry.get("push_access_levels"), list):
        return None
    roles = [e.get("access_level") for e in entry["push_access_levels"] if isinstance(e, dict)
             and not any(e.get(k) is not None for k in ("user_id", "group_id", "deploy_key_id", "member_role_id"))]
    return "open" if any(isinstance(x, int) and 0 < x < 60 for x in roles) else "pr"


def _gl_wildcard(name, branch):
    """Does the protected-branch `name` (GitLab wildcards are `*` only) match `branch`?"""
    return re.fullmatch(".*".join(re.escape(x) for x in name.split("*")), branch) is not None


def _requires_mr(host, slug, branch):
    """"pr", "open", or None when GitLab can't answer. A protected branch no role below
    Administrator may push to takes a merge request; a user, group or deploy key allowed to
    push there anyway (or a custom role) is that rule's bypass, as a ruleset's bypass actor is on GitHub.
    A branch protected only by a wildcard name answers 404 by name, so the list is matched."""
    key = f"{host}/{slug}"
    cached = yield Need("ruleset-cache", key, branch)
    if cached and cached[1] == "pr" and (yield Need("clock")) - cached[0] < TTL:
        return "pr"
    proj = f"projects/{quote(slug, safe='')}/protected_branches"
    code, body = yield Need("forge-api", "gitlab", host, f"{proj}/{quote(branch, safe='')}")
    if code == 200 and isinstance(body, dict) and isinstance(body.get("push_access_levels"), list):
        got = _gl_pushes(body)
    elif code == 404 and isinstance(body, dict) and str(body.get("message", "")).lower() == "404 not found":
        code, body = yield Need("forge-api", "gitlab", host, f"{proj}?per_page={sw.PAGE}")
        if code != 200 or not isinstance(body, list):
            return None
        hits = [_gl_pushes(e) for e in body if isinstance(e, dict) and isinstance(e.get("name"), str)
                and _gl_wildcard(e["name"], branch)]
        if None in hits or (not hits and len(body) >= sw.PAGE):
            return None                        # an entry unread, or a match may sit on a later page
        got = "open" if not hits or "open" in hits else "pr"   # the most permissive matching rule applies
    else:
        return None
    if got == "pr":
        yield Act("ruleset-keep", key, branch, got)
    return got


def _judge(p, env):
    """deny or ask for one push, or None."""
    remote, dsts = p.remote, list(p.dsts)
    if IMPLICIT in dsts:
        dsts.remove(IMPLICIT)
        up = yield from _git(p, env, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{push}")
        if up and "/" in up:
            r, br = up.split("/", 1)
            remote = remote or r
            dsts.append(br)
        else:
            dsts.append(HEAD)
    if HEAD in dsts:
        dsts.remove(HEAD)
        cur = yield from _git(p, env, "symbolic-ref", "--short", "HEAD")
        if cur is None:
            return ask(say("ruleset_head_unknown", prog=p.prog))
        dsts.append(cur)
    if remote is None:
        cur = (yield from _git(p, env, "symbolic-ref", "--short", "HEAD")) or ""
        for key in (f"branch.{cur}.pushRemote", "remote.pushDefault", f"branch.{cur}.remote"):
            remote = yield from _git(p, env, "config", key)
            if remote:
                break
        remote = remote or "origin"
    url = remote if ("/" in remote or ":" in remote) else (yield from _git(p, env, "remote", "get-url", "--push",
                                                                           remote))
    defaults = yield from default_branches(partial(_git, p, env), remote)
    hits = defaults if ALL in dsts else [d for d in dsts if d in defaults]
    if not hits:
        return None
    if url is None:
        return ask(say("ruleset_repo_unknown", branch=hits[0], remote=remote))
    r = sw.remote(url)
    if not r or r.forge not in ("github", "gitlab"):
        return None
    slug, gitlab = r.repo, r.forge == "gitlab"
    asked = None
    for branch in hits:
        if gitlab:
            got = yield from _requires_mr(r.host, slug, branch)
        else:
            got = yield from _requires_pr(slug, branch)
        if got == "pr" and gitlab:
            return deny(say("ruleset_needs_mr", branch=branch, slug=slug))
        if got == "pr":
            return deny(say("ruleset_needs_pr", branch=branch, slug=slug))
        bq = quote(branch, safe="")
        if got is None and gitlab:
            asked = asked or ask(say("ruleset_gitlab_silent", branch=branch, slug=slug, branch_q=bq,
                                     slug_q=quote(slug, safe="")))
        elif got is None:
            asked = asked or ask(say("ruleset_github_silent", branch=branch, slug=slug, branch_q=bq))
    return asked


def pushed(doc):
    """The `ruleset-pushes` test: {"pushes": the pushes the command runs, "admin": whether it
    runs `gh pr merge --admin`, "refused": the first command it could not read, or None}, or
    None when it holds none of the three."""
    cmd = doc.text
    if not cmd or not cmd.strip():
        return None
    pushes, admin, refused = _walk(doc, cmd, doc.payload["cwd"], doc.env.get("HOME"))
    return {"pushes": pushes, "admin": admin, "refused": refused} if pushes or admin or refused else None


def branch_rules(doc, guard, found):
    """The `branch-rules` handler: an admin merge is denied; a push that lands on the remote's
    default branch asks GitHub, through the cache, whether that branch requires a pull
    request, and is denied when it does; it asks when GitHub or the walk cannot tell."""
    if found["admin"]:
        return deny(say("ruleset_admin"))
    asked = None
    for p in found["pushes"]:
        v = yield from _judge(p, doc.env)
        if v and v["permissionDecision"] == "deny":
            return v
        asked = asked or v
    if found["refused"]:
        return ask(say("ruleset_refused", refused=found["refused"]))
    return asked
