"""guard-worktrees: two controls over where a session's git work lands. The
specs are features/guard-worktrees-checkout-home.feature and
features/guard-worktrees-foreign.feature.

  checkout-home  a `git`/`yadm` checkout or switch that would move the branch
                 checked out in $HOME, when $HOME is itself a worktree
  foreign        a reach into a linked worktree that is not this session's own,
                 by a Bash word, a file tool's path, or EnterWorktree(path=...)

Opt-in: hooks.json runs it only when the option guard_worktrees is exactly
true, and run.py without --guard skips it unless that option is set. A
control is skipped when its own option (guard_worktrees_checkout_home,
guard_worktrees_foreign) is exactly false; the first control to object wins.

checkout-home. yadm hardcodes --work-tree=$HOME, so any yadm checkout/switch
that is not a file restore (`checkout [<ref>] -- <path>`) is denied, from any
directory. Plain git is denied only when git itself resolves the target to
$HOME's worktree (`rev-parse --show-toplevel`), following a cd/pushd, chained
-C, --git-dir/--work-tree and GIT_DIR=/GIT_WORK_TREE=, exported or inline. A
--git-dir counts when it is $HOME's repo or any repo whose work tree is $HOME.
A directory that cannot be resolved (a variable, `cd -`, a stale cwd) is a
deny. `(cd x); git checkout y` is judged from x: a known false allow.

foreign. A hand-off carries a branch, an issue and a PR, never a directory:
the session that owns a worktree may archive it mid-turn under anyone who
reached in. Any path-shaped word (or the word after -C, or a cd target) that
git resolves to a toplevel that is not this session's own and whose `.git` is
a file (a linked worktree) is denied; main worktrees and other clones are
allowed. A session's own: the cwd's toplevel; a linked worktree with a path
component equal to the payload's session_id (its scratchpad); and toplevels
recorded in ${TMPDIR:-/tmp}/languette-guard-worktrees.<session>[.<agent>]
when reached by a route this guard vouches for (the session's first call, the
call after EnterWorktree(name=...), a cd into a path that did not exist yet).
Each record line carries the inode of the worktree's `.git`; a record not
owned by this user, or a symlink, is ignored. EnterWorktree(path=...) is
denied outright. Redirection targets are not seen. The deny names
claim-stamp.sh's live or stale reading when it is usable, and a one-command
recipe for the session's own worktree.
"""

import glob
import os
import re

from languette import scan as sw
from languette.verdict import Need, Refuse, deny

NAME = "guard-worktrees"
OPT_IN = "CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES"
GIT = re.compile(r"(?:^|/)(?:git|yadm)\Z")
CD = re.compile(r"\A(?:cd|pushd|popd)\Z")
MAX_CANDIDATES = 48
_HOMEISH = re.compile(r"(?:/|~\Z|~/|\$HOME\Z|\$HOME/|\$\{HOME\}\Z|\$\{HOME\}/)")
_KEYWORD = frozenset("builtin command if then else elif while until do !".split())


def _git(cwd, *argv):
    return (yield Need("git", "git", cwd, *argv))


def _canon(p):
    """`cd p && pwd -P`, or None."""
    if p and (yield Need("path", "isdir", p)):
        return (yield Need("path", "realpath", p))
    return None


def _expand_home(raw, home):
    """The literal ~ / $HOME / ${HOME} the shell would expand, or None."""
    if raw in ("$HOME", "${HOME}", "~"):
        return home
    for pre in ("$HOME/", "${HOME}/", "~/"):
        if raw.startswith(pre):
            return home + "/" + raw[len(pre):]
    return None


# --- checkout-home --------------------------------------------------------

