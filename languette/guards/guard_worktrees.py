"""guard-worktrees: two controls over where a session's git work lands. The
spec is features/guard-worktrees.feature.

  checkout-home  a `git`/`yadm`/`vcsh` checkout or switch that would move the branch
                 checked out in $HOME, when $HOME is itself a worktree
  foreign        a reach into a linked worktree that is not this session's own,
                 by a Bash word, a file tool's path, or EnterWorktree(path=...)

Opt-in: hooks.json runs it only when the option guard_worktrees is exactly
true, and run.py without --guard skips it unless that option is set. A
control is skipped when its own option (guard_worktrees_checkout_home,
guard_worktrees_foreign) is exactly false; the first control to object wins,
and a note is given only when neither does.

checkout-home. yadm and vcsh hardcode --work-tree=$HOME, so any such checkout/switch
that is not a file restore (`checkout [<ref>] -- <path>`) is denied, from any
directory. Plain git is denied only when git itself resolves the target to
$HOME's worktree (`rev-parse --show-toplevel`), following a cd/pushd, chained
-C, --git-dir/--work-tree and GIT_DIR=/GIT_WORK_TREE=, exported or inline. A
--git-dir counts when it is $HOME's repo or any repo whose work tree is $HOME.
A directory that cannot be resolved (a variable, `cd -`, a stale cwd) is a
deny, with one exception: an allow with a note when the session's cwd is its
own linked worktree (recorded, or under its scratchpad) or lies under its
scratchpad, and every directory the command resolved before losing track is
too. The scratchpad is the directory the harness made for the session, not
any directory named for it. Tilde forms expand as the shell expands them: ~
from $HOME, ~user from the user database, ~+ from the directory the word is
read in. A literal path that does not exist yet (after that expansion) is
judged by the nearest directory above it that does, which must be an own
place too. $HOME, a main checkout, a cwd that does not resolve, `cd -`, ~-,
a directory-stack ~N, a ~user the lookup can't find, and a session's first
call (nothing recorded yet) keep the deny. So does every cd or -C after a
command that may make a link or move, copy or unpack something into place
(ln, mv, cp, rsync, tar, unzip, cpio, git mv): a path it touched need not
land where it looks. A word that resolves into another session's worktree
is the foreign control's deny. What a word the guard can't read names (a
variable other than HOME, a `$( )`, a glob) is unseen, so it may be any
directory: a known gap. So is a link made by a command the guard does not
know as one (a script, a clone whose tree holds a symlink).
`(cd x); git checkout y` is judged from x: a known false allow.

foreign. Another session's worktree is never a place to work:
the session that owns a worktree may archive it mid-turn under anyone who
reached in. Any path-shaped word (or the word after -C, or a cd target) that
git resolves to a toplevel that is not this session's own and whose `.git` is
a file (a linked worktree) is denied; main worktrees and other clones are
allowed. A session's own: the cwd's toplevel; a linked worktree with a path
component equal to the payload's session_id (its scratchpad); and toplevels
recorded in ${TMPDIR:-/tmp}/languette-guard-worktrees.<session>[.<agent>]
when reached by a route this guard vouches for (the session's first call, the
call after EnterWorktree(name=...), a cd into a path that did not exist yet),
or, at the session's next call, the path of an unconditional `git worktree
add` this guard allowed while nothing stood there, when a `.git` file made
since stands there. Each record line carries the inode of the worktree's
`.git`; a record not
owned by this user, or a symlink, is ignored. EnterWorktree(path=...) is
denied outright. Redirection targets are not seen. The deny names a
one-command recipe for the session's own worktree.
"""

import os
import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import Act, Need, Refuse, context, deny

