"""guard-secrets: a credential pasted into a command.

A secret written literally into a Bash command is in the transcript already,
and in whatever the command commits, prints or posts next. The detector
(languette/secrets.py, #95) names the words that are one. A known token
shape (a GitHub PAT, an AWS key id, a PEM header) is denied; a value only
its context names as a credential (`DB_PASSWORD=...`, `--password ...`, a
URL with a password) is asked, since the shape alone cannot tell a secret
from a hostname. Heredoc bodies and nested shell text are read too.

The project may extend the shipped list, in <project>/.languette/secrets.json
(the nearest at or above the payload's cwd, else $CLAUDE_PROJECT_DIR):

    {"patterns": [{"id": "acme-key", "description": "Acme API key",
                   "regex": "acme_[a-z0-9]{24}", "entropy": 3.0}]}

No file is the shipped list alone. A file that does not parse or has another
shape denies every Bash command until it is fixed: the guard cannot tell what
it was meant to cover. The file is read through the runner (Need), so the
guard, like the detector, is a pure function.
"""

import json
import os
import re

from languette import scan as sw
from languette import secrets
from languette.verdict import Need, Refuse, ask, deny

NAME = "guard-secrets"
CONFIG = ".languette/secrets.json"

_WAY_OUT = ("Keep the value out of the command: read it from the environment (`\"$TOKEN\"`), a file "
            "(`--password-file`, `gh auth login --with-token < file`) or the tool's own credential store, so the "
            "secret is not in the transcript or in what the command writes.")


def _config(payload, env):
    """The project's list path, or None. The nearest at or above cwd wins,
    stopping at the repo root; then $CLAUDE_PROJECT_DIR's."""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.startswith("/") and (yield Need("path", "isdir", cwd)):
        d = yield Need("path", "realpath", cwd)
        while True:
            if (yield Need("path", "lexists", os.path.join(d, CONFIG))):
                return os.path.join(d, CONFIG)
            if (yield Need("path", "lexists", os.path.join(d, ".git"))) or os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
    proj = env.get("CLAUDE_PROJECT_DIR")
    if proj and (yield Need("path", "lexists", os.path.join(proj, CONFIG))):
        return os.path.join(proj, CONFIG)
    return None


def _load(path):
    """The project's rules, or Refuse naming what is wrong with the file."""
    try:
        cfg = json.loads((yield Need("read", path)))
    except ValueError as e:
        raise Refuse(f"not JSON ({e})")
    except OSError as e:
        raise Refuse(f"unreadable ({e.strerror})")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("patterns"), list):
        raise Refuse('the top level must be {"patterns": [...]}')
    rules, seen = [], set()
    for n, p in enumerate(cfg["patterns"]):
        where = f"patterns[{n}]"
        if not isinstance(p, dict):
            raise Refuse(f"{where} is not an object")
        for key in ("id", "regex"):
            if not isinstance(p.get(key), str) or not p[key].strip():
                raise Refuse(f"{where}.{key} must be a non-empty string")
        if p["id"] in seen:
            raise Refuse(f"{where}.id '{p['id']}' is a duplicate")
        seen.add(p["id"])
        try:
            rx = re.compile(p["regex"])
        except re.error as e:
            raise Refuse(f"{where}.regex does not compile ({e})")
        ent = p.get("entropy", 0.0)
        if not isinstance(ent, (int, float)) or isinstance(ent, bool) or ent < 0:
            raise Refuse(f"{where}.entropy must be a number >= 0")
        rules.append(secrets.Rule(p["id"], p.get("description") or p["id"], rx, float(ent)))
    return rules


def _scans(cmd):
    """Every text the command may run or feed, read the way it will be: the
    command with heredocs stripped and its nested shell strings as shell,
    each heredoc body as lines of data."""
    body = cmd + "\n"
    return ([sw.Scan(text) for text, _ in sw.texts_of(sw.strip_heredocs(body))]
            + [secrets.Text(h) for h in sw.heredoc_bodies(body)])


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)
    cmd = cmd.rstrip("\n")
    if not cmd:
        return None
    try:
        path = yield from _config(payload, env)
        extra = (yield from _load(path)) if path else ()
    except Refuse as e:
        return deny(f"guard-secrets: {CONFIG} is {e}, so the project's secret patterns cannot be read. "
                    f"Fix the file; until then every Bash command is denied.")
    desc = {r.id: r.description for r in tuple(secrets.secret_rules.RULES) + tuple(extra)}
    shapes, contexts = [], []
    for s in _scans(cmd):
        for f in secrets.findings(s, extra):
            item = f"`{secrets.shown(s, f)}` ({desc.get(f.rule, f.rule.replace('context:', 'named by '))})"
            (shapes if f.how == "shape" else contexts).append(item)
    if shapes:
        return deny(f"guard-secrets: the command holds what looks like a credential: {', '.join(shapes)}. "
                    f"A secret pasted into a command is in the transcript and in anything it writes or posts. {_WAY_OUT}")
    if contexts:
        return ask(f"guard-secrets: a value here is named as a credential: {', '.join(contexts)}. "
                   f"If it is a real secret, say no and keep it out of the command. {_WAY_OUT}")
    return None

