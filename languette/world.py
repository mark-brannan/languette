"""The one module that touches the disk, subprocesses, the clock or the network.

The runner (run.py) holds one World per payload and asks it for each Need a
guard yields (languette.verdict.Need lists the kinds). World owns the budget:
one timeout per kind of fact, the ruleset cache, the spent-file lock.
Standard library only.
"""

import fcntl
import glob
import json
import os
import re
import shutil
import subprocess
import time
from urllib.parse import quote

GIT_TIMEOUT = 5
GH_TIMEOUT = 10
PR_LIST_TIMEOUT = 25                # past the `timeout 20` guard-git-stacked-base wraps gh pr list in
SPENT = ".languette-ask"            # appended to the transcript path
RECORDS = "decisions.jsonl"         # under $XDG_STATE_HOME/languette
RECORDS_MAX = 8 << 20               # bytes; past it the file becomes .1, the old .1 goes
RECORDS_WAIT = 0.1                  # seconds a writer waits on the lock before dropping its record
KINDS = frozenset("git gh-api pr-list which read path cwd clock ruleset-cache ruleset-keep claim worktree run door "
                  "send-state send-keep".split())
DOOR = "languette-guard-github-issues."   # + the session id, under $TMPDIR
SEND_STATE = "languette-guard-cross-session-send."   # + session id, under $TMPDIR
SEND_SUBAGENTS_MAX = 500            # names and ids kept per session; the oldest go first
# What a failed write, or a first write that is not a session start, leaves:
# no subagents known, the door open.
SEND_LOST = '{"subagents": [], "read": "an unknown tool (this session\'s state was lost)"}'