def _home_events(cmd):
    """The command's moves, in order: ("DENY",) for a yadm checkout/switch,
    ("CD", v), ("ENV", kind, v) for a GIT_DIR=/GIT_WORK_TREE= outside a git
    segment, and ("G", [(kind, v)]) for one git checkout/switch with its
    -C/GITDIR/WORKTREE targets in order."""
    out = []
    for text, nested in sw.texts_of(sw.strip_heredocs(cmd + "\n")):
        s = sw.Scan(text)
        for a, b in s.segments():
            if a > b:
                continue
            c = sw.cmd_index(s, a, b, CD, nested)
            if c is not None:
                v = next((s.w[i] for i in range(c + 1, b + 1)
                          if s.k[i] == "w" and (not s.w[i].startswith("-") or s.w[i] == "-")), "")
                out.append(("CD", "-" if s.w[c] == "popd" else v))
                continue
            g = sw.cmd_index(s, a, b, GIT, nested)
            if g is None:
                for i in range(a, b + 1):
                    if s.k[i] == "w" and s.w[i].startswith("GIT_DIR="):
                        out.append(("ENV", "GITDIR", s.w[i][8:]))
                    if s.k[i] == "w" and s.w[i].startswith("GIT_WORK_TREE="):
                        out.append(("ENV", "WORKTREE", s.w[i][14:]))
                continue
            sidx = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and s.w[i] in ("checkout", "switch")), None)
            if sidx is None:
                continue
            # checkout -- <path> is a file restore; a bare trailing -- is not.
            if s.w[sidx] == "checkout" and any(s.k[i] == "w" and s.w[i] == "--" and s.k[i + 1] == "w"
                                               for i in range(sidx + 1, b)):
                continue
            if re.search(r"(?:^|/)yadm\Z", s.w[g]):
                out.append(("DENY",))
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
    r = _expand_home(raw, home)
    if r is None:
        if raw.startswith("/"):
            r = raw
        elif not base:
            return None
        else:
            r = base + "/" + raw
    if not r.startswith("/"):
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


def _generic(prog):
    return Refuse(f"{NAME}: `checkout`/`switch` in $HOME switches the branch every shell and session on this "
                  f"machine sees until someone checks the old branch back out. Use a worktree instead:\n"
                  f"  {prog} worktree add -b <branch> <path> main\nthen cd into it and work there.")


