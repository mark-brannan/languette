"""`languette install [HOST]`: wire languette into a coding agent on this
machine, one row per step, each ✓, ! or ✗, in the doctor's format. Exits 1 on
any ✗. Only Claude Code is a host today; other hosts are planned (#5).

The package install (pipx, brew) puts `languette` on PATH; the guards reach
Claude Code as its plugin, through languette's own plugin marketplace. So this
writes no plugin file itself: it asks the `claude` command to add the marketplace
and install the plugin, and only Claude Code writes those. The one file it
writes is the default redacted terms file, where there is none, plugin already
installed or not. When the plugin is already installed for this directory, it
runs neither command and says so. Like the doctor, it
sits outside the guard pipeline: no guard imports it and it imports no guard.
Standard library only.
"""

import os
import shutil
import sys

from languette import doctor, host
from languette.host import FAIL, MARKETPLACE, OK, PLUGIN, REPO, SOURCE


def _foreign(source):
    return (FAIL, "marketplace", f"{MARKETPLACE} is added from {source}, not {REPO}; remove it with claude plugin "
                                 f"marketplace remove {MARKETPLACE}, then run languette install again")


def _terms_rows(files, inst):
    """The default terms file, where the options `inst` has in the settings already read say."""
    try:
        options = host.plugin_options(files, inst)
    except host.Unreadable:
        options = {}
    return doctor.default_terms_rows(options)


def claude_rows(cwd):
    """[(mark, label, text)]: each step run, stopping at the first ✗."""
    claude = shutil.which("claude")
    if not claude:
        return [(FAIL, "Claude Code", "the claude command is not on PATH; install Claude Code, or see the README section "
                                      "If you cannot run the installer")]
    files = host.settings_files(cwd)
    try:
        inst = host.in_effect(host.installs(files), cwd)
    except host.Unreadable as e:
        return [(FAIL, "Claude Code", f"{e}, so whether languette is installed is unknown; nothing run")]
    if inst and inst.get("enabled") is False:
        # Enabling is the host's own command: name it, never run it.
        return [(FAIL, "Claude Code", f"plugin {host.version(inst)}, {inst.get('scope', '?')} scope, is disabled: "
                                      f"claude plugin enable {inst.get('id') or PLUGIN}")]
    if inst:
        return [(OK, "Claude Code", f"plugin {host.version(inst)} already installed, "
                                    f"{inst.get('scope', '?')} scope; nothing written")] + _terms_rows(files, inst)
    # A marketplace of the same name from elsewhere would serve its own languette@languette.
    rows, (source, _) = [], host.marketplace(claude)
    if source is None:
        r, problem = host.call(claude, "plugin", "marketplace", "add", SOURCE)
        if problem or (r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower()):
            return [(FAIL, "marketplace", problem or host.first_line(r))]
        if r.returncode == 0:
            rows.append((OK, "marketplace", f"{SOURCE} added"))
        else:
            source = host.marketplace(claude)[0]
            if source is None:
                return [(FAIL, "marketplace", host.first_line(r))]
    if source is not None and not host.ours_source(source):
        return [_foreign(source)]
    if source is not None:
        rows.append((OK, "marketplace", f"{SOURCE} already added"))
    r, problem = host.call(claude, "plugin", "install", PLUGIN)
    if problem or r.returncode != 0:
        return rows + [(FAIL, "Claude Code", problem or host.first_line(r))]
    return rows + [(OK, "Claude Code", "plugin installed, user scope; run languette doctor")] + _terms_rows(files, {"id": PLUGIN})


def main(agent="claude"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        cwd = os.getcwd()
    except OSError as e:
        print(f"{FAIL} {'install':<13} the current directory is unreadable ({e.strerror or e})")
        return 1
    rows = claude_rows(cwd)
    for mark, label, text in rows:
        print(f"{mark} {label:<13} {text}")
    return 1 if any(mark == FAIL for mark, _, _ in rows) else 0
