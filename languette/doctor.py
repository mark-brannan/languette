"""`languette doctor`: say whether languette protects Claude Code on this
machine, one row per check, each ✓, ! or ✗. Exits 1 on any ✗, so CI can run it.

The doctor reads settings and runs programs, so it sits outside the pure
steps of the guard pipeline (docs/design/guard-pipeline.md): no guard imports
it. It writes nothing. The canary sends `rm -rf ~` to the installed hook as a
JSON payload, the way Claude Code would; nothing here ever runs that command.
Anything it cannot read, or reads in a shape it does not know, is a ! row,
never a traceback. Standard library only.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from languette import scan

OK, WARN, FAIL = "✓", "!", "✗"
CANARY = "rm -rf ~"
CANARY_GUARD = "guard-recursive-delete"
HOOK_TIMEOUT = 600                 # seconds: Claude Code's default for a command hook
WAIT_MAX = 60                      # seconds the doctor waits on the canary, whatever the hook's limit
# The gate each hooks.json command opens with: `= false` runs the guard unless
# its option is exactly false, `!= true` (an opt-in guard) only when exactly true.
GATE = re.compile(r'^\[ "\$\{CLAUDE_PLUGIN_OPTION_(\w+)-\}" (=|!=) (true|false) \]')
BY_HAND = re.compile(r"languette/run\.py")
SHA = re.compile(r"[0-9a-f]{7,40}")


class Unreadable(Exception):
    """A file the doctor needs is missing, not JSON, or not in a shape it knows."""


def _home():
    return Path(os.environ.get("HOME") or Path.home())


def _tilde(path):
    home, p = str(_home()), str(path)
    return "~" + p[len(home):] if p == home or p.startswith(home.rstrip("/") + "/") else p


def _json(path, missing=None):
    """The JSON in `path`, `missing` when there is no file, or Unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise Unreadable(f"{_tilde(path)} is missing") from None
    except (OSError, UnicodeDecodeError) as e:
        raise Unreadable(f"{_tilde(path)} is unreadable ({getattr(e, 'strerror', None) or e})") from None
    except ValueError:
        raise Unreadable(f"{_tilde(path)} is not JSON") from None


def _dig(value, keys, where):
    """value[k0][k1]... where each level is an object; {} past a missing key."""
    for k in keys:
        if not isinstance(value, dict):
            raise Unreadable(f"{where} has a shape the doctor does not know")
        value = value.get(k, {})
    if not isinstance(value, dict):
        raise Unreadable(f"{where} has a shape the doctor does not know")
    return value


def _commands(settings):
    """Every hook command string in a settings object, skipping shapes Claude Code would not load."""
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    for entries in (hooks.values() if isinstance(hooks, dict) else ()):
        for e in (entries if isinstance(entries, list) else ()):
            for h in (e.get("hooks") if isinstance(e, dict) and isinstance(e.get("hooks"), list) else ()):
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    yield h


# --- gather: every read, every program run ---------------------------------

def _ours(pid):
    return isinstance(pid, str) and pid.split("@")[0] == "languette"


def installs(settings_files):
    """languette's installs, each {id, version, scope, enabled, installPath[, projectPath]}:
    `claude plugin list --json`, else ~/.claude/plugins/installed_plugins.json."""
    claude = shutil.which("claude")
    if claude:
        try:
            r = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, text=True, timeout=30)
            listed = json.loads(r.stdout) if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            listed = None
        if isinstance(listed, list) and all(isinstance(x, dict) for x in listed):
            return [x for x in listed if _ours(x.get("id"))]
    path = _home() / ".claude/plugins/installed_plugins.json"
    plugins = _dig(_json(path, missing={}), ["plugins"], _tilde(path))
    out = []
    for pid, entries in plugins.items():
        if not _ours(pid):
            continue
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise Unreadable(f"{_tilde(path)} has a shape the doctor does not know")
        # The file has no enabled flag: an install counts as enabled unless a
        # settings file sets enabledPlugins[id] to false.
        off = any(isinstance(s, dict) and isinstance(s.get("enabledPlugins"), dict)
                  and s["enabledPlugins"].get(pid) is False for s in settings_files.values())
        out += [{**e, "id": pid, "enabled": not off} for e in entries]
    return out


def settings_files(cwd):
    """path -> parsed JSON (or the Unreadable) for the user's settings.json and every
    .claude/settings{,.local}.json from cwd up to, not including, $HOME."""
    home = _home()
    paths = [home / ".claude/settings.json"]
    d = Path(cwd)
    for d in (d, *d.parents):
        if d == home:
            break
        paths += [d / ".claude/settings.json", d / ".claude/settings.local.json"]
    out = {}
    for p in paths:
        try:
            out[p] = _json(p, missing={})
        except Unreadable as e:
            out[p] = e
    return out


