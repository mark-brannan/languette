"""The one module that touches the disk, subprocesses, the clock or the network.

The runner (run.py) holds one World per payload and asks it for each Need a
guard yields (languette.verdict.Need lists the kinds). World owns the budget:
one timeout per kind of fact, the ruleset cache, the spent-file lock.
Standard library only.
"""

import fcntl
import json
import os
import re
import subprocess
import time
from urllib.parse import quote

GIT_TIMEOUT = 5
GH_TIMEOUT = 10
SPENT = ".languette-ask"            # appended to the transcript path
RECORDS = "decisions.jsonl"         # under $XDG_STATE_HOME/languette
RECORDS_MAX = 8 << 20               # bytes; past it the file becomes .1, the old .1 goes
RECORDS_WAIT = 0.1                  # seconds a writer waits on the lock before dropping its record
KINDS = frozenset("git gh-api read path cwd clock ruleset-cache ruleset-keep claim".split())


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

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _path(self, op, path):
        if op not in ("isdir", "lexists", "realpath"):
            raise ValueError(f"no path fact {op!r}")
        return getattr(os.path, op)(path)

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
            path = os.path.join(d, RECORDS)
            line = (json.dumps(rec, separators=(",", ":")) + "\n").encode("utf-8", "surrogatepass")
            deadline = time.monotonic() + RECORDS_WAIT
            for _ in range(3):
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
                        if os.stat(path).st_ino != st.st_ino:
                            continue               # rotated while we waited
                    except FileNotFoundError:
                        continue                   # rotated, and the new file not made yet
                    if st.st_mode & 0o077:
                        os.fchmod(fd, 0o600)
                    if st.st_size + len(line) > RECORDS_MAX and st.st_size:
                        os.replace(path, path + ".1")
                        continue
                    os.write(fd, line)
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
