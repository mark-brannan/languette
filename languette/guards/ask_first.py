"""ask-first: a command the repo names as costly runs only after the user said
yes to it, once, through AskUserQuestion.

The repo owns the list, in <project>/.claude/languette-ask.json, where
<project> is $CLAUDE_PROJECT_DIR, else the git toplevel of the payload's cwd:

    {"commands": [{"id": "conformance",
                   "match": [{"cmd": "npm", "args": ["run", "conformance"]},
                             {"cmd": "tsx", "script": "research/conformance/run.ts"}],
                   "cost": "full walk ~46 min, load ~20 on 16 cores",
                   "cheaper": "--sample=N, --jobs=N",
                   "approve_label": "Run conformance"}]}

No file is silence. A file that does not parse, or does not have this shape,
denies every Bash command until it is fixed: the guard cannot tell what it
was meant to cover.

A match entry is a command word (`cmd`, by basename) followed by `args` as
its leading non-option words, and/or any later word that is `script` or ends
in `/script`. npm, pnpm, yarn and bun stand in for each other (`yarn
conformance` is `npm run conformance`), and npx, bunx, `pnpm exec|dlx` and
`yarn exec|dlx` launch `cmd`. Wrappers, chains, `sh -c "..."` and `echo ... |
sh` are seen through by the scanner; prose (grep, git commit -m, cat, echo
into nothing) and process tools (pkill -f, pgrep) are not commands.

Approval is in the transcript: an AskUserQuestion tool_use whose input names
the id, answered (tool_result, not is_error) with the exact quoted
approve_label. Each approval allows one run: its tool_use id is appended to
<transcript>.languette-ask and never counts again.
"""

import json
import os
import re
import subprocess

from languette import scan as sw

NAME = "ask-first"
CONFIG = ".claude/languette-ask.json"

PM = frozenset("npm pnpm yarn bun".split())
LAUNCH = frozenset("npx bunx pnpm yarn bun".split())
LAUNCH_SUB = frozenset("exec dlx x".split())
# Process tools name a script to find it, not to run it.
PROSE = sw.PROSE | frozenset("pkill pgrep killall ps lsof fuser which type".split())


class _Bad(Exception):
    pass


def _deny(reason):
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def _project(payload, env):
    d = env.get("CLAUDE_PROJECT_DIR")
    if d:
        return d
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/") or not os.path.isdir(cwd):
        return None
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=3)
    except Exception:  # noqa: BLE001 -- no git is no project, not a deny
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _strs(v, what):
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
        raise _Bad(f"{what} must be a non-empty list of non-empty strings")
    return v


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except ValueError as e:
        raise _Bad(f"not JSON ({e})")
    except OSError as e:
        raise _Bad(f"unreadable ({e.strerror})")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("commands"), list) or not cfg["commands"]:
        raise _Bad('the top level must be {"commands": [...]} with at least one command')
    seen = set()
    for n, c in enumerate(cfg["commands"]):
        where = f"commands[{n}]"
        if not isinstance(c, dict):
            raise _Bad(f"{where} is not an object")
        for key in ("id", "cost", "approve_label"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                raise _Bad(f"{where}.{key} must be a non-empty string")
        if c["id"] in seen:
            raise _Bad(f"{where}.id '{c['id']}' is a duplicate")
        seen.add(c["id"])
        if "cheaper" in c and not isinstance(c["cheaper"], str):
            raise _Bad(f"{where}.cheaper must be a string")
        if not isinstance(c.get("match"), list) or not c["match"]:
            raise _Bad(f"{where}.match must be a non-empty list")
        for m, e in enumerate(c["match"]):
            w = f"{where}.match[{m}]"
            if not isinstance(e, dict) or not isinstance(e.get("cmd"), str) or not re.fullmatch(r"[A-Za-z0-9._+-]+", e["cmd"]):
                raise _Bad(f"{w}.cmd must be a bare command name")
            if "args" not in e and "script" not in e:
                raise _Bad(f"{w} needs args or script, or it would match every {e['cmd']}")
            if "args" in e:
                _strs(e["args"], f"{w}.args")
            if "script" in e and (not isinstance(e["script"], str) or not e["script"].strip("./")):
                raise _Bad(f"{w}.script must be a non-empty path")
    return cfg["commands"]


def _base(w):
    return w.rsplit("/", 1)[-1]


def _hit(entry, name, rest):
    """Does entry match command word `name` followed by words `rest`?"""
    words = [w for w in rest if not w.startswith("-")]
    cmd = entry["cmd"]
    if name != cmd and not (cmd in PM and name in PM):
        if name in LAUNCH:
            if words and words[0] in LAUNCH_SUB:
                words = words[1:]
            if words and _base(words[0]) == cmd:
                i = rest.index(words[0])
                return _hit(entry, cmd, rest[i + 1:])
        return False
    ok = True
    if "args" in entry:
        a = entry["args"]
        ok = words[:len(a)] == a or (name in PM - {"npm"} and a[0] == "run" and words[:len(a) - 1] == a[1:])
    if ok and "script" in entry:
        sc = entry["script"]
        while sc.startswith("./"):
            sc = sc[2:]
        ok = any(w == sc or w.endswith("/" + sc) for w in rest)
    return ok


def _matches(entry, text):
    names = {entry["cmd"]} | LAUNCH | (PM if entry["cmd"] in PM else set())
    rx = re.compile(r"(?:^|/)(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\Z")
    for t, nested in sw.texts_of(sw.strip_heredocs(text), PROSE):
        s = sw.Scan(t)
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, rx, nested, prose=PROSE)
            # cmd_index stops at the first launcher; a later word may be the command.
            while g is not None:
                if _hit(entry, _base(s.w[g]), s.w[g + 1:b + 1]):
                    return True
                if nested:
                    break
                g = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and rx.search(s.w[i])), None)
    return False


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text") if isinstance(c, dict) else c) for c in content)
    return ""


