"""`languette uninstall [HOST]`: reverse `languette install` for a coding agent
on this machine. It lists what it will remove, asks, then removes it, one row
per step in the doctor's marks; exits 1 on any ✗. Only Claude Code is a host
today; other hosts are planned (#5).

What install wrote is the user-scope languette@languette plugin and the
languette marketplace added from this repo, both through the `claude` command,
so uninstall asks `claude` to remove those two and nothing else. An install at
project or local scope, a marketplace of the same name from elsewhere, the
terms files and the plugin's options are left. Claude Code
drops the plugin's options from the user's settings when it uninstalls the
plugin, so they are written back, as they were, for a later install to find.
Like install, it sits outside the guard pipeline. Standard library only.
"""

import json
import os
import shutil
import sys

from languette import doctor, install

OK, WARN, FAIL = doctor.OK, doctor.WARN, doctor.FAIL
PLUGIN, MARKETPLACE = install.PLUGIN, install.MARKETPLACE


def _settings_path():
    return doctor._config_dir() / "settings.json"


def _options():
    """The plugin's options in the user's settings; None when there are none or the file will not say."""
    try:
        s = doctor._json(_settings_path(), missing={})
    except doctor.Unreadable:
        return None
    configs = s.get("pluginConfigs") if isinstance(s, dict) else None
    return configs.get(PLUGIN) if isinstance(configs, dict) else None


def _keep_options(kept):
    """(mark, label, text): `kept` written back as the plugin's options where Claude Code removed them."""
    path = _settings_path()
    where = doctor._tilde(path)
    lost = f"; they were {json.dumps(kept, separators=(',', ':'))}"
    try:
        s = doctor._json(path, missing={})
    except doctor.Unreadable as e:
        return FAIL, "options", f"{e}{lost}"
    if not isinstance(s, dict) or not isinstance(s.setdefault("pluginConfigs", {}), dict):
        return FAIL, "options", f"{where} has a shape uninstall does not know{lost}"
    if s["pluginConfigs"].get(PLUGIN) == kept:
        return OK, "options", f"left in {where}"
    s["pluginConfigs"][PLUGIN] = kept
    # Whole or untouched: a cut-off write would leave the user's settings half gone.
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(s, indent=2) + "\n")
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError as e:
        return FAIL, "options", f"{where} cannot be written ({e.strerror or e}){lost}"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return OK, "options", f"kept in {where}"


def plan(claude, cwd):
    """(steps, left, problem): what install wrote, as [(label, text, claude args)] in the order removed;
    rows for the languette installs and marketplace it did not write; a ✗ row when that is unknown."""
    try:
        found = doctor.installs(doctor.settings_files(cwd))
    except doctor.Unreadable as e:
        return [], [], (FAIL, "Claude Code", f"{e}, so what install wrote is unknown; nothing removed")
    source = install._marketplace(claude)
    ours = source is not None and install._ours(source)
    mine = ours or source is None     # no marketplace listed: the plugin is still the one install wrote
    steps, left, fed = [], [], 0
    for inst in found:
        where = f"plugin {doctor._version(inst)}, {inst.get('scope', '?')} scope"
        if inst.get("id") == PLUGIN and inst.get("scope") == "user" and mine:
            steps.append(("Claude Code", f"{PLUGIN}, {where}",
                          ("plugin", "uninstall", PLUGIN, "--scope", "user")))
        else:
            at = f" for {doctor._tilde(inst['projectPath'])}" if isinstance(inst.get("projectPath"), str) else ""
            left.append((WARN, "Claude Code", f"{inst.get('id', '?')}, {where}{at}, left: install did not write it"))
            fed += inst.get("id") == PLUGIN
    if ours and fed:
        left.append((WARN, "marketplace", f"{MARKETPLACE}, added from {source}, left: {fed} install(s) "
                                          "still come from it"))
    elif ours:
        steps.append(("marketplace", f"{MARKETPLACE}, added from {source}",
                      ("plugin", "marketplace", "remove", MARKETPLACE, "--scope", "user")))
    elif source is not None:
        left.append((WARN, "marketplace", f"{MARKETPLACE} is added from {source}, not {install.REPO}; left: "
                                          "install did not write it"))
    return steps, left, None


def _ask():
    try:
        answer = input("Remove them? [y/N] ")
    except EOFError:
        answer = ""
    if not sys.stdin.isatty():
        print()                          # no echoed Enter ends the question's line
    return answer.strip().lower() in ("y", "yes")


def claude_rows(cwd, ask=_ask):
    """[(mark, label, text)]: each removal run, stopping at the first ✗. The list of what will go,
    and the question, are printed before anything is removed."""
    claude = shutil.which("claude")
    if not claude:
        return [(FAIL, "Claude Code", "the claude command is not on PATH, so nothing can be removed through it")]
    steps, left, problem = plan(claude, cwd)
    if problem:
        return [problem]
    if not steps:
        return left + [(OK, "uninstall", "nothing install wrote is here; nothing removed")]
    print("Will remove from Claude Code:")
    for label, text, _ in steps:
        print(f"    {label:<13} {text}")
    print("Leaves the plugin's options and the terms files as they are.")
    if not ask():
        return left + [(WARN, "uninstall", "nothing removed")]
    kept, rows = _options(), list(left)
    for label, text, args in steps:
        r, why = install._claude(claude, *args)
        if why or r.returncode != 0:
            return rows + [(FAIL, label, why or install._first_line(r))]
        rows.append((OK, label, f"{text.split(',')[0]} removed"))
        if args[1] == "uninstall" and kept is not None:
            rows.append(_keep_options(kept))
    return rows


def main(host="claude"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        cwd = os.getcwd()
    except OSError as e:
        print(f"{FAIL} {'uninstall':<13} the current directory is unreadable ({e.strerror or e})")
        return 1
    rows = claude_rows(cwd)
    for mark, label, text in rows:
        print(f"{mark} {label:<13} {text}")
    return 1 if any(mark == FAIL for mark, _, _ in rows) else 0