NAME = "guard-worktrees"
OPT_IN = "CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES"
MAX_CANDIDATES = 48
# A spelling that names the same directory from anywhere: absolute, $HOME, ~ or ~user.
_HOMEISH = re.compile(r"(?:/|~(?:[^/+\-0-9][^/]*)?(?:/|\Z)|\$HOME(?:/|\Z)|\$\{HOME\}(?:/|\Z))")
# A tilde the guard can't follow: ~- is $OLDPWD, ~N, ~+N and ~-N the directory stack.
_TILDE_LOST = re.compile(r"~(?:-|[+-]?[0-9]+)(?:/|\Z)")
# A command that can make a path land somewhere other than where it looks: a
# link made, or something moved, copied or unpacked into place.
_FS_CHANGE = re.compile(r"(?:^|/)(?:ln|link|mv|cp|rsync|tar|unzip|cpio)\Z")
GETENT_TIMEOUT = 2
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_KEYWORD = frozenset("builtin command if then else elif while until do !".split())


def _git(cwd, *argv):
    return (yield Need("git", "git", cwd, *argv))


def _canon(p):
    """`cd p && pwd -P`, or None."""
    if p and (yield Need("path", "isdir", p)):
        return (yield Need("path", "realpath", p))
    return None


def _user_home(name):
    """A user's home directory from the user database, as the shell's ~user
    reads it, or None when it can't be had."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9._-]*", name):
        return None
    try:
        rc, out, _ = yield Need("run", "/", GETENT_TIMEOUT, "getent", "passwd", name)
    except Exception:  # noqa: BLE001 -- no getent, or it hung: unfollowed
        return None
    f = out.split("\n", 1)[0].split(":")
    return f[5] if rc == 0 and len(f) == 7 and f[0] == name and f[5].startswith("/") else None


def _expand(raw, base, home):
    """`raw` with what the shell expands at its start: $HOME, ${HOME} and every
    tilde form (~ and ~/x from $HOME, ~user from the user database, ~+ from
    the directory it runs in, `base`). None for a tilde the guard can't
    follow: ~-, a directory-stack ~N, a user the lookup can't find, ~+ with no
    directory. Any other word as written."""
    for pre in ("$HOME", "${HOME}"):
        if raw == pre or raw.startswith(pre + "/"):
            return home + raw[len(pre):]
    if not raw.startswith("~"):
        return raw
    head, sep, tail = raw[1:].partition("/")
    if head == "":
        d = home
    elif head == "+":
        d = base
    elif _TILDE_LOST.match(raw):
        d = None
    else:
        d = yield from _user_home(head)
    return d + sep + tail if d else None


# --- checkout-home --------------------------------------------------------

def _home_events(doc):
    """The command's moves, in order: ("DENY", the wrapper as it is typed) for a
    checkout/switch by a wrapper whose work tree is always $HOME, ("CD", v), ("ENV", kind, v) for a GIT_DIR=/GIT_WORK_TREE= outside a git
    segment, ("FS",) for a segment that may make a link or move, copy or
    unpack one into place (a `git mv` too), and ("G", [(kind, v)]) for one git
    checkout/switch with its -C/GITDIR/WORKTREE targets in order."""
    out = []
    for text, nested in doc.texts():
        s = doc.scan(text)
        for a, b in s.segments():
            if a > b:
                continue
            c = sw.cmd_index(s, a, b, sw.CD, nested)
            if c is not None:
                v = next((s.w[i] for i in range(c + 1, b + 1)
                          if s.k[i] == "w" and (not s.w[i].startswith("-") or s.w[i] == "-")), "")
                out.append(("CD", "-" if s.w[c] == "popd" else v))
                continue
            g = sw.cmd_index(s, a, b, sw.GIT, nested)
            if g is None:
                for i in range(a, b + 1):
                    if s.k[i] == "w" and s.w[i].startswith("GIT_DIR="):
                        out.append(("ENV", "GITDIR", s.w[i][8:]))
                    if s.k[i] == "w" and s.w[i].startswith("GIT_WORK_TREE="):
                        out.append(("ENV", "WORKTREE", s.w[i][14:]))
                if sw.cmd_index(s, a, b, _FS_CHANGE, nested) is not None:
                    out.append(("FS",))
                continue
            sidx = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and s.w[i] in ("checkout", "switch")), None)
            if sidx is None:
                sub = sw.git_subcommand(s, g, b)
                if sub <= b and s.w[sub] == "mv":
                    out.append(("FS",))
                continue
            # checkout -- <path> is a file restore; a bare trailing -- is not.
            if s.w[sidx] == "checkout" and any(s.k[i] == "w" and s.w[i] == "--" and s.k[i + 1] == "w"
                                               for i in range(sidx + 1, b)):
                continue
            name, row = sw.git_wrapper(s.w[g])
            if row.home:
                out.append(("DENY", name + " <repo>" * row.repo))
                continue
            targets = []
            for i in range(a, b + 1):
                if s.k[i] != "w":
                    continue
                w = s.w[i]
                nxt = s.w[i + 1] if i + 1 <= b and s.k[i + 1] == "w" else None
                if w == "-C":
                    if nxt is not None:
                        targets.append(("C", nxt))
                elif w == "--git-dir":
                    if nxt is not None:
                        targets.append(("GITDIR", nxt))
                elif w.startswith("--git-dir="):
                    targets.append(("GITDIR", w.split("=", 1)[1]))
                elif w == "--work-tree":
                    if nxt is not None:
                        targets.append(("WORKTREE", nxt))
                elif w.startswith("--work-tree="):
                    targets.append(("WORKTREE", w.split("=", 1)[1]))
                elif w.startswith("GIT_DIR="):
                    targets.append(("GITDIR", w[8:]))
                elif w.startswith("GIT_WORK_TREE="):
                    targets.append(("WORKTREE", w[14:]))
            out.append(("G", targets))
    return out


def _resolve_arg(raw, base, home):
    """A -C/--git-dir/--work-tree/cd value resolved the way the shell would
    leave it unquoted, canonical; a git dir may be a gitfile, so a file
    resolves through its parent. None when it can't be."""
    r = yield from _expand(raw, base, home)
    if r and not r.startswith("/") and base:
        r = base + "/" + r
    if not r or not r.startswith("/"):
        return None
    if (yield Need("path", "isdir", r)):
        return (yield Need("path", "realpath", r))
    if (yield Need("path", "exists", r)):
        parent = yield from _canon(os.path.dirname(r))
        return parent and parent.rstrip("/") + "/" + os.path.basename(r)
    return None