def _names(inp, cid):
    """Does the question name cid as a word, outside the option labels (the
    approve label alone, "Run conformance", would otherwise name it)?"""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k != "label"}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    text = json.dumps(strip(inp), ensure_ascii=False)
    return re.search(r"(?<![\w-])" + re.escape(cid) + r"(?![\w-])", text) is not None


def _approvals(transcript, cid, label):
    """tool_use ids of AskUserQuestion calls naming cid that the user answered with label."""
    asks, yes = {}, []
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
                if c.get("type") == "tool_use" and c.get("name") == "AskUserQuestion" and \
                        _names(c.get("input"), cid):
                    asks[c.get("id")] = True
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in asks and not c.get("is_error"):
                    if f'"{label}"' in _text(c.get("content")):
                        yes.append(c["tool_use_id"])
    return yes


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    proj = _project(payload, env)
    if not proj:
        return None
    path = os.path.join(proj, CONFIG)
    if not os.path.lexists(path):
        return None
    try:
        commands = _load(path)
    except _Bad as e:
        return _deny(f"ask-first: {path} is invalid: {e}. Every Bash command is denied until it is fixed, "
                     "because the guard cannot tell which commands the repo meant to cover. Fix it with "
                     "the Edit tool, or tell the user.")
    hits = [c for c in commands if any(_matches(e, cmd + "\n") for e in c["match"])]
    if not hits:
        return None

    tp = payload.get("transcript_path")
    spent_path = (tp + ".languette-ask") if isinstance(tp, str) and tp else None
    try:
        if not spent_path:
            raise OSError("the payload has no transcript_path")
        spent = set()
        if os.path.exists(spent_path):
            with open(spent_path, encoding="utf-8") as f:
                spent = {x.strip() for x in f if x.strip()}
        approved = {c["id"]: [i for i in _approvals(tp, c["id"], c["approve_label"]) if i not in spent]
                    for c in hits}
    except (OSError, ValueError) as e:
        return _deny(f"ask-first: cannot read the session transcript to look for the user's approval "
                     f"({e}), so `{cmd.strip()}` is denied. Ask the user to run it themselves.")

    missing = [c for c in hits if not approved[c["id"]]]
    if missing:
        parts = []
        for c in missing:
            p = (f"`{c['id']}` ({path}) needs the user's approval for each run. Cost: {c['cost']}."
                 + (f" Cheaper forms: {c['cheaper']}." if c.get("cheaper") else ""))
            p += (f" If a cheaper form answers the question, use it instead. Otherwise call AskUserQuestion: "
                  f"name `{c['id']}`, give the exact command (`{cmd.strip()}`), why it must run now, and the "
                  f"cost above, with one option labelled exactly \"{c['approve_label']}\" and one to skip. "
                  "One approval is one run; ask again before running it again.")
            parts.append(p)
        return _deny("ask-first: " + "\n\n".join(parts))
    try:
        with open(spent_path, "a", encoding="utf-8") as f:
            for c in hits:
                f.write(approved[c["id"]][0] + "\n")
    except OSError as e:
        return _deny(f"ask-first: the approval could not be recorded as spent ({e}), so it is not used.")
    return None