def shfmt_version(path):
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=scan.SHFMT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)", r.stdout)
    return f"{m[1]}.{m[2]}" if m else None


def gh_signed_in():
    """True, False, or None when gh is not installed or did not answer."""
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        return subprocess.run([gh, "auth", "status"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return None


def canary(command, env, cwd, limit):
    """Send `rm -rf ~` to a hook command as Claude Code would, under /bin/sh:
    (denied, what happened, milliseconds). The command is a payload only."""
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": CANARY},
                          "cwd": cwd, "session_id": "languette-doctor"})
    wait = min(limit, WAIT_MAX)
    start = time.monotonic()
    try:
        r = subprocess.run(["/bin/sh", "-c", command], input=payload, capture_output=True, text=True, env=env,
                           cwd=cwd, timeout=wait)
    except subprocess.TimeoutExpired:
        return False, f"the hook command ran past {wait} s", None
    except OSError as e:
        return False, f"the hook command could not start ({e.strerror or e})", None
    ms = round((time.monotonic() - start) * 1000)
    if r.returncode == 2:                      # Claude Code reads exit 2 as a block
        return True, "", ms
    try:
        decision = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else None
    except (ValueError, KeyError, TypeError):
        return False, f"the hook printed something that is not a decision (exit {r.returncode})", ms
    if decision == "deny":
        return True, "", ms
    return False, f"the hook {'let it through silently' if decision is None else 'answered ' + str(decision)}" \
                  f" (exit {r.returncode})", ms


# --- rows ------------------------------------------------------------------

def in_effect(found, cwd):
    """The install in effect for cwd: the most specific project or local install
    whose projectPath holds cwd, local before project, else the user's."""
    def holds(p):
        return isinstance(p, str) and p and (cwd == p or cwd.startswith(p.rstrip("/") + "/"))
    scoped = [i for i in found if i.get("scope") in ("project", "local") and holds(i.get("projectPath"))]
    if scoped:
        return max(scoped, key=lambda i: (len(i["projectPath"]), i.get("scope") == "local"))
    rest = [i for i in found if i.get("scope") not in ("project", "local")]
    return rest[0] if rest else None


def _version(inst):
    v = str(inst.get("version") or "?")
    return v[:7] if SHA.fullmatch(v) else v


def _env_value(v):
    return "true" if v is True else "false" if v is False else v if isinstance(v, str) else json.dumps(v)


def gates(hooks):
    """Option name -> its gate, `=` (on unless false) or `!=` (on only if true),
    and the guard-recursive-delete hook, from a hooks.json object."""
    found, canary_hook = {}, None
    pre = hooks.get("hooks") if isinstance(hooks, dict) else None
    if not isinstance(pre, dict):
        raise Unreadable("hooks.json has a shape the doctor does not know")
    for h in _commands(hooks):
        m = GATE.match(h["command"])
        if m:
            found[m[1].lower()] = m[2]
        if f"--guard {CANARY_GUARD}" in h["command"] and canary_hook is None:
            canary_hook = h
    return found, canary_hook


def is_on(gate, value):
    if value is None:
        return gate == "="
    v = _env_value(value)
    return v != "false" if gate == "=" else v == "true"


def by_hand(files):
    """path -> by-hand languette hook commands in that settings file."""
    return {p: [h for h in _commands(s) if BY_HAND.search(h["command"])]
            for p, s in files.items() if not isinstance(s, Unreadable)}


