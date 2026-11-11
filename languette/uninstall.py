"""`languette uninstall [HOST]`: reverse `languette install` for a coding agent
on this machine. It lists what it will remove, asks, then removes it, one row
per step in the doctor's marks; exits 1 on any ✗. Only Claude Code is a host
today; other hosts are planned (#5).

What install wrote is the user-scope languette@languette plugin and the
languette marketplace added from this repo, both through the `claude` command,
so uninstall asks `claude` to remove those two and nothing else. An install at
project or local scope, a marketplace of the same name from elsewhere, the
terms files are left. Uninstall writes nothing to the user's
settings itself: Claude Code's own uninstall drops the plugin's options from
settings.json, and the plan says so before asking.
Like install, it sits outside the guard pipeline. Standard library only.
"""

import os
import shutil
import sys

from languette import host
from languette.host import FAIL, MARKETPLACE, OK, PLUGIN, REPO, WARN


def plan(claude, cwd):
    """(steps, left, problem): what install wrote, as [(label, text, claude args)] in the order removed;
    rows for the languette installs and marketplace it did not write; a ✗ row when that is unknown."""
    try:
        found = host.installs(host.settings_files(cwd))
    except host.Unreadable as e:
        return [], [], (FAIL, "Claude Code", f"{e}, so what install wrote is unknown; nothing removed")
    source, why = host.marketplace(claude)
    if why:
        return [], [], (FAIL, "Claude Code", f"{why}, so what install wrote is unknown; nothing removed")
    ours = source is not None and host.ours_source(source)
    mine = ours or source is None     # no marketplace listed: the plugin is still the one install wrote
    steps, left, fed = [], [], 0
    for inst in found:
        where = f"plugin {host.version(inst)}, {inst.get('scope', '?')} scope"
        if inst.get("id") == PLUGIN and inst.get("scope") == "user" and mine:
            steps.append(("Claude Code", f"{PLUGIN}, {where}",
                          ("plugin", "uninstall", PLUGIN, "--scope", "user")))
        else:
            at = f" for {host.tilde(inst['projectPath'])}" if isinstance(inst.get("projectPath"), str) else ""
            left.append((WARN, "Claude Code", f"{inst.get('id', '?')}, {where}{at}, left: install did not write it"))
            fed += inst.get("id") == PLUGIN
    if ours and fed:
        left.append((WARN, "marketplace", f"{MARKETPLACE}, added from {source}, left: {fed} install(s) "
                                          "still come from it"))
    elif ours:
        steps.append(("marketplace", f"{MARKETPLACE}, added from {source}",
                      ("plugin", "marketplace", "remove", MARKETPLACE, "--scope", "user")))
    elif source is not None:
        left.append((WARN, "marketplace", f"{MARKETPLACE} is added from {source}, not {REPO}; left: "
                                          "install did not write it"))
    return steps, left, None


def _ask():
    return host.confirm("Remove them?")


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
    if any(args[1] == "uninstall" for _, _, args in steps):
        print("Claude Code's uninstall also removes your languette options from settings.json.")
    print("Leaves the terms files as they are.")
    if not ask():
        return left + [(WARN, "uninstall", "nothing removed")]
    rows = list(left)
    for label, text, args in steps:
        r, why = host.call(claude, *args)
        if why or r.returncode != 0:
            return rows + [(FAIL, label, why or host.first_line(r))]
        rows.append((OK, label, f"{text.split(',')[0]} removed"))
    return rows


def main(agent="claude"):
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