def _checkout_home(payload, env):
    cmd = (payload.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not cmd:
        return
    events = _home_events(cmd)
    if not events:
        return
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

    cands, lost, env_targets = ([cwd] if cwd else []), not cwd, []
    for ev in events:
        if ev[0] == "DENY":
            raise _generic("yadm")
        if ev[0] == "ENV":
            env_targets.append(ev[1:])
        elif ev[0] == "CD":
            v = ev[1]
            if v == "":
                cands, lost = [home], False
            elif v == "-":
                lost = True
            else:
                if _HOMEISH.match(v):
                    lost = False
                if lost:
                    continue
                res, miss = yield from _resolve_all(v, cands, home)
                if not miss and res:
                    cands = res
                else:
                    lost = True
        else:
            if not home:
                raise Refuse(f"{NAME}: $HOME does not resolve, so a git checkout/switch can't be checked against it.")
            bases, blind, pinned = cands, lost, False
            for tk, tv in env_targets + ev[1]:
                if tk == "C":
                    bases, miss = yield from _resolve_all(tv, bases, home)
                    blind = blind or miss or not bases
                    continue
                pinned = True
                res, _ = yield from _resolve_all(tv, bases, home)
                for r in res:
                    if (tk == "GITDIR" and (yield from gitdir_is_home(r))) or (tk == "WORKTREE" and r == home):
                        raise _generic("git")
            # -C, --git-dir or --work-tree pin where the command resolves.
            if pinned:
                continue
            if blind:
                raise Refuse(f"{NAME}: can't tell which directory this git checkout/switch runs in (a cd, -C or "
                             "session cwd that doesn't resolve), so it can't be checked against $HOME. Use an "
                             "absolute path with git -C.")
            for d in bases:
                if (yield from targets_home(d)):
                    raise _generic("git")


# --- foreign --------------------------------------------------------------

def _pathish(t):
    t = re.sub(r"^--?[A-Za-z0-9][A-Za-z0-9-]*=", "", t, count=1)
    t = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=", "", t, count=1)
    if t in ("~", "$HOME", "${HOME}"):
        return t
    return t if "/" in t else ""


def _foreign_words(cmd):
    """("T",) where a text begins (its shell starts in the payload cwd),
    ("C", w) for a cd/pushd target, ("W", w) for any other path-shaped word or
    the word after -C, in order."""
    out = []
    for x, (text, nested) in enumerate(sw.texts_of(sw.strip_heredocs(cmd + "\n"))):
        s = sw.Scan(text)
        out.append(("T",))
        ncd, seen = 0, set()
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
    return out


class _Session:
    """This session's own worktrees: the cwd's toplevel, its scratchpad, and
    the per-session record. Every failure to read or write the record leaves
    the rule as strict as the cwd alone."""

    def __init__(self, payload, env, own_top, home):
        self.env, self.own_top, self.home = env, own_top, home
        sid, aid = payload.get("session_id"), payload.get("agent_id")
        self.sid = sid if isinstance(sid, str) else ""
        self.rec = None
        if self.sid:
            tag = re.sub(r"[^A-Za-z0-9_-]", "_", self.sid)
            if isinstance(aid, str) and aid:
                tag += "." + re.sub(r"[^A-Za-z0-9_-]", "_", aid)
            self.rec = os.path.join(env.get("TMPDIR") or "/tmp", "languette-guard-worktrees." + tag)

    @staticmethod
    def mine(f):
        """A regular file owned by this user, not a symlink."""
        try:
            st = os.lstat(f)
        except OSError:
            return False
        return os.path.isfile(f) and not os.path.islink(f) and st.st_uid == os.geteuid()

    @staticmethod
    def inode(top):
        try:
            return os.stat(os.path.join(top, ".git")).st_ino
        except OSError:
            return None

    def under_scratch(self, d):
        return bool(self.sid) and f"/{self.sid}/" in f"/{d}/"

    def recorded(self, top):
        if not self.rec or not self.mine(self.rec):
            return False
        ino = self.inode(top)
        if ino is None:
            return False
        try:
            with open(self.rec, encoding="utf-8") as f:
                return f"{top}\t{ino}" in f.read().splitlines()
        except OSError:
            return False

    @staticmethod
    def write_new(f, text):
        """Create `f` afresh, private, never following a link left at that name."""
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
        except OSError:
            return
        try:
            fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            return
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    def arrive(self, own_linked):
        """Record the cwd's toplevel when this call reached it by a vouched
        route; consume the arrival the previous call left, exactly once."""
        if not self.rec:
            return
        adopt = False
        if not os.path.lexists(self.rec):
            try:                               # O_EXCL: two first calls racing must not truncate each other
                os.close(os.open(self.rec, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
                adopt = True
            except OSError:
                pass
        if not self.mine(self.rec):
            self.rec = None
            return
        arrival = self.rec + ".arrive"
        if not adopt and own_linked and self.mine(arrival):
            try:
                with open(arrival, encoding="utf-8") as f:
                    for a in f.read().splitlines():
                        if a == "enter" or (a and (a + "/").startswith(self.own_top + "/")):
                            adopt = True
            except OSError:
                pass
        try:
            os.unlink(arrival)
        except OSError:
            pass
        if adopt and own_linked and not self.under_scratch(self.own_top) and not self.recorded(self.own_top):
            ino = self.inode(self.own_top)
            if ino is not None:
                try:
                    with open(self.rec, "a", encoding="utf-8") as f:
                        f.write(f"{self.own_top}\t{ino}\n")
                except OSError:
                    pass

    def scratchpad(self):
        if self.sid:
            for root in (self.env.get("CLAUDE_CODE_TMPDIR") or "/nonexistent", self.env.get("TMPDIR") or "/nonexistent",
                         os.path.join(self.env.get("HOME") or "", ".local/state/claude-tmpdir")):
                for d in sorted(glob.glob(os.path.join(glob.escape(root), "claude-*", "*", glob.escape(self.sid),
                                                       "scratchpad"))):
                    if os.path.isdir(d):
                        return d
        return "<scratchpad>"


def _recipe(sess, d):
    gcd = yield from _git("/", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir")
    scratch = sess.scratchpad()
    return f"git --git-dir={gcd or '<git-dir>'} worktree add {scratch}/<name> && cd {scratch}/<name>"


def _claim(env, ft):
    """("live", line), ("stale", None) or ("unknown", None), from one
    claim-stamp.sh read; anything unclear is unknown, never stale."""
    if env.get("GITHUB_ACTIONS") or env.get("CI") or env.get("CLAUDE_CLAIM_STAMP", "on") == "off":
        return "unknown", None
    binary = env.get("CLAIM_STAMP_BIN") or (yield Need("which", "claim-stamp.sh"))
    if not binary or not os.access(binary, os.X_OK) or not os.path.isfile(binary):
        return "unknown", None
    if not (yield Need("which", "gh")):
        return "unknown", None
    out = yield Need("git", "sh", "/", binary, "read", "-C", ft)
    if not out or out == "no card" or out.startswith("unverified"):
        return "unknown", None
    rows = [line.split("\t") for line in out.splitlines()]
    live = next(("\t".join(r) for r in rows if r[0] == "live"), None)
    if live:
        return "live", live
    return ("stale", None) if any(r[0] == "stale" for r in rows) else ("unknown", None)


def _deny_path(sess, env, word, ft):
    branch = yield from _git("/", "-C", ft, "symbolic-ref", "-q", "--short", "HEAD")
    state, live = (yield from _claim(env, ft)) if branch else ("unknown", None)
    head = f"{NAME}: `{word}` is inside {ft}, a git worktree this session does not own."
    if state == "live":
        f = live.split("\t")
        who = f"session `{f[1] if len(f) > 1 else ''}` on `{f[2] if len(f) > 2 else ''}`, claimed {f[3] if len(f) > 3 else ''} ago"
        raise Refuse(f"{head} {who} -- another session is live in there (claim-stamp.sh); it may be archived out "
                     "from under you mid-turn if you reach in (an agent once lost a worktree that way).\n"
                     f"To read that branch, stay here: `git log/diff/show {branch}`, `git show {branch}:<path>` -- "
                     "worktrees of a repo share objects and refs.\nReport it and stop. Do not take the worktree away "
                     "from them.")
    if state == "stale":
        raise Refuse(f"{head} claim-stamp.sh finds no live claim on `{branch}` -- the session that held this "
                     "worktree looks dead, not merely between turns.\nThat does not make it yours to clear: reaching "
                     "in and archiving it out from under an owner who turns out to still be there is how an agent "
                     "once lost a worktree. Report this to the user with the cleanup command: "
                     f"`git worktree remove {ft}` (run from a worktree other than this one) -- git itself refuses if "
                     "anything uncommitted is left inside, and the branch survives the removal either way, so nothing "
                     "is lost if the stale read was wrong.\nTo read that branch meanwhile, stay here: "
                     f"`git log/diff/show {branch}`, `git show {branch}:<path>`.")
    recipe = yield from _recipe(sess, ft)
    raise Refuse(f"{head} A hand-off carries a branch, an issue and a PR -- never a directory; another session may "
                 "still be running in there, and it may be archived out from under you mid-turn (an agent once lost "
                 "a worktree that way).\nTo read that branch, stay here: `git log/diff/show <branch>`, "
                 "`git show <branch>:<path>` -- worktrees of a repo share objects and refs.\n"
                 f"To work on it, take your own worktree, one command, from anywhere: `{recipe}`, then "
                 f"`git merge --ff-only {branch or '<branch>'}` inside it. If --ff-only fails, the histories have "
                 "diverged: report that and stop.\nIf you made this worktree yourself in an earlier call, that is "
                 "why: a worktree is yours only when the command that creates it also `cd`s into it, or it lives "
                 "under your scratchpad. The recipe above does both.\nWorktree hygiene is the user's call, not a "
                 "session's.")


def _resolve_dir(raw, base, home):
    """(canonical nearest existing directory, the part below it that does not
    exist yet), or ("", "") when the word can't be judged."""
    r = _expand_home(raw, home)
    if r is None:
        if raw.startswith("/"):
            r = raw
        elif not base:
            return "", ""
        else:
            r = base + "/" + raw
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
        raise Refuse(f"{NAME}: `{raw}` has a `..` after a directory that does not exist, so where it lands cannot "
                     "be resolved. Spell the path without `..`.")
    return (yield Need("path", "realpath", r)), rest


def _foreign(payload, env):
    # git is what every foreignness answer is asked of: without it, every path
    # would read as nobody's worktree.
    if not (yield Need("which", "git")):
        raise Refuse(f"{NAME}: git is missing, so worktree ownership cannot be checked. This is a gate and fails "
                     "closed.")
    tool = payload.get("tool_name")
    pcwd = payload.get("cwd")
    if not isinstance(pcwd, str) or not pcwd:
        return
    home = yield from _canon(env.get("HOME") or "")
    if not home:
        return
    own_top = (yield from _git("/", "-C", pcwd, "rev-parse", "--show-toplevel")) or ""
    sess = _Session(payload, env, own_top, home)
    sess.arrive(bool(own_top) and (yield Need("path", "isfile", os.path.join(own_top, ".git"))))
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}

    if tool == "EnterWorktree":
        p = ti.get("path")
        if not p:
            if sess.rec:                       # a fresh worktree of the session's making: the next cwd is own
                sess.write_new(sess.rec + ".arrive", "enter")
            return
        recipe = yield from _recipe(sess, p)
        raise Refuse(f"{NAME}: EnterWorktree(path=...) enters a worktree that already exists, with no check on whose "
                     "it is -- the tool only requires that the path appear in `git worktree list`. That is how an "
                     "agent once lost a worktree mid-turn: the session that owned it was archived and the directory "
                     "went away underneath the session that had attached to it.\nTake your own instead, one command, "
                     f"from anywhere: `{recipe}`, then `git merge --ff-only <branch>` inside it to bring the branch "
                     "you are resuming into your own directory. If --ff-only fails, the histories have diverged: "
                     "report that and stop.\nNothing needs the other directory -- worktrees of a repo share objects "
                     "and refs, so `git log/diff/show <branch>` and `git show <branch>:<path>` read it from here.")

    def foreign_top(d):
        t = yield from _git("/", "-C", d, "rev-parse", "--show-toplevel")
        if not t or t == own_top or not (yield Need("path", "isfile", os.path.join(t, ".git"))):
            return None
        if sess.under_scratch(t) or sess.recorded(t):
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
    arrivals, vcwd, n = [], pcwd, 0
    for ev in _foreign_words(cmd):
        if ev[0] == "T":
            vcwd = pcwd
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
    if sess.rec and arrivals:
        sess.write_new(sess.rec + ".arrive", "\n".join(arrivals))


CONTROLS = (("CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_CHECKOUT_HOME", _checkout_home),
            ("CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_FOREIGN", _foreign))


def check(payload, env=None):
    env = env if env is not None else os.environ
    if not isinstance(payload, dict):
        return None
    for option, control in CONTROLS:
        if env.get(option) == "false":
            continue
        try:
            yield from control(payload, env)
        except Refuse as r:
            return deny(str(r))
    return None