def _resolve_all(raw, bases, home):
    """(resolved, missed): `raw` against every base; an absolute spelling
    against / alone."""
    if _HOMEISH.match(raw):
        bases = ["/"]
    res, miss = [], False
    for base in bases:
        r = yield from _resolve_arg(raw, base, home)
        if r:
            res.append(r)
        else:
            miss = True
    return res, miss


def _landings(raw, bases, home):
    """Where a literal word that does not resolve would land: the nearest
    existing directory above it, against each base it missed on. A word the
    guard can't read (a variable other than HOME, a `$( )`, a glob) lands
    nowhere it can name, so []; a tilde it can't follow (~-, ~N, an unknown
    ~user) and a `..` through a part that does not exist yet are None, never
    judged."""
    if _TILDE_LOST.match(raw):
        return None
    if _HOMEISH.match(raw):
        bases = ["/"]
    out = []
    for base in bases:
        w = yield from _expand(raw, base, home)
        if w is None:
            return None
        if (yield from _resolve_arg(w, base, home)):
            continue
        try:
            d, _ = yield from _resolve_dir(w, base, home)
        except Refuse:
            return None
        if d:
            out.append(d)
    return out


def _generic(prog):
    return Refuse(say("wt_checkout_home", guard=NAME, prog=prog))


