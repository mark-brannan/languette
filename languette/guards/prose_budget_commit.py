"""prose-budget-commit: before a `git commit`, run the prose-budget engine and
warn on a finding, so documentation bloat is caught as it is written. CI is
the gate; this never blocks the commit. The spec is
features/prose-budget-commit.feature.

The engine is the command the prose_budget_command option names (an absolute
path, a path relative to the commit's cwd, or a bare name on PATH), else
`prose-budget` on PATH. Nothing is bundled: no engine is a no-op, as is an
engine crash. `--staged` checks the index; a commit that reaches past it (-a,
a pathspec, an `add` in the same command, -p, --pathspec-from-file) also runs
`--file` on what it would commit. Exit 1 is a finding and warns; exit 2 (a bad
budgets config, or an engine too old for --staged/--file) warns and says so.
Both checks' warnings arrive together: the commit is not blocked, so there is
no retry to show the second.

Silent on what it cannot resolve: a `cd`/`-C` target, a pathspec word, a
directory pathspec, a second commit in a different directory. A failed
`rev-parse`/`diff`/`ls-files` adds no files to the `--file` run; the files
already gathered are still checked. `yadm` is recognised as git's wrapper
word, and is run only when the command named it.
"""

import re

from languette import paths
from languette import scan as sw
from languette.verdict import Need, context

NAME = "prose-budget-commit"
OPTION = "CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMAND"
DEFAULT = "prose-budget"
ENGINE_TIMEOUT = 50                 # under Claude Code's 60 s hook timeout; past it the engine counts as crashed
GIT_TIMEOUT = 10
GIT = re.compile(r"(?:^|/)(?:git|yadm)\Z")
_ADD_QUIET = re.compile(r"-[nv]+\Z|--(?:dry-run|verbose)\Z")
_VALUED = frozenset("-m --message -F --file -C --reuse-message -c --reedit-message --fixup --squash --author "
                    "--date --template".split())
CI = "CI fails on this; fix before the push."


def _warn(why):
    return f"{NAME}: {why}"


def _done(notes):
    """The warnings, joined, as a call that still runs; None when there are none."""
    return context("\n\n".join(notes)) if notes else None


def _join(base, step):
    return step if base == "" or step.startswith("/") else base + "/" + step


def _wide(p):
    """A directory, magic or glob pathspec names more than itself."""
    return p in (".", "*", ":") or re.search(r"[*?\[]", p) is not None or p.endswith("/") or p.startswith(":")


