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


def _own(c, where):
    for key in ("cost", "approve_label"):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise sw.BadRules(f"{where}.{key} must be a non-empty string")
    if "cheaper" in c and not isinstance(c["cheaper"], str):
        raise sw.BadRules(f"{where}.cheaper must be a string")


def _load(path):
    cfg = yield from paths.read_json(path)
    try:
        commands = sw.load_rules(cfg, "commands", ("cost", "approve_label", "cheaper"), _own, many=True, nonempty=True)
    except sw.BadRules as e:
        raise Refuse(str(e))
    labels = {}
    for n, c in enumerate(commands):
        if c["approve_label"] in labels:
            raise Refuse(f"commands[{n}].approve_label '{c['approve_label']}' is shared with another command; "
                         "a click must approve exactly one")
        labels[c["approve_label"]] = c
    return commands


def check(doc):
    payload, env = doc.payload, doc.env
    cmd = doc.text
    if not cmd or not cmd.strip():
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
        m = [sw.match_rule(doc, e)[:2] for e in c["match"]]
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
