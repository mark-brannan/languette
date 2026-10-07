"""The one module that touches the disk, subprocesses, the clock or the network.

The runner (run.py) holds one World per payload and asks it for each Need a
guard yields (languette.verdict.Need lists the kinds), then, once the verdict
is not a deny, for the approvals the findings want spent. World owns the
budget: one timeout per kind of fact, the ruleset cache, the spent-file lock.
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
KINDS = frozenset("git gh-api read path cwd clock ruleset-cache ruleset-keep approvals".split())


class World:
    def __init__(self, env, payload):
        self.env, self.payload = env, payload
        self._yes = {}                         # label -> approving ids; the transcript only grows

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
        except OSError:
            return None

    def _ruleset_keep(self, slug, branch, text):
        f = self._ruleset_file(slug, branch)
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as fh:
                fh.write(text + "\n")
        except OSError:
            pass                               # a cache that can't be written only costs a later ask

    def _approvals(self, labels):
        """{label: [unspent ids]}, from the transcript and the spent file as they stand."""
        return _unspent(self._transcript_yes(labels), self._spent_ids())

    # --- the one write ---------------------------------------------------

    def spend(self, wants):
        """Spend `wants` ({approve_label: runs}) atomically: under an exclusive lock
        on the spent file, re-read what is spent and record one tool_use id per run
        only when every label still has its runs' worth unspent. True when spent;
        False, spending nothing, when a parallel hook got there first. Raises OSError
        when the transcript or the spent file cannot be read or written."""
        yes = self._transcript_yes(wants)
        with open(self._transcript() + SPENT, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            approved = _unspent(yes, {x.strip() for x in f if x.strip()})
            if any(len(approved[label]) < n for label, n in wants.items()):
                return False
            f.writelines(i + "\n" for label, n in wants.items() for i in approved[label][:n])
            return True

    # --- the transcript --------------------------------------------------

    def _transcript(self):
        tp = self.payload.get("transcript_path")
        if not isinstance(tp, str) or not tp:
            raise OSError("the payload has no transcript_path")
        return tp

    def _transcript_yes(self, labels):
        """{label: approving tool_use ids}; the transcript only grows, so read once a label."""
        missing = [label for label in labels if label not in self._yes]
        if missing:
            self._yes.update(approvals(self._transcript(), missing))
        return {label: self._yes[label] for label in labels}

    def _spent_ids(self):
        try:
            with open(self._transcript() + SPENT, encoding="utf-8") as f:
                return {x.strip() for x in f if x.strip()}
        except FileNotFoundError:
            return set()


def _unspent(yes, spent):
    return {label: [i for i in ids if i not in spent] for label, ids in yes.items()}


# --- reading approvals out of a transcript ---------------------------------

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text") if isinstance(c, dict) else c) for c in content)
    return ""


def _questions(inp):
    qs = inp.get("questions") if isinstance(inp, dict) else None
    return [q["question"] for q in qs or () if isinstance(q, dict) and isinstance(q.get("question"), str)]


def _said(rec, c, questions, label):
    """Did the user answer one of `questions` with exactly `label`? Only the
    answer side counts: the question is the agent's text and may quote the
    label. Claude Code records the answers structured beside the result; the
    result text, `"<question>"="<answer>"` pairs, is read only for a
    one-question ask, where no question can embed another's pair."""
    tur = rec.get("toolUseResult")
    if isinstance(tur, dict) and isinstance(tur.get("answers"), dict):
        return any(tur["answers"].get(q) == label for q in questions)
    if len(questions) != 1:
        return False
    return re.search(r'(?:^|: )' + re.escape(f'"{questions[0]}"="{label}"') + r'(?:\.|$)',
                     _text(c.get("content")), re.M) is not None


def approvals(transcript, labels):
    """{label: tool_use ids of AskUserQuestion calls the user answered with label}."""
    asks, yes = {}, {label: [] for label in labels}
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
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in asks and not c.get("is_error"):
                    for label in labels:
                        if _said(rec, c, asks[c["tool_use_id"]], label):
                            yes[label].append(c["tool_use_id"])
    return yes