class _Commits:
    """The git/yadm commits in a command: the first one's cd, -C dir and wrapper
    word; the pathspecs it reaches past the index with; whether it reaches every
    unstaged tracked change (allflag) or untracked files too (allnew); whether a
    pathspec cannot be resolved (bad); whether a second commit runs elsewhere (multi)."""

    def __init__(self, doc):
        self.seen = self.multi = self.allflag = self.allnew = self.bad = self.addseen = False
        self.paths, self.cd, self.ctx = [], "", None
        self.ccd = self.cdir = self.cbin = self.addctx = None
        for text, nested in doc.texts():
            s = self.s = doc.scan(text)
            for a, b in s.segments():
                if a <= b:
                    self._segment(a, b, nested)

    def _w(self, i):
        return self.s.w[i] if i < len(self.s.w) else ""

    def _isbad(self, i):
        return self.s.k[i] == "q" or self.s.live[i]

    def _add_path(self, p, add):
        if _wide(p):
            self.allflag = True
            self.allnew = self.allnew or add     # only an add can stage a brand-new file
        else:
            self.paths.append(p)

    def _collect_add(self, lo, hi):
        w = self.s.w
        for i in range(lo, hi + 1):
            if w[i] == "--":
                continue
            if w[i].startswith("-"):
                if re.fullmatch(r"--(?:a|al|all)", w[i]) or (re.fullmatch(r"-[A-Za-z]+", w[i]) and "A" in w[i]):
                    self.allflag = self.allnew = True
                elif re.fullmatch(r"--(?:u|up|upd|upda|updat|update)", w[i]) or \
                        (re.fullmatch(r"-[A-Za-z]+", w[i]) and "u" in w[i]):
                    self.allflag = True
                elif _ADD_QUIET.match(w[i]):
                    pass                       # -n/-v change nothing about what gets staged
                else:
                    self.allflag = self.allnew = True   # -f, -p, -i, or a flag this does not know: widen
                continue
            if self._isbad(i):
                self.bad = True
                continue
            self._add_path(w[i], True)

    def _commit_tail(self, lo, hi):
        w = self.s.w
        i = lo
        while i <= hi:
            if w[i] == "--":
                for j in range(i + 1, hi + 1):
                    if self._isbad(j):
                        self.bad = True
                    else:
                        self._add_path(w[j], False)
                return
            if w[i] == "--all" or w[i].startswith("--pathspec-from-file="):
                self.allflag = True
                i += 1
            elif w[i] == "--pathspec-from-file":
                self.allflag = True
                i += 2
            elif w[i] in ("--patch", "--interactive"):
                self.allflag = self.allnew = True
                i += 1
            elif w[i] in _VALUED:
                i += 2
            elif re.fullmatch(r"-[A-Za-z]+", w[i]):
                # A short-option cluster: the first letter that takes a value takes the
                # rest of the word, or the next word when it is the last letter.
                m = re.search(r"[mFcCt]", w[i])
                flags = w[i][1:m.start()] if m else w[i][1:]
                if "a" in flags:
                    self.allflag = True
                if "p" in flags:
                    self.allflag = self.allnew = True
                i += 2 if m and m.start() == len(w[i]) - 1 else 1
            elif w[i].startswith("-"):
                i += 1
            else:
                if self._isbad(i):
                    self.bad = True
                else:
                    self._add_path(w[i], False)
                i += 1

    def _segment(self, lo, hi, nested):
        s = self.s
        if s.w[lo] == "cd" and lo + 1 < len(s.w) and s.k[lo + 1] == "w":
            self.cd = _join(self.cd, s.w[lo + 1])
        g = sw.cmd_index(s, lo, hi, GIT, nested)
        if g is None:
            return
        self.bin = s.w[g]
        i, d = g + 1, ""
        while i <= hi and s.w[i].startswith("-"):
            if s.w[i] == "-C":
                d = _join(d, self._w(i + 1))
                i += 1
            elif s.w[i] in ("-c", "--git-dir", "--work-tree", "--namespace"):
                i += 1
            i += 1
        if i <= hi and s.w[i] in ("add", "stage"):
            self.addseen, self.addctx = True, (self.cd, d)
            self._collect_add(i + 1, hi)
        elif i <= hi and s.w[i] == "commit":
            self._commit_tail(i + 1, hi)
            self._seen(d)
        elif i <= hi and s.w[i] == "merge" and "--continue" in s.w[i + 1:hi + 1]:
            self._seen(d)

    def _seen(self, d):
        """A commit (or a merge --continue) in its context; a later one elsewhere is multi."""
        ctx = (self.cd, d, "yadm" if re.search(r"(?:^|/)yadm\Z", self.bin) else "git")
        if self.addseen and self.addctx != (self.cd, d):
            self.allflag = self.allnew = True
        if not self.seen:
            self.seen, self.ctx, self.ccd, self.cdir, self.cbin = True, ctx, self.cd, d, self.bin
        elif ctx != self.ctx:
            self.multi = True


def _engine(env, cwd):
    """The engine's path, or None: relative to the commit's cwd, or a bare name on PATH."""
    name = env.get(OPTION) or DEFAULT
    if name.startswith("/"):
        path = name
    elif "/" in name:
        path = cwd + "/" + name
    else:
        path = yield Need("which", name)
    if path and (yield Need("path", "executable", path)):
        return path
    return None


