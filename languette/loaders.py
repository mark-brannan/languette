"""Every languette config read through its guard's own loader, for the commands that judge one
outside a hook: `languette config` before it writes an option, the doctor over every option,
every file under `.languette/` and the user's own lists beside them. The guard's code is what refuses, so neither command can store
or pass a value the guard would refuse. Like the doctor, this sits outside the guard pipeline:
no guard imports it. Standard library only.
"""

import os
import re

from languette import comment_posts, engine, host, listed_runs, paths, secrets, terms
from languette.rules import deny_always

# A repo's file under .languette/ -> (the option that switches its guard, its loader: path -> generator).
# One that does not load denies every Bash command while its guard is on.
REPO_FILES = {
    "ask-first.json": ("ask_first", listed_runs.load),
    "deny-always.json": ("deny_always", lambda path: engine.repo_rules(path, engine.load(deny_always.RULE_SET))),
    "secrets.json": ("guard_secrets", secrets.load),
}
REPO_DIR = ".languette"
# The user's own files, in paths.user_config, read in every repo beside the repo's own, and by the same loader.
USER_FILES = (listed_runs.USER, deny_always.RULE_SET["user"])


def drive(gen, env):
    """What generator `gen` returns, its Needs answered by the world under `env`."""
    from languette.run import drive as run_drive  # run.py exits when a guard will not import
    from languette.world import World
    return run_drive(gen, World(env, {}), [])


def option(name, value, env):
    """Why the guard that reads option `name` would refuse `value` (a string, as the hook is
    given it), or None. `env` is the guard's environment the value is judged in."""
    if not value:
        return None
    env = {**env, terms.option_env(name): value}
    for kind in terms.KINDS:
        if terms.option_name(kind) == name:
            penv = drive(terms.environment(env), env)
            _, path, _, err = drive(terms.load(kind, env, penv), env)
            where = host.tilde(path)
            if isinstance(err, terms.BadTerms):
                return f"{where} {err}"
            return f"{where} {terms.why_not(err)}" if err else None
    if name == "signed_comments_signature":
        try:
            comment_posts.signature_patterns(value)
        except re.error as e:
            return f"is not a regular expression ({e})"
    if name == "signed_comments_mcp" and value not in comment_posts.MCP_RULES:
        return f"is not one of {', '.join(comment_posts.MCP_RULES)}"
    return None


def user_files(env):
    """[(path, the option of the guard that reads it, why it does not load or None)]: each of
    USER_FILES that is there."""
    out = []
    for name in USER_FILES:
        path = paths.user_config(env, name)
        if not path or not os.path.lexists(path):
            continue
        out.append((path, REPO_FILES[name][0], _why(REPO_FILES[name][1], path, env)))
    return out


def _why(load, path, env):
    try:
        drive(load(path), env)
    except Exception as e:  # noqa: BLE001 -- Refuse, or the world's own read error
        return str(e)
    return None


def shared_labels(cwd, env):
    """{approve_label: [path, ...]} for each label the user's ask-first list and the repo's both
    give, as listed_runs.shared_labels finds them; lists that do not load are left out."""
    lists = []
    for path in (paths.user_config(env, listed_runs.USER),
                 drive(paths.project_config({"cwd": cwd}, env, listed_runs.CONFIG), env)[0]):
        if path and os.path.lexists(path):
            try:
                lists.append((path, drive(listed_runs.load(path), env)))
            except Exception:  # noqa: BLE001 -- a list that does not load has a row of its own
                pass
    return listed_runs.shared_labels(lists)


def repo_files(cwd, env):
    """[(path, the option of the guard that reads it or None, why it does not load or None)]: each
    file of REPO_FILES the guards would read from cwd, found as they find it, then any other file in
    the nearest .languette/, which no guard reads."""
    payload = {"cwd": cwd}
    out, found = [], set()
    for name, (opt, load) in REPO_FILES.items():
        path, _ = drive(paths.project_config(payload, env, f"{REPO_DIR}/{name}"), env)
        if path is None:
            continue
        found.add(path)
        out.append((path, opt, _why(load, path, env)))
    nearest, _ = drive(paths.project_config(payload, env, REPO_DIR), env)
    if nearest and os.path.isdir(nearest):
        out += [(p, None, None) for p in sorted(os.path.join(nearest, n) for n in os.listdir(nearest))
                if p not in found and os.path.isfile(p)]
    return out