def _checkout_home(doc):
    payload, env = doc.payload, doc.env
    cmd = (payload.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd:
        return
    events = _home_events(doc)
    if all(ev[0] == "FS" for ev in events):
        return
    if not (yield Need("which", "git")):
        raise Refuse(say("wt_git_missing_checkout", guard=NAME))
    home = (yield from _canon(env.get("HOME") or "")) or ""
    pcwd = payload.get("cwd")
    cwd = (yield from _canon(pcwd)) if isinstance(pcwd, str) and pcwd else None
    home_gitdir = (yield from _git("/", "-C", home, "rev-parse", "--absolute-git-dir")) if home else None

    def gitdir_is_home(p):
        d = yield from _git("/", f"--git-dir={p}", "rev-parse", "--absolute-git-dir")
        if not d:
            return False
        if home_gitdir and d == home_gitdir:
            return True
        return (yield from _git("/", f"--git-dir={p}", "rev-parse", "--show-toplevel")) == home

    def targets_home(d):
        return d == home or (yield from _git("/", "-C", d, "rev-parse", "--show-toplevel")) == home

    sess = _Session(payload, env, "", home)

    def user_word(v):
        """A ~user word with the user's home put in, so each is looked up once."""
        m = re.match(r"~([^/+\-0-9][^/]*)(/.*)?\Z", v, re.S)
        if not m:
            return v
        d = yield from _user_home(m.group(1))
        return d + (m.group(2) or "") if d else v

    def own_place(d):
        """Under this session's scratchpad, or in its own linked worktree: one
        under the scratchpad or recorded. Never $HOME or a main checkout. The
        scratchpad is the directory itself, found where the harness makes it,
        not any directory named for the session."""
        if d == home:
            return False
        if (yield from sess.in_pad(d)):
            return True
        top = yield from _git("/", "-C", d, "rev-parse", "--show-toplevel")
        if not top or top == home or not (yield Need("path", "isfile", os.path.join(top, ".git"))):
            return False
        return (yield from sess.in_pad(top)) or (yield from sess.recorded(top))

    # visited: every directory the command was known to stand in; None once a
    # `cd -` took it somewhere no word names. changed: a link, move or copy ran
    # earlier, so no later directory word lands where it looks; each is lost.
    cands, lost, env_targets, visited, note = ([cwd] if cwd else []), not cwd, [], ([cwd] if cwd else None), None
    changed = False
    for ev in events:
        if ev[0] == "DENY":
            raise _generic(ev[1])
        if ev[0] == "FS":
            changed = True
        elif ev[0] == "ENV":
            env_targets.append(ev[1:])
        elif ev[0] == "CD":
            v = yield from user_word(ev[1])
            if v == "":
                cands, lost = [home], False
                visited = visited and visited + [home]
            elif v == "-" or changed or _TILDE_LOST.match(v):
                lost, visited = True, None
            else:
                if _HOMEISH.match(v):
                    lost = False
                if lost:
                    continue
                res, miss = yield from _resolve_all(v, cands, home)
                if not miss and res:
                    cands = res
                    visited = visited and visited + res
                else:
                    lost = True
                    # A literal path not made yet is judged where it lands.
                    land = yield from _landings(v, cands, home)
                    visited = visited and (None if land is None else visited + land)
        else:
            if not home:
                raise Refuse(say("wt_home_unresolved_checkout", guard=NAME))
            bases, blind, pinned, unpinned, seen = cands, lost, False, False, visited
            for tk, tv in env_targets + ev[1]:
                tv = yield from user_word(tv)
                if tk == "C":
                    land = None if changed else (yield from _landings(tv, bases, home))
                    bases, miss = yield from _resolve_all(tv, bases, home)
                    blind = blind or changed or miss or not bases
                    seen = seen and (None if land is None else seen + bases + land)
                    continue
                # --work-tree says where files land, not which repo: git still finds the repo from the directory.
                pinned = pinned or tk == "GITDIR"
                res, miss = yield from _resolve_all(tv, bases, home)
                # A value that does not resolve (or is relative to a directory that doesn't) pins nothing.
                # any miss denies: one candidate base that fails to resolve is enough
                unpinned = unpinned or changed or miss or not res or (blind and not _HOMEISH.match(tv))
                for r in res:
                    if (tk == "GITDIR" and (yield from gitdir_is_home(r))) or (tk == "WORKTREE" and r == home):
                        raise _generic("git")
            if unpinned:
                raise Refuse(say("wt_repo_unclear", guard=NAME))
            # --git-dir pins where the command resolves; -C moved the bases; --work-tree does neither.
            if pinned:
                continue
            if blind:
                if not seen:
                    raise Refuse(say("wt_dir_unclear", guard=NAME))
                for d in dict.fromkeys(seen):
                    if not (yield from own_place(d)):
                        raise Refuse(say("wt_dir_unclear", guard=NAME))
                note = say("wt_dir_unclear_note", guard=NAME)
                continue
            for d in bases:
                if (yield from targets_home(d)):
                    raise _generic("git")
    return note


# --- foreign --------------------------------------------------------------

def _pathish(t):
    t = re.sub(r"^--?[A-Za-z0-9][A-Za-z0-9-]*=", "", t, count=1)
    t = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=", "", t, count=1)
    if t in ("~", "$HOME", "${HOME}"):
        return t
    return t if "/" in t else ""


# `git worktree add` options: flags, and those that take the next word.
_ADD_FLAGS = frozenset("-f --force -d --detach --checkout --no-checkout --lock -q --quiet --track --no-track "
                       "--guess-remote --no-guess-remote --orphan --relative-paths --no-relative-paths".split())
_ADD_VALUE = frozenset("-b -B --reason".split())
# Words that make what follows run only on a condition, or more than once.
_CONTROL = frozenset("if then else elif fi while until do done for case select function !".split())


def _worktree_add(s, a, b):
    """(path, [-C values]) for a `git worktree add <path>` in segment a..b, or
    None. Any option it does not know, a word it can't read, or more than a
    path and a commit-ish is None: what it can't parse it never records."""
    g = sw.cmd_index(s, a, b, sw.GIT, False)
    if g is None or sw.git_wrapper(s.w[g])[1].home:
        return None
    sub = sw.git_subcommand(s, g, b)
    if sub + 1 > b or s.w[sub] != "worktree" or s.w[sub + 1] != "add":
        return None
    cs = [s.w[i + 1] for i in sw.git_options(s, g, sub) if s.w[i] == "-C"]
    pos, i, opts = [], sub + 2, True
    while i <= b:
        if s.k[i] != "w":
            return None
        w = s.w[i]
        i += 1
        if not opts or not w.startswith("-") or w == "-":
            pos.append(w)
        elif w == "--":
            opts = False
        elif w in _ADD_FLAGS or w.startswith("--reason="):
            pass
        elif w in _ADD_VALUE:
            i += 1
        elif re.fullmatch(r"-[fdq]*[bB].*|-[fdq]+", w):
            # a bundle: -fq, -fb <branch>, -fbname
            if re.fullmatch(r"-[fdq]*[bB]", w):
                i += 1
        else:
            return None
    if i > b + 1 or not 1 <= len(pos) <= 2:
        return None
    return pos[0], cs


def _foreign_words(doc):
    """("T",) where a text begins (its shell starts in the payload cwd),
    ("C", w) for a cd/pushd target, ("W", w) for any other path-shaped word or
    the word after -C, ("A", path, [-C values]) for a `git worktree add`, in
    order."""
    out = []
    for x, (text, nested) in enumerate(doc.texts()):
        s = doc.scan(text)
        out.append(("T",))
        ncd, seen, cond = 0, set(), False
        for a, b in s.segments():
            c = a
            while c <= b and s.k[c] == "w" and (sw._ASSIGN.match(s.w[c]) or s.w[c] in _KEYWORD):
                c += 1
            cdt = None
            if c <= b and s.k[c] == "w" and s.w[c] in ("cd", "pushd"):
                cdt = -1
                for j in range(c + 1, b + 1):
                    if s.k[j] == "w" and (s.w[j] == "--" or re.fullmatch(r"-[A-Za-z@]+", s.w[j])):
                        continue
                    cdt = j
                    break
                if cdt == -1:
                    out.append(("C", "~"))
                    ncd += 1
            for j in range(a, b + 1):
                if j == cdt:                   # a quoted target is "$Q": unresolvable, as it should be
                    out.append(("C", s.w[j]))
                    ncd += 1
                    continue
                if s.k[j] != "w":
                    continue
                t = s.w[j] if j > a and s.k[j - 1] == "w" and s.w[j - 1] == "-C" else _pathish(s.w[j])
                if not t or (ncd, t) in seen:
                    continue
                seen.add((ncd, t))
                out.append(("W", t))
            # An add that runs only on a condition (behind &&, ||, a pipe, a
            # keyword, or in a nested text) may never run: it records nothing.
            if a > 0 and any(o in s.op[a - 1] for o in ("&&", "||", "|")):
                cond = True
            cond = cond or nested or any(s.k[j] == "w" and s.w[j] in _CONTROL for j in range(a, b + 1))
            add = None if cond else _worktree_add(s, a, b)
            if add:
                out.append(("A", *add))
    return out


class _Session:
    """This session's own worktrees: the cwd's toplevel, its scratchpad, and
    the per-session record, which World keeps (the `worktree` fact). Every
    failure to read or write the record leaves the rule as strict as the cwd
    alone."""

    def __init__(self, payload, env, own_top, home):
        self.env, self.own_top, self.home = env, own_top, home
        sid, aid = payload.get("session_id"), payload.get("agent_id")
        self.sid = sid if isinstance(sid, str) else ""
        self.rec, self.pad = None, None
        if self.sid:
            tag = re.sub(r"[^A-Za-z0-9_-]", "_", self.sid)
            if isinstance(aid, str) and aid:
                tag += "." + re.sub(r"[^A-Za-z0-9_-]", "_", aid)
            self.rec = os.path.join(env.get("TMPDIR") or "/tmp", "languette-guard-worktrees." + tag)

    def under_scratch(self, d):
        return bool(self.sid) and f"/{self.sid}/" in f"/{d}/"

    def in_pad(self, d):
        """`d` is the scratchpad the harness made for this session, or under it."""
        if self.pad is None:
            p = (yield Need("worktree", "scratchpad", self.sid)) if self.sid else None
            self.pad = ((yield from _canon(p)) if p else None) or ""
        return bool(self.pad) and (d == self.pad or d.startswith(self.pad.rstrip("/") + "/"))

    def recorded(self, top):
        if not self.rec:
            return False
        return (yield Need("worktree", "recorded", self.rec, top))

    def leave(self, text):
        """What the next call may adopt as its own: `enter`, the arrivals, or
        `add<TAB><path>` for a worktree this call's `git worktree add` makes."""
        if self.rec:
            yield Act("worktree-leave", self.rec, text)

    def arrive(self, own_linked):
        """Record the cwd's toplevel when this call reached it by a vouched
        route; consume the arrival the previous call left, exactly once."""
        if not self.rec:
            return
        usable, adopt = yield Need("worktree", "arrive", self.rec, self.own_top if own_linked else "")
        if not usable:
            self.rec = None
            return
        if adopt and own_linked and not self.under_scratch(self.own_top) and not (yield from self.recorded(self.own_top)):
            yield Act("worktree-keep", self.rec, self.own_top)

    def scratchpad(self):
        d = (yield Need("worktree", "scratchpad", self.sid)) if self.sid else None
        return d or "<scratchpad>"


def _recipe(sess, d):
    gcd = yield from _git("/", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir")
    scratch = yield from sess.scratchpad()
    return f"git --git-dir={gcd or '<git-dir>'} worktree add {scratch}/<name> && cd {scratch}/<name>"


def _deny_path(sess, env, word, ft):
    branch = yield from _git("/", "-C", ft, "symbolic-ref", "-q", "--short", "HEAD")
    recipe = yield from _recipe(sess, ft)
    raise Refuse(say("wt_foreign", guard=NAME, word=word, ft=ft, recipe=recipe, branch=branch or "<branch>"))


def _resolve_dir(raw, base, home):
    """(canonical nearest existing directory, the part below it that does not
    exist yet), or ("", "") when the word can't be judged."""
    r = yield from _expand(raw, base, home)
    if r and not r.startswith("/") and base:
        r = base + "/" + r
    if not r or not r.startswith("/"):
        return "", ""
    # An unexpandable word ($VAR, a brace, a glob): the walk up would answer
    # about a real ancestor instead.
    if any(ch in r for ch in "$*?{"):
        return "", ""
    rest = ""
    while r and r != "/" and not (yield Need("path", "isdir", r)):
        if "/" not in r:
            return "", ""
        r, last = r.rsplit("/", 1)
        rest = last + ("/" + rest if rest else "")
        r = r or "/"
    if not (yield Need("path", "isdir", r)):
        return "", ""
    if "/../" in f"/{rest}/":
        raise Refuse(say("wt_dotdot_missing", guard=NAME, raw=raw))
    return (yield Need("path", "realpath", r)), rest


def _foreign(doc):
    payload, env = doc.payload, doc.env
    # git is what every foreignness answer is asked of: without it, every path
    # would read as nobody's worktree.
    if not (yield Need("which", "git")):
        raise Refuse(say("wt_git_missing_owner", guard=NAME))
    tool = payload.get("tool_name")
    pcwd = payload["cwd"]
    home = yield from _canon(env.get("HOME") or "")
    if not home:
        raise Refuse(say("wt_home_unresolved_owner", guard=NAME))
    own_top = (yield from _git("/", "-C", pcwd, "rev-parse", "--show-toplevel")) or ""
    sess = _Session(payload, env, own_top, home)
    yield from sess.arrive(bool(own_top) and (yield Need("path", "isfile", os.path.join(own_top, ".git"))))
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}

    if tool == "EnterWorktree":
        p = ti.get("path")
        if not p:                              # a fresh worktree of the session's making: the next cwd is own
            yield from sess.leave("enter")
            return
        recipe = yield from _recipe(sess, p)
        raise Refuse(say("wt_enter_existing", guard=NAME, recipe=recipe))

    def foreign_top(d):
        t = yield from _git("/", "-C", d, "rev-parse", "--show-toplevel")
        if not t or t == own_top or not (yield Need("path", "isfile", os.path.join(t, ".git"))):
            return None
        if sess.under_scratch(t) or (yield from sess.recorded(t)):
            return None
        return t

    def check_word(word, base):
        d, rest = yield from _resolve_dir(word, base, home)
        if d:
            ft = yield from foreign_top(d)
            if ft:
                yield from _deny_path(sess, env, word, ft)
        return d, rest

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path")
        if isinstance(fp, str) and fp:
            yield from check_word(fp, pcwd)
        return
    if tool != "Bash":
        return
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd:
        return
    arrivals, adds, vcwd, n = [], [], pcwd, 0

    def add_target(word, cs):
        """The canonical path a `git worktree add` will create, or None when it
        can't be told or something that is a worktree already stands there."""
        base = vcwd
        for c in cs:
            if not base:
                break
            d, rest = yield from _resolve_dir(c, base, home)
            base = "" if rest else d
        if not base:
            return None
        d, rest = yield from _resolve_dir(word, base, home)
        if not d:
            return None
        p = d.rstrip("/") + "/" + os.path.normpath(rest) if rest else d
        if _CTRL.search(p) or (yield Need("path", "lexists", p + "/.git")) or (rest and (yield Need("path", "lexists", p))):
            return None
        return None if sess.under_scratch(p) else p

    for ev in _foreign_words(doc):
        if ev[0] == "T":
            vcwd = pcwd
            continue
        if ev[0] == "A":
            p = yield from add_target(ev[1], ev[2])
            if p:
                adds.append(p)
            continue
        kind, word = ev
        if not word:
            continue
        n += 1
        if n > MAX_CANDIDATES:
            break
        if vcwd and vcwd != pcwd:
            cd_dir, cd_rest = yield from check_word(word, vcwd)
            yield from check_word(word, pcwd)
        else:
            cd_dir, cd_rest = yield from check_word(word, pcwd)
        if kind != "C":
            continue
        if not cd_dir:
            vcwd = ""
        elif cd_rest:
            vcwd = cd_dir + "/" + cd_rest
            arrivals.append(vcwd)
        else:
            vcwd = cd_dir
    # Allowed. Leave this command's arrivals for the next call to consume.
    if arrivals or adds:
        yield from sess.leave("\n".join(arrivals + ["add\t" + p for p in adds]))


CONTROLS = (("CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_CHECKOUT_HOME", _checkout_home),
            ("CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_FOREIGN", _foreign))


def check(doc):
    if not isinstance(doc.payload, dict):
        return None
    notes = []
    for option, control in CONTROLS:
        if doc.env.get(option) == "false":
            continue
        try:
            note = yield from control(doc)
        except Refuse as r:
            return deny(str(r))
        if note:
            notes.append(note)
    return context("\n\n".join(notes)) if notes else None