def check(doc):
    payload, env = doc.payload, doc.env
    if payload.get("tool_name") != "Bash":
        return None
    ti = payload.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str) or not cmd:
        return None
    cwd = payload["cwd"]
    engine = yield from _engine(env, cwd)
    if engine is None:
        return None
    c = _Commits(doc)
    if not c.seen:
        return None
    if c.multi:                         # one check cannot serve two repositories
        return None
    d = cwd
    for step in (c.ccd, c.cdir):
        if not step:
            continue
        new = paths.lexical(step if step.startswith("/") else d + "/" + step)
        if not ((yield Need("path", "isdir", d)) and (yield Need("path", "isdir", new))):
            return None
        d = new
    if c.bad:
        return None
    for p in c.paths:
        if p and (yield Need("path", "isdir", p if p.startswith("/") else d + "/" + p)):
            return None                 # this guard does not expand a directory pathspec

    notes = []
    found = yield from _run_engine(engine, d, ["--staged"])
    if found is not None:
        rc, out = found
        if rc == 1:
            notes.append(_warn(f"prose-budget --staged found:\n{out}\n{CI}"))
        elif rc == 2:
            notes.append(_warn("prose-budget --staged could not check the staged prose (exit 2: a bad budgets "
                               f"config, or an engine too old for --staged):\n{out}\nA bad config fails CI too; "
                               "fix it, or update the engine, before the push."))

    files = list(c.paths)
    if c.allflag or c.allnew:
        files += yield from _unstaged(c, d)
    files = ["./" + f if f.startswith("-") else f for f in files if f]
    if not files:
        return _done(notes)
    found = yield from _run_engine(engine, d, ["--file", *files])
    if found is not None:
        rc, out = found
        if rc == 1:
            notes.append(_warn("this commit reaches prose outside the staged index (git commit -a/--all, a pathspec "
                               "commit, or a git add in the same command) -- checked those files directly and "
                               f"prose-budget found:\n{out}\n{CI}"))
        elif rc == 2:
            notes.append(_warn("prose-budget --file could not check those files (exit 2: a bad budgets config, or "
                               f"an engine too old for --file):\n{out}\nA bad config fails CI too; fix it, or "
                               "update the engine, before the push."))
    return _done(notes)


def _unstaged(c, d):
    """The files a commit that reaches past the index would add, as far as git can
    list them: a step that fails ends the listing, and what it had gathered stands."""
    # -a and a pattern add stage repo-wide, so these listings are anchored to the
    # repo root. The wrapper word is the command's own and may be anyone's: only
    # which CLI it names is trusted, found fresh on PATH.
    binary = yield Need("which", "yadm" if re.search(r"(?:^|/)yadm\Z", c.cbin) else "git")
    if not binary:
        return []
    try:
        rc, out, _ = yield Need("run", d, GIT_TIMEOUT, binary, "rev-parse", "--show-toplevel")
    except Exception:  # noqa: BLE001
        rc, out = None, ""
    if rc != 0:
        return []
    root = out.rstrip("\n")
    listings = []
    if c.allflag:
        listings.append(["diff", "-z", "--name-only", "--diff-filter=d"])          # unstaged tracked changes
    if c.allnew:
        listings.append(["ls-files", "-z", "--others", "--exclude-standard"])      # new untracked files
    found = []
    for argv in listings:
        try:
            rc, out, _ = yield Need("run", root, GIT_TIMEOUT, binary, *argv)
        except Exception:  # noqa: BLE001
            rc, out = None, ""
        if rc != 0 or "\n" in out:    # a failed listing, or a name with a newline that cannot reach the engine
            break
        found += [root + "/" + f for f in out.split("\0") if f]
    return found


def _run_engine(engine, d, args):
    """(exit code, its output) or None when the engine could not run: a crash is a no-op."""
    try:
        rc, out, err = yield Need("run", d, ENGINE_TIMEOUT, engine, *args)
    except Exception:  # noqa: BLE001
        return None
    return rc, (out + err).rstrip("\n")
