"""ask-first's handler (languette/rules/ask_first.py is the rule set): a command the
repo names as costly runs only after the user said yes to it, once, through
AskUserQuestion. The spec is features/ask-first.feature. The list is the repo's, read
from a file, so the walk of the command is the handler's too, after the read.

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
`/script`, or is the file <project>/`script` where the word runs: the
payload's cwd, moved by an earlier cd in the command. A cd the scanner cannot
follow (a variable, `cd -`, popd) leaves that unknown, and then any word
naming the script's file is it. npm, pnpm, yarn and bun stand in for each other (`yarn
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

import os

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.secrets import quote
from languette.verdict import NO_QUESTION, Need, Refuse, approve, deny

CONFIG = ".languette/ask-first.json"


def _config(payload, env):
    """The governing config path, or None when no project has one
    (paths.project_config). Raises Refuse when cwd is unusable and the project
    dir gives no answer either: unknown is not the same as none."""
    path, usable = yield from paths.project_config(payload, env, CONFIG)
    if path is None and not usable:
        raise Refuse(say("af_cwd_not_dir", cwd=repr(payload.get("cwd") or "(none)")))
    return path


def _start(payload):
    """The directory the command starts in, as the list's path was found (realpath), or None."""
    cwd = payload.get("cwd")
    if not (isinstance(cwd, str) and cwd.startswith("/") and (yield Need("path", "isdir", cwd))):
        return None
    return (yield Need("path", "realpath", cwd))


def _own(c, where):
    for key in ("cost", "approve_label"):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise sw.BadRules(f"{where}.{key} must be a non-empty string")
    if "cheaper" in c and not isinstance(c["cheaper"], str):
        raise sw.BadRules(f"{where}.cheaper must be a string")


def load(path):
    """The repo's listed commands, or Refuse naming what is wrong with the file."""
    commands = yield from paths.read_rules(
        path, "commands", ("cost", "approve_label", "cheaper"), _own, many=True, nonempty=True)
    labels = {}
    for n, c in enumerate(commands):
        if c["approve_label"] in labels:
            raise Refuse(say("af_label_shared", n=n, label=c["approve_label"]))
        labels[c["approve_label"]] = c
    return commands


def approval(doc, guard, found):
    """The `listed-approval` handler: finds the repo's list, and for each listed command the
    call runs, spends one of the user's approvals per run; short of one per run, or in a
    loop, the call is denied. No list is no finding; a list it cannot read denies every command."""
    payload, env = doc.payload, doc.env
    try:
        path = yield from _config(payload, env)
    except Refuse as e:
        return deny(say("ask_first_cannot_look", err=e))
    if not path:
        return None
    try:
        commands = yield from load(path)
    except Refuse as e:
        return deny(say("ask_first_invalid", path=path, err=e))
    at = None
    root = os.path.dirname(os.path.dirname(path))
    if root.startswith("/") and any("script" in e for c in commands for e in c["match"]):
        start = yield from _start(payload)
        at = (start, root)
    runs, looped = {}, []
    for c in commands:
        m = [sw.match_rule(doc, e, at=at)[:2] for e in c["match"]]
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
        return deny(say("loop", guard=guard, what=", ".join(f"`{c['id']}`" for c in looped),
                        then="Run it once, on its own."))

    shown = quote(doc) or say("command_withheld")
    approved, done = yield from approve(
        {c["approve_label"]: runs[c["id"]] for c in hits},
        lambda e: say("transcript_unreadable", guard=guard, err=e, cmd=shown,
                      then="Ask the user to run it themselves."))
    if done:
        return done[0]
    parts = []
    for c in hits:
        have = len(approved[c["approve_label"]])
        if have >= runs[c["id"]]:
            continue
        cheaper = say("ask_first_cheaper", cheaper=c["cheaper"]) if c.get("cheaper") else ""
        if doc.mode in NO_QUESTION:  # any other mode, unknown or missing included, stays an ask
            parts.append(say("ask_first_unattended", id=c["id"], path=path, mode=doc.mode, cost=c["cost"],
                             cheaper=cheaper, cmd=shown))
            continue
        parts.append(say("ask_first_need", id=c["id"], path=path,
                         times=(say("ask_first_times", n=runs[c["id"]], have=have) if runs[c["id"]] > 1 else ""),
                         cost=c["cost"], cheaper=cheaper, cmd=shown, label=c["approve_label"]))
    return deny(say("judged", guard=guard, why="\n\n".join(parts)))
