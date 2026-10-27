"""`languette install [HOST]`: wire languette into a coding agent on this
machine, one row per step, each ✓, ! or ✗, in the doctor's format. Exits 1 on
any ✗. Only Claude Code is a host today; other hosts are planned (#5).

The package install (pipx, brew) puts `languette` on PATH; the guards reach
Claude Code as its plugin, through languette's own plugin marketplace. So this
writes nothing itself: it asks the `claude` command to add the marketplace and
install the plugin, and only Claude Code writes. When the plugin is already
installed for this directory, it runs neither and says so. Like the doctor, it
sits outside the guard pipeline: no guard imports it and it imports no guard.
Standard library only.
"""

import json
import os
import shutil
import subprocess
import sys

from languette import doctor

OK, FAIL = doctor.OK, doctor.FAIL
HOSTS = ("claude",)
MARKETPLACE = "languette"                  # the name in .claude-plugin/marketplace.json
HOME_PAGE = "https://github.com/mark-brannan/languette"
SOURCE = HOME_PAGE.removeprefix("https://github.com/") + "#release"   # owner/repo#ref, as `claude` reads it
PLUGIN = "languette@languette"
STEP_TIMEOUT = 120                         # seconds for each `claude plugin` command


def _first_line(r):
    for text in (r.stderr, r.stdout):
        for ln in (text or "").splitlines():
            if ln.strip():
                return ln.strip()
    return f"exit {r.returncode}, no output"


def _claude(claude, *args):
    """(CompletedProcess or None, what went wrong when it did not run)."""
    try:
        return subprocess.run([claude, *args], capture_output=True, text=True, timeout=STEP_TIMEOUT), None
    except subprocess.TimeoutExpired:
        return None, f"`claude {' '.join(args)}` ran past {STEP_TIMEOUT} s"
    except OSError as e:
        return None, f"`claude {' '.join(args)}` could not start ({e.strerror or e})"


def _marketplace_added(claude):
    r, _ = _claude(claude, "plugin", "marketplace", "list", "--json")
    try:
        listed = json.loads(r.stdout) if r and r.returncode == 0 else []
    except ValueError:
        return False
    return isinstance(listed, list) and any(isinstance(m, dict) and m.get("name") == MARKETPLACE for m in listed)


def claude_rows(cwd):
    """[(mark, label, text)]: each step run, stopping at the first ✗."""
    claude = shutil.which("claude")
    if not claude:
        return [(FAIL, "Claude Code", "the claude command is not on PATH; install Claude Code, or see "
                                      "Installing by hand in the README")]
    try:
        inst = doctor.in_effect(doctor.installs(doctor.settings_files(cwd)), cwd)
    except doctor.Unreadable as e:
        return [(FAIL, "Claude Code", f"{e}, so whether languette is installed is unknown; nothing run")]
    if inst and inst.get("enabled") is False:
        # Enabling is the host's own command: name it, never run it.
        return [(FAIL, "Claude Code", f"plugin {doctor._version(inst)}, {inst.get('scope', '?')} scope, is disabled: "
                                      f"claude plugin enable {inst.get('id') or PLUGIN}")]
    if inst:
        return [(OK, "Claude Code", f"plugin {doctor._version(inst)} already installed, "
                                    f"{inst.get('scope', '?')} scope; nothing written")]
    rows = []
    if _marketplace_added(claude):
        rows.append((OK, "marketplace", f"{SOURCE} already added"))
    else:
        r, problem = _claude(claude, "plugin", "marketplace", "add", SOURCE)
        if problem or (r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower()):
            return rows + [(FAIL, "marketplace", problem or _first_line(r))]
        rows.append((OK, "marketplace", f"{SOURCE} {'added' if r.returncode == 0 else 'already added'}"))
    r, problem = _claude(claude, "plugin", "install", PLUGIN)
    if problem or r.returncode != 0:
        return rows + [(FAIL, "Claude Code", problem or _first_line(r))]
    return rows + [(OK, "Claude Code", "plugin installed, user scope; run languette doctor")]


def main(host="claude"):
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
