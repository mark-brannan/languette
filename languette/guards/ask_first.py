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

The payload's permission_mode changes only the message: in dontAsk, where
AskUserQuestion is denied unseen, the deny says no one can approve it instead
of sending the agent to ask.
"""

import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import NO_QUESTION, Refuse, claim, deny

NAME = "ask-first"
CONFIG = ".languette/ask-first.json"

def _config(payload, env):
    """The governing config path, or None when no project has one
    (paths.project_config). Raises Refuse when cwd is unusable and the project
    dir gives no answer either: unknown is not the same as none."""
    path, usable = yield from paths.project_config(payload, env, CONFIG)
    if path is None and not usable:
        raise Refuse(f"the payload's cwd {payload.get('cwd') or '(none)'!r} is not a directory, "
                     "so the repo's list cannot be found")
    return path


def _strs(v, what):
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
        raise Refuse(f"{what} must be a non-empty list of non-empty strings")
    return v


def _load(path):
    cfg = yield from paths.read_json(path)
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


def check(doc):
    payload, env = doc.payload, doc.env
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    try:
        path = yield from _config(payload, env)
    except Refuse as e:
        return deny(say("ask_first_cannot_look", err=e))
    if not path:
        return None
    try:
        commands = yield from _load(path)
    except Refuse as e:
        return deny(say("ask_first_invalid", path=path, err=e))
    runs, looped = {}, []
    for c in commands:
        m = [sw.matches(doc, e) for e in c["match"]]
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
        return deny(say("loop", guard="ask-first", what=", ".join(f"`{c['id']}`" for c in looped),
                        then="Run it once, on its own."))

    try:
        approved, spent = yield from claim({c["approve_label"]: runs[c["id"]] for c in hits})
    except (OSError, ValueError) as e:
        return deny(say("transcript_unreadable", guard="ask-first", err=e, cmd=cmd.strip(),
                        then="Ask the user to run it themselves."))
    if spent:
        return None
    parts = []
    for c in hits:
        have = len(approved[c["approve_label"]])
        if have >= runs[c["id"]]:
            continue
        cheaper = say("ask_first_cheaper", cheaper=c["cheaper"]) if c.get("cheaper") else ""
        if doc.mode in NO_QUESTION:  # any other mode, unknown or missing included, stays an ask
            parts.append(say("ask_first_unattended", id=c["id"], path=path, mode=doc.mode, cost=c["cost"],
                             cheaper=cheaper, cmd=cmd.strip()))
            continue
        parts.append(say("ask_first_need", id=c["id"], path=path,
                         times=(say("ask_first_times", n=runs[c["id"]], have=have) if runs[c["id"]] > 1 else ""),
                         cost=c["cost"], cheaper=cheaper, cmd=cmd.strip(), label=c["approve_label"]))
    return deny(say("judged", guard="ask-first", why="\n\n".join(parts)))
