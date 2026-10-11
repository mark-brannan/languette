"""ask-first: a command the repo names as costly runs only after the user said
yes to it, once, through AskUserQuestion.

The repo owns the list, in <project>/.languette/ask-first.json, where
<project> is the nearest directory at or above the payload's cwd that has one,
stopping at the repo root, else $CLAUDE_PROJECT_DIR:

    {"commands": [{"id": "e2e",
                   "match": [{"cmd": "npm", "args": ["run", "e2e"]},
                             {"cmd": "node", "script": "scripts/e2e.mjs"}],
                   "cost": "> 40 minutes, using all CPU cores on a typical desktop",
                   "approve_label": "Run e2e"}]}

No file is silence. A file that does not parse, or does not have this shape,
denies every Bash command until it is fixed: the guard cannot tell what it
was meant to cover.

A match entry is a command word (`cmd`, by basename) followed by `args` as
a run of its non-option words (so an option's value, `npm --prefix web run
x`, cannot hide it), and/or any later word that is `script` or ends in
`/script`. npm, pnpm, yarn and bun stand in for each other (`yarn
e2e` is `npm run e2e`, `run-script` is `run`), and npx, bunx,
`pnpm exec|dlx` and `yarn exec|dlx` launch `cmd`. Wrappers, chains, `sh -c "..."` and `echo ... |
sh` are seen through by the scanner; prose (grep, git commit -m, cat, echo
into nothing) and process tools (pkill -f, pgrep) are not commands.

Approval is in the transcript: an AskUserQuestion tool_use whose answer
(tool_result, not is_error) to one of its questions is exactly approve_label;
the question's text is the agent's and proves nothing. approve_labels are
unique within the file, so one click approves one command. Each approval
allows one run: its tool_use id is appended to <transcript>.languette-ask and
never counts again. A command that runs a listed one twice needs two
approvals; one inside a loop or xargs is denied outright, since no count of
approvals covers it.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import Need, Refuse, deny

NAME = "ask-first"
CONFIG = ".languette/ask-first.json"

PM = frozenset("npm pnpm yarn bun".split())
LAUNCH = frozenset("npx bunx pnpm yarn bun".split())
LAUNCH_SUB = frozenset("exec dlx x".split())
# Process tools name a script to find it, not to run it.
PROSE = sw.PROSE | frozenset("pkill pgrep killall ps lsof fuser which type".split())
# npm's aliases for `run`.
RUN = frozenset("run run-script rum urn".split())
# Words that run what follows an unknown number of times.
LOOP = frozenset("for while until select xargs parallel watch -exec -execdir -ok -okdir".split())


def _config(payload, env):
    """The governing config path, or None when no project has one. The nearest
    at or above cwd wins, because the agent may have cd'd into another repo;
    then $CLAUDE_PROJECT_DIR's. Raises Refuse when cwd is unusable and the
    project dir gives no answer either: unknown is not the same as none."""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.startswith("/") and (yield Need("path", "isdir", cwd)):
        d = yield Need("path", "realpath", cwd)
        while True:
            if (yield Need("path", "lexists", os.path.join(d, CONFIG))):
                return os.path.join(d, CONFIG)
            if (yield Need("path", "lexists", os.path.join(d, ".git"))) or os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
        cwd = None
    else:
        cwd = cwd or "(none)"
    proj = env.get("CLAUDE_PROJECT_DIR")
    if proj and (yield Need("path", "lexists", os.path.join(proj, CONFIG))):
        return os.path.join(proj, CONFIG)
    if cwd:
        raise Refuse(f"the payload's cwd {cwd!r} is not a directory, so the repo's list cannot be found")
    return None


def _strs(v, what):
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
        raise Refuse(f"{what} must be a non-empty list of non-empty strings")
    return v


def _load(path):
    try:
        cfg = json.loads((yield Need("read", path)))
    except ValueError as e:
        raise Refuse(f"not JSON ({e})")
    except OSError as e:
        raise Refuse(f"unreadable ({e.strerror})")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("commands"), list) or not cfg["commands"]:
        raise Refuse('the top level must be {"commands": [...]} with at least one command')
    seen, labels = set(), set()
    for n, c in enumerate(cfg["commands"]):
        where = f"commands[{n}]"
        if not isinstance(c, dict):
            raise Refuse(f"{where} is not an object")
        for key in ("id", "cost", "approve_label"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                raise Refuse(f"{where}.{key} must be a non-empty string")
        if c["id"] in seen:
            raise Refuse(f"{where}.id '{c['id']}' is a duplicate")
        seen.add(c["id"])
        if c["approve_label"] in labels:
            raise Refuse(f"{where}.approve_label '{c['approve_label']}' is shared with another command; "
                       "a click must approve exactly one")
        labels.add(c["approve_label"])
        if "cheaper" in c and not isinstance(c["cheaper"], str):
            raise Refuse(f"{where}.cheaper must be a string")
        if not isinstance(c.get("match"), list) or not c["match"]:
            raise Refuse(f"{where}.match must be a non-empty list")
        for m, e in enumerate(c["match"]):
            w = f"{where}.match[{m}]"
            if not isinstance(e, dict) or not isinstance(e.get("cmd"), str) or not re.fullmatch(r"[A-Za-z0-9._+-]+", e["cmd"]):
                raise Refuse(f"{w}.cmd must be a bare command name")
            if "args" not in e and "script" not in e:
                raise Refuse(f"{w} needs args or script, or it would match every {e['cmd']}")
            if "args" in e:
                _strs(e["args"], f"{w}.args")
            if "script" in e and (not isinstance(e["script"], str) or not e["script"].strip("./")):
                raise Refuse(f"{w}.script must be a non-empty path")
    return cfg["commands"]


def _base(w):
    return w.rsplit("/", 1)[-1]


def _run_of(words, a):
    """Is `a` a contiguous run inside `words`?"""
    return any(words[i:i + len(a)] == a for i in range(len(words) - len(a) + 1))


def _hit(entry, name, rest):
    """Does entry match command word `name` followed by words `rest`?"""
    words = [w for w in rest if not w.startswith("-")]
    cmd = entry["cmd"]
    if name in PM:
        words = ["run" if w in RUN else w for w in words]
    if name != cmd and not (cmd in PM and name in PM):
        if name in LAUNCH:
            if words and words[0] in LAUNCH_SUB:
                words = words[1:]
            # The first word naming cmd: an option's value (npx -p x cmd) may come first.
            w = next((w for w in words if _base(w) == cmd), None)
            if w is not None:
                return _hit(entry, cmd, rest[rest.index(w) + 1:])
        return False
    ok = True
    if "args" in entry:
        a = entry["args"]
        ok = _run_of(words, a) or (name in PM - {"npm"} and a[0] == "run" and len(a) > 1 and _run_of(words, a[1:]))
    if ok and "script" in entry:
        sc = entry["script"]
        while sc.startswith("./"):
            sc = sc[2:]
        ok = any(w == sc or w.endswith("/" + sc) for w in rest)
    return ok


def _matches(doc, entry):
    """(how many times the command runs entry, whether any of it sits in a loop)."""
    names = {entry["cmd"]} | LAUNCH | (PM if entry["cmd"] in PM else set())
    rx = re.compile(r"(?:^|/)(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\Z")
    n, loop = 0, False
    for t, nested in doc.texts(PROSE):
        s = doc.scan(t)
        loop = loop or any(k == "w" and w in LOOP for k, w in zip(s.k, s.w))
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, rx, nested, prose=PROSE)
            # cmd_index stops at the first launcher; a later word may be the command.
            while g is not None:
                if _hit(entry, _base(s.w[g]), s.w[g + 1:b + 1]):
                    n += 1
                    break
                if nested:
                    break
                g = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and rx.search(s.w[i])), None)
    return n, loop


def claim(wants):
    """Spend one of the user's approvals per run; `wants` is {approve_label: runs}.
    Use as `approved, spent = yield from claim({c["approve_label"]: runs[c["id"]] for c in hits})`: approved is {label:
    tool_use ids}, spent is whether every label had its runs' worth, now recorded
    against this tool call. A click comes back when the transcript shows the call
    never ran (languette.world). The world's OSError or ValueError, for a payload
    with no transcript or a transcript that can't be read, is raised from here.
    Shared with guard-infra and guard-bypass-hooks: one click is one run,
    whichever guard asked."""
    return (yield Need("claim", dict(wants)))


def check(doc):
    payload, env = doc.payload, doc.env
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    try:
        path = yield from _config(payload, env)
    except Refuse as e:
        return deny(f"ask-first: {e}. A gate that cannot look fails closed: retry from the project directory.")
    if not path:
        return None
    try:
        commands = yield from _load(path)
    except Refuse as e:
        return deny(f"ask-first: {path} is invalid: {e}. Every Bash command is denied until it is fixed, "
                     "because the guard cannot tell which commands the repo meant to cover. Fix it with "
                     "the Edit tool, or tell the user.")
    runs, looped = {}, []
    for c in commands:
        m = [_matches(doc, e) for e in c["match"]]
        # Entries may describe the same run two ways (npm run x, tsx x.ts); count the widest.
        n = max(k for k, _ in m)
        if n:
            runs[c["id"]] = n
            if any(lp for k, lp in m if k):
                looped.append(c)
    hits = [c for c in commands if c["id"] in runs]
    if not hits:
        return None
    if looped:
        return deny("ask-first: " + ", ".join(f"`{c['id']}`" for c in looped) + " inside a loop, xargs, "
                     "parallel or watch runs an unknown number of times, and each run needs its own "
                     "approval. Run it once, on its own.")

    try:
        approved, spent = yield from claim({c["approve_label"]: runs[c["id"]] for c in hits})
    except (OSError, ValueError) as e:
        return deny(f"ask-first: cannot read the session transcript to look for the user's approval, or "
                     f"record it as spent ({e}), so `{cmd.strip()}` is denied. Ask the user to run it themselves.")
    if spent:
        return None
    parts = []
    for c in hits:
        have = len(approved[c["approve_label"]])
        if have >= runs[c["id"]]:
            continue
        p = (f"`{c['id']}` ({path}) needs the user's approval for each run"
             + (f"; this command runs it {runs[c['id']]} times and has {have} unspent"
                if runs[c["id"]] > 1 else "") + f". Cost: {c['cost']}."
             + (f" Cheaper forms: {c['cheaper']}." if c.get("cheaper") else ""))
        p += (f" If a cheaper form answers the question, use it instead. Otherwise call AskUserQuestion: "
              f"give the exact command (`{cmd.strip()}`), why it must run now, and the "
              f"cost above, with one option labelled exactly \"{c['approve_label']}\" and one to skip. "
              "One approval is one run; ask again before running it again.")
        parts.append(p)
    return deny("ask-first: " + "\n\n".join(parts))