class World:
    def __init__(self, env, payload):
        self.env, self.payload = env, payload
        self._seen = None                      # the transcript's scan; it only grows

    def answer(self, need):
        if need.kind not in KINDS:
            raise ValueError(f"no such fact: {need!r}")
        return getattr(self, "_" + need.kind.replace("-", "_"))(*need.args)

    # --- facts -----------------------------------------------------------

    def _git(self, prog, cwd, *argv):
        try:
            r = subprocess.run([prog, *argv], cwd=cwd, env=self.env, capture_output=True, text=True,
                               timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        out = r.stdout.strip()
        return out if r.returncode == 0 and out else None

    def _gh_api(self, path):
        try:
            r = subprocess.run(["gh", "api", path], env=self.env, capture_output=True, text=True,
                               timeout=GH_TIMEOUT, stdin=subprocess.DEVNULL)
            body = json.loads(r.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None, None
        if r.returncode == 0:
            return 200, body
        status = body.get("status") if isinstance(body, dict) else None
        return (int(status), body) if isinstance(status, str) and status.isdigit() else (None, None)

    def _pr_list(self, cwd, *argv):
        try:
            r = subprocess.run(list(argv), cwd=cwd, env=self.env, capture_output=True, text=True,
                               timeout=PR_LIST_TIMEOUT, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            return None
        out = r.stdout.strip()
        return out if r.returncode == 0 and out else None

    def _which(self, name):
        return shutil.which(name, path=os.pathsep.join(os.get_exec_path(self.env)))

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _path(self, op, path):
        if op == "executable":
            return os.path.isfile(path) and os.access(path, os.X_OK)
        if op not in ("isdir", "isfile", "islink", "exists", "lexists", "realpath"):
            raise ValueError(f"no path fact {op!r}")
        return getattr(os.path, op)(path)

    def _run(self, cwd, timeout, *argv):
        r = subprocess.run(list(argv), cwd=cwd, env=self.env, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        dec = lambda b: b.decode("utf-8", "surrogateescape")
        return r.returncode, dec(r.stdout), dec(r.stderr)

    def _door(self, op, session, call=""):
        """guard-github-issues' door for one session: a file under $TMPDIR that a
        human turn opens and one identifier write claims, then spends.

            open           -> None: the door is a fresh plain file, any claim dropped
            spend          -> None: door and claim both gone
            claim          -> True when this call took the open door; False when
                              another call won it first; else the id the standing
                              claim holds ("" when there is none)
            take           -> True when this call took the standing claim over

        A taker renames the file to a name of its own (atomic: one racer wins)
        and stamps its id in a file made fresh, so a link planted at the door
        or the claim is removed, never written through."""
        door = os.path.join(self.env.get("TMPDIR") or "/tmp", DOOR + session)
        held = door + ".held"
        if op in ("open", "spend"):
            for f in (door, held):
                try:
                    os.unlink(f)
                except FileNotFoundError:
                    pass
            if op == "open":
                os.close(os.open(door, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            return None
        if op == "claim":
            if os.path.lexists(door):
                return self._take(door, door, call)
            if not os.path.isfile(held):
                return ""
            try:
                with open(held, encoding="utf-8", errors="replace") as f:
                    return f.read()
            except OSError:
                return ""
        if op == "take":
            return self._take(held, door, call)
        raise ValueError(f"no door op {op!r}")

    @staticmethod
    def _take(src, door, call):
        mine, held = f"{door}.claim.{os.getpid()}", door + ".held"
        try:
            os.rename(src, mine)
        except OSError:
            return False
        for f in (mine, held):
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass
        fd = os.open(mine, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(call)
        os.rename(mine, held)
        return True

    def _cwd(self):
        return os.getcwd()

    def _clock(self):
        return time.time()

    def _ruleset_file(self, slug, branch):
        base = self.env.get("XDG_CACHE_HOME") or os.path.join(self.env.get("HOME") or "/", ".cache")
        return os.path.join(base, "languette", "rulesets", slug, quote(branch, safe=""))

    def _ruleset_cache(self, slug, branch):
        f = self._ruleset_file(slug, branch)
        try:
            with open(f) as fh:
                return os.fstat(fh.fileno()).st_mtime, fh.read().strip()
        except (OSError, ValueError):              # unreadable or garbled: a miss
            return None

    def _ruleset_keep(self, slug, branch, text):
        f = self._ruleset_file(slug, branch)
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as fh:
                fh.write(text + "\n")
        except OSError:
            pass                               # a cache that can't be written only costs a later ask

    # --- guard-worktrees' per-session record -----------------------------
    # ${TMPDIR:-/tmp}/languette-guard-worktrees.<session>[.<agent>] lists the
    # toplevels this session reached by a vouched route, one "<top>\t<inode of
    # top/.git>" per line; <record>.arrive is what the previous call left for
    # this one. Every failure to read or write leaves the guard's rule as
    # strict as the cwd alone.

    def _worktree(self, op, *args):
        if op not in ("arrive", "recorded", "keep", "leave", "scratchpad"):
            raise ValueError(f"no worktree fact {op!r}")
        return getattr(self, "_wt_" + op)(*args)

    @staticmethod
    def _wt_mine(f):
        """A regular file owned by this user, not a symlink."""
        try:
            st = os.lstat(f)
        except OSError:
            return False
        return os.path.isfile(f) and not os.path.islink(f) and st.st_uid == os.geteuid()

    @staticmethod
    def _wt_inode(top):
        try:
            return os.stat(os.path.join(top, ".git")).st_ino
        except OSError:
            return None

    def _wt_arrive(self, rec, own_top):
        """(usable, adopt): the record is this user's; and this call reached
        `own_top` by a vouched route (the session's first call, or an arrival
        the previous call left: `enter`, or a path under own_top). The arrival
        is consumed exactly once."""
        adopt = False
        if not os.path.lexists(rec):
            try:                               # O_EXCL: two first calls racing must not truncate each other
                os.close(os.open(rec, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
                adopt = True
            except OSError:
                pass
        if not self._wt_mine(rec):
            return False, False
        arrival = rec + ".arrive"
        if not adopt and own_top and self._wt_mine(arrival):
            try:
                with open(arrival, encoding="utf-8") as f:
                    for a in f.read().splitlines():
                        if a == "enter" or (a and (a + "/").startswith(own_top + "/")):
                            adopt = True
            except OSError:
                pass
        try:
            os.unlink(arrival)
        except OSError:
            pass
        return True, adopt

    def _wt_recorded(self, rec, top):
        if not self._wt_mine(rec):
            return False
        ino = self._wt_inode(top)
        if ino is None:
            return False
        try:
            with open(rec, encoding="utf-8") as f:
                return f"{top}\t{ino}" in f.read().splitlines()
        except OSError:
            return False

    def _wt_keep(self, rec, top):
        ino = self._wt_inode(top)
        if ino is None:
            return None
        try:
            with open(rec, "a", encoding="utf-8") as f:
                f.write(f"{top}\t{ino}\n")
        except OSError:
            pass

    @staticmethod
    def _wt_leave(rec, text):
        """Create <rec>.arrive afresh, private, never following a link left at that name."""
        f = rec + ".arrive"
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

    def _wt_scratchpad(self, sid):
        """The session's scratchpad directory, or None."""
        for root in (self.env.get("CLAUDE_CODE_TMPDIR") or "/nonexistent", self.env.get("TMPDIR") or "/nonexistent",
                     os.path.join(self.env.get("HOME") or "", ".local/state/claude-tmpdir")):
            for d in sorted(glob.glob(os.path.join(glob.escape(root), "claude-*", "*", glob.escape(sid), "scratchpad"))):
                if os.path.isdir(d):
                    return d
        return None

    def _claim(self, wants):
        """Spend one approval per run for this tool call, atomically. `wants` is
        {approve_label: runs}. Returns ({label: approvals that are this call's or
        unspent}, spent): when every label has its runs' worth they are recorded
        against the call and `spent` is True; otherwise nothing is recorded and
        the guard says what is missing. Read, check and record happen under an
        exclusive lock on the spent file, so parallel hooks cannot both pass on
        one click. A click recorded against a call the transcript shows never ran
        (the user declined it, or a hook denied it) is unspent again; one already
        recorded against this call counts for it, so one click is one run,
        whichever guard asked and however often. Raises OSError when the payload
        names no transcript, or it or the spent file cannot be read or written."""
        call = self.payload.get("tool_use_id")
        call = call if isinstance(call, str) and call else None
        answers, never_ran = self._scan()
        with open(self._transcript() + SPENT, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            held = [r for r in map(_record, f) if r and (r["call"] is None or r["call"] not in never_ran)]
            spent = {r["approval"] for r in held}
            approved = {}
            for label in wants:
                mine = [r["approval"] for r in held if call and r["call"] == call and r["label"] == label]
                approved[label] = mine + [i for i in _yes(answers, label) if i not in spent]
            if any(len(approved[label]) < n for label, n in wants.items()):
                return approved, False
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.writelines(json.dumps({"t": now, "label": label, "approval": i, "call": call}) + "\n"
                         for label, n in wants.items() for i in approved[label][:n]
                         if i not in spent)
            return approved, True

    def _send_file(self, session):
        base = self.env.get("TMPDIR") or "/tmp"
        return os.path.join(base, SEND_STATE + re.sub(r"[^A-Za-z0-9_-]", "_", session))

    def _send_state(self, session):
        """guard-cross-session-send's state for `session`: {"subagents": [the
        names and ids of this session's subagents], "read": the tool that read
        untrusted content in this session, or None}. Raises OSError or
        ValueError when it is missing, a link, someone else's, open to others,
        or garbled."""
        fd = os.open(self._send_file(session), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, encoding="utf-8") as f:
            _own(f)
            fcntl.flock(f, fcntl.LOCK_SH)
            st = json.load(f)
        if not (isinstance(st, dict) and isinstance(st.get("subagents"), list)
                and (st.get("read") is None or isinstance(st.get("read"), str))):
            raise ValueError("guard-cross-session-send state has the wrong shape")
        return st

    def _send_keep(self, session, op, arg):
        """Update that state under an exclusive lock: op "clear" writes a closed
        door with no subagents (a new or cleared session), "read" opens it naming `arg`, "names"
        records the subagent names and ids in `arg`. Only "clear" makes a
        closed door: a file another op creates starts as SEND_LOST. A link
        planted at the path is removed, never written through. A write that
        fails leaves SEND_LOST in its place where it can."""
        path = self._send_file(session)
        try:
            if os.path.islink(path):
                os.unlink(path)
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "r+", encoding="utf-8") as f:
                _own(f)
                fcntl.flock(f, fcntl.LOCK_EX)
                text = f.read()
                try:
                    st = json.loads(text) if text.strip() else None
                except ValueError:
                    st = None
                if not isinstance(st, dict) or not isinstance(st.get("subagents"), list):
                    st = json.loads(SEND_LOST)
                if op == "clear":
                    st = {"subagents": [], "read": None}   # a fresh context has no subagents yet
                elif op == "read":
                    st["read"] = arg
                elif op == "names":
                    st["subagents"] = ([s for s in st["subagents"] if s not in arg] + list(arg))[-SEND_SUBAGENTS_MAX:]
                else:
                    raise ValueError(f"no send-keep op {op!r}")
                f.seek(0)
                f.truncate()
                f.write(json.dumps(st) + "\n")
        except Exception:
            try:
                os.unlink(path)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w") as f:
                    f.write(SEND_LOST + "\n")
            except OSError:
                pass
            raise

    # --- acts ------------------------------------------------------------

    def keep(self, rec):
        """Append one decision record (languette.record). Silent on any failure:
        a record never changes the verdict, nor holds it up past RECORDS_WAIT.
        Lines go in whole under an exclusive lock, so parallel hooks cannot
        interleave them; rotation happens under the same lock, and a writer that
        waited on a file rotated away from it reopens rather than rotating the
        new one."""
        try:
            base = self.env.get("XDG_STATE_HOME") or os.path.join(self.env["HOME"], ".local", "state")
            d = os.path.join(base, "languette")
            os.makedirs(d, mode=0o700, exist_ok=True)
            if os.stat(d).st_mode & 0o077:
                os.chmod(d, 0o700)             # made before, by hand or an older umask
            path = os.path.join(d, RECORDS)
            line = (json.dumps(rec, separators=(",", ":")) + "\n").encode("utf-8", "surrogatepass")
            deadline = time.monotonic() + RECORDS_WAIT
            while True:
                fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                try:
                    while True:
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() > deadline:
                                return             # a stuck holder costs this record, not the call
                            time.sleep(0.002)
                    st = os.fstat(fd)
                    try:
                        moved = os.stat(path).st_ino != st.st_ino   # rotated while we waited
                    except FileNotFoundError:
                        moved = True               # rotated, and the new file not made yet
                    if moved:
                        if time.monotonic() > deadline:
                            return
                        continue
                    if st.st_mode & 0o077:
                        os.fchmod(fd, 0o600)
                    if st.st_size + len(line) > RECORDS_MAX and st.st_size:
                        os.replace(path, path + ".1")
                        continue               # to the new file, which this writer makes
                    done = 0
                    try:
                        while done < len(line):
                            done += os.write(fd, line[done:])
                    except OSError:
                        os.ftruncate(fd, st.st_size)   # no half line for the next writer to join
                    return
                finally:
                    os.close(fd)
        except Exception:  # noqa: BLE001
            pass

    # --- the transcript --------------------------------------------------

    def _transcript(self):
        tp = self.payload.get("transcript_path")
        if not isinstance(tp, str) or not tp:
            raise OSError("the payload has no transcript_path")
        return tp

    def _scan(self):
        if self._seen is None:
            self._seen = scan(self._transcript())
        return self._seen


def _own(f):
    """Refuse a state file another user made, or one others may write: on a
    shared /tmp it could have been planted to say the door is closed."""
    st = os.fstat(f.fileno())
    if st.st_uid != os.geteuid() or st.st_mode & 0o022:
        raise PermissionError("guard-cross-session-send state is not this user's alone")


def _record(line):
    """One spent-file line: a JSON record, or a bare approval id from before calls
    were recorded (spent for good)."""
    line = line.strip()
    if not line:
        return None
    try:
        r = json.loads(line)
    except ValueError:
        return {"label": None, "approval": line, "call": None}
    return r if isinstance(r, dict) and isinstance(r.get("approval"), str) else None


# --- reading a transcript ---------------------------------------------------

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text") if isinstance(c, dict) else c) for c in content)
    return ""


def _questions(inp):
    qs = inp.get("questions") if isinstance(inp, dict) else None
    return [q["question"] for q in qs or () if isinstance(q, dict) and isinstance(q.get("question"), str)]


def _said(answer, label):
    """Did the user answer one of the ask's questions with exactly `label`? Only
    the answer side counts: the question is the agent's text and may quote the
    label. Claude Code records the answers structured beside the result; the
    result text, `"<question>"="<answer>"` pairs, is read only for a
    one-question ask, where no question can embed another's pair."""
    questions, structured, text = answer
    if structured is not None:
        return any(structured.get(q) == label for q in questions)
    if len(questions) != 1:
        return False
    return re.search(r'(?:^|: )' + re.escape(f'"{questions[0]}"="{label}"') + r'(?:\.|$)', text, re.M) is not None


def _yes(answers, label):
    return [i for i, answer in answers if _said(answer, label)]


# A call that never ran, by the result Claude Code records for it: the user
# declined the prompt, a hook or the classifier denied it, or a languette guard
# did. Any other error is a call that ran and failed, and keeps its click.
_REFUSED = re.compile(r"(?:The user doesn't want to proceed with this tool use|PreToolUse:|"
                      r"Permission for this action was denied|(?:languette|ask-first|guard-[a-z0-9-]+): )")


def _never_ran(rec, c):
    return rec.get("toolUseResult") == "User rejected tool use" or _REFUSED.match(_text(c.get("content"))) is not None


def scan(transcript):
    """(answers, never_ran) from a transcript: answers is [(ask id, (questions,
    structured answers or None, result text))] for each AskUserQuestion the user
    answered, never_ran the ids of tool calls whose result shows they never ran."""
    asks, answers, never_ran = {}, [], set()
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use" and c.get("name") == "AskUserQuestion":
                    asks[c.get("id")] = _questions(c.get("input"))
                elif c.get("type") == "tool_result" and c.get("is_error"):
                    if _never_ran(rec, c):
                        never_ran.add(c.get("tool_use_id"))
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in asks:
                    tur = rec.get("toolUseResult")
                    structured = tur["answers"] if isinstance(tur, dict) and isinstance(tur.get("answers"), dict) else None
                    answers.append((c["tool_use_id"], (asks[c["tool_use_id"]], structured, _text(c.get("content")))))
    return answers, never_ran