def check(cwd):
    """[(mark, label, text)] for this machine, from cwd."""
    rows = []
    files = settings_files(cwd)
    user_path = _home() / ".claude/settings.json"
    hand = {p: hs for p, hs in by_hand(files).items() if hs}
    try:
        inst = in_effect(installs(files), cwd)
        problem = None
    except Unreadable as e:
        inst, problem = None, str(e)

    canary_hook, env, limit, guard_off = None, None, HOOK_TIMEOUT, False
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_PLUGIN_OPTION_")}
    if inst:
        where = f"plugin {_version(inst)}, {inst.get('scope', '?')} scope"
        root = str(inst.get("installPath") or "")
        if hand:
            names = ", ".join(_tilde(p) for p in hand)
            rows.append((FAIL, "Claude Code", f"{where}, and by-hand run.py hooks in {names}: every guard "
                                              "runs twice; remove the by-hand entries"))
        elif inst.get("enabled") is False:
            rows.append((FAIL, "Claude Code", f"{where}, is disabled: claude plugin enable {inst.get('id')}"))
        try:
            user = files[user_path]
            if isinstance(user, Unreadable):
                raise user
            options = _dig(user, ["pluginConfigs", inst.get("id") or "languette@languette", "options"],
                           f"pluginConfigs in {_tilde(user_path)}")
        except Unreadable as e:
            options, opt_problem = {}, str(e)
        else:
            opt_problem = None
        try:
            if not root:
                raise Unreadable("the install names no installPath")
            found, canary_hook = gates(_json(Path(root) / "hooks/hooks.json"))
        except Unreadable as e:
            found, hooks_problem = {}, str(e)
        else:
            hooks_problem = None
        if not hand and inst.get("enabled") is not False:
            if hooks_problem or opt_problem:
                rows.append((WARN, "Claude Code", f"{where}; {hooks_problem or opt_problem}, so which guards "
                                                  "are on is unknown"))
            else:
                off = sorted(k for k, g in found.items() if not is_on(g, options.get(k)))
                rows.append((OK, "Claude Code", f"{where}; {len(found) - len(off)} guards on, {len(off)} off"
                                                + (f": {', '.join(off)}" if off else "")))
        guard_off = not is_on("=", options.get(CANARY_GUARD.replace("-", "_")))
        env = {**base_env, "CLAUDE_PLUGIN_ROOT": root,
               **{f"CLAUDE_PLUGIN_OPTION_{k.upper()}": _env_value(v) for k, v in options.items()
                  if isinstance(k, str) and re.fullmatch(r"\w+", k) and v is not None}}
    elif hand:
        names = ", ".join(_tilde(p) for p in hand)
        count = len({m for hs in hand.values() for h in hs for m in re.findall(r"--guard ([\w-]+)", h["command"])})
        rows.append((OK, "Claude Code", f"by hand, {count} guard{'' if count == 1 else 's'} in {names}"))
        canary_hook = next((h for hs in hand.values() for h in hs if f"--guard {CANARY_GUARD}" in h["command"]), None)
        env = base_env
    elif problem:
        rows.append((WARN, "Claude Code", problem))
    else:
        rows.append((FAIL, "Claude Code", "languette is not installed for this directory"))

    try:
        path = scan.shfmt()
    except scan.Unparseable as e:
        rows.append((WARN, "shell parser", f"shfmt did not answer: {e}"))
    else:
        if path:
            rows.append((OK, "shell parser", f"shfmt {shfmt_version(path) or '(version unread)'}"))
        else:
            fallback = "bash -n checks the parse" if shutil.which("bash") else "the built-in lexer reads commands"
            rows.append((WARN, "shell parser", f"no shfmt {'.'.join(map(str, scan.SHFMT_MIN))} or newer on PATH; "
                                               f"{fallback} instead"))

    signed = gh_signed_in()
    if signed:
        rows.append((OK, "gh", "signed in"))
    else:
        rows.append((WARN, "gh", f"{'not signed in' if signed is False else 'not installed or not answering'}; the "
                                 "stacked-base and ruleset guards will ask instead of deciding"))

    if guard_off:
        rows.append((WARN, "fail-closed", f"{CANARY_GUARD} is off, so `{CANARY}` would go through; the canary "
                                          "did not run"))
    elif canary_hook is None:
        rows.append((FAIL, "fail-closed", f"no {CANARY_GUARD} hook {'in the install' if inst or hand else 'installed'}"
                                          " to send the canary to"))
    else:
        t = canary_hook.get("timeout")
        limit = t if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else HOOK_TIMEOUT
        denied, what, ms = canary(canary_hook["command"], env, cwd, limit)
        how = "through the hook command as installed"
        if denied:
            rows.append((OK, "fail-closed", f"`{CANARY}` was denied {how}, {ms} ms of {limit:g} s"))
        else:
            rows.append((FAIL, "fail-closed", f"`{CANARY}` was not denied {how}: {what}"))

    if inst:
        v = str(inst.get("version") or "")
        rows.append((WARN, "version", f"no releases yet; plugin at commit {v[:7]}" if SHA.fullmatch(v) else
                     f"plugin at {v or 'an unknown version'}; not checked against the latest release"))
    elif hand:
        rows.append((WARN, "version", "installed by hand; not checked"))
    return rows


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        cwd = os.getcwd()
    except OSError as e:
        print(f"{FAIL} {'doctor':<13} the current directory is unreadable ({e.strerror or e})")
        return 1
    rows = check(cwd)
    for mark, label, text in rows:
        print(f"{mark} {label:<13} {text}")
    return 1 if any(mark == FAIL for mark, _, _ in rows) else 0
