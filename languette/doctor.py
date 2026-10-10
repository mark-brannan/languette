"""`languette doctor`: say whether languette protects Claude Code on this
machine, one row per check, each ✓, ! or ✗. Exits 1 on any ✗, so CI can run it.

The doctor reads settings and runs programs, so it sits outside the pure
steps of the guard pipeline (docs/design/guard-pipeline.md): no guard imports
it. It writes nothing. Two probes each send one command to an installed hook as
a JSON payload, the way Claude Code would: a command that does not parse, to
require-well-formed, and a recursive delete of a fake path, to
guard-recursive-delete. Nothing here ever runs either command.
Only trusted hooks get a probe: the plugin's own hooks.json and by-hand
entries in the user's ~/.claude/settings.json. A project's settings arrive
with whatever was checked out, so their hooks are counted, never run.
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
# A probe is (row label, guard, command): the command goes to the guard's hook as a payload.
PARSE = ("parse check", "require-well-formed", 'echo "unclosed')
CANARY = ("fail-closed", "guard-recursive-delete", "rm -rf /fake/languette-doctor")
PROBES = (PARSE, CANARY)
REASON_MAX = 100                   # characters of a deny reason the parse check row shows
HOOK_TIMEOUT = 600                 # seconds: Claude Code's default for a command hook
WAIT_MAX = 60                      # seconds the doctor waits on a probe, whatever the hook's limit
# The gate each hooks.json command opens with: `= false` runs the guard unless
# its option is exactly false, `!= true` (an opt-in guard) only when exactly true.
GATE = re.compile(r'^\[ "\$\{CLAUDE_PLUGIN_OPTION_(\w+)-\}" (=|!=) (true|false) \]')
BY_HAND = re.compile(r"languette/run\.py")
SHA = re.compile(r"[0-9a-f]{7,40}")
# A deny that came from the wrapper, the loader or a crash, not the guard: run.py is
# missing, a guard failed to import or raised, or the payload was refused. Fail-closed, but nothing judged.
FALLBACK = re.compile(r"This is a gate and fails closed|^languette: (a guard failed to load|unreadable hook payload)"
                      r"|^[\w-]+: guard crashed \(")


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


def one_line(reason):
    """A deny reason on one short line: its first sentence, the parenthesised detail if it has one."""
    first = " ".join(reason.split()).split(". ")[0].rstrip(".")
    m = re.search(r"\((.+)\)", first)
    text = m[1] if m else first
    return text if len(text) <= REASON_MAX else text[:REASON_MAX - 1] + "…"


def probe(command, env, cwd, limit, sent):
    """Send `sent` to a hook command as Claude Code would, under /bin/sh:
    (denied, why it was denied or what went wrong, milliseconds). `sent` is a payload only."""
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": sent},
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
        return True, one_line(r.stderr) or "no reason given", ms
    try:
        out = json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else {}
        decision, reason = out.get("permissionDecision"), out.get("permissionDecisionReason")
    except (ValueError, KeyError, TypeError, AttributeError):
        return False, f"the hook printed something that is not a decision (exit {r.returncode})", ms
    if decision == "deny" and isinstance(reason, str) and FALLBACK.search(reason):
        return False, f"only the fallback denied it, so the guard never judged it: {reason.split('. ')[0]}", ms
    if decision == "deny":
        return True, (one_line(reason) if isinstance(reason, str) else "") or "no reason given", ms
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
    and the first hook of each probed guard, from a hooks.json object."""
    found, probed = {}, {}
    pre = hooks.get("hooks") if isinstance(hooks, dict) else None
    if not isinstance(pre, dict):
        raise Unreadable("hooks.json has a shape the doctor does not know")
    for h in _commands(hooks):
        m = GATE.match(h["command"])
        if m:
            found[m[1].lower()] = m[2]
        for _, guard, _ in PROBES:
            if f"--guard {guard}" in h["command"]:
                probed.setdefault(guard, h)
    return found, probed


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

    probed, env, not_run = {}, None, {}      # guard -> trusted hook; guard -> why its probe did not run
    # A probe's environment is an allowlist, not the doctor's own.
    base_env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
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
            found, probed = gates(_json(Path(root) / "hooks/hooks.json"))
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
        for _, guard, sent in PROBES:
            key = guard.replace("-", "_")
            if inst.get("enabled") is False:
                not_run[guard] = "the plugin is disabled, so its hooks do not run; the probe did not run"
            elif not is_on(found.get(key, "="), options.get(key)):
                not_run[guard] = f"{guard} is off, so `{sent}` would go through; the probe did not run"
        env = {**base_env, "CLAUDE_PLUGIN_ROOT": root,
               **{f"CLAUDE_PLUGIN_OPTION_{k.upper()}": _env_value(v) for k, v in options.items()
                  if isinstance(k, str) and re.fullmatch(r"\w+", k) and v is not None}}
    elif hand:
        names = ", ".join(_tilde(p) for p in hand)
        count = len({m for hs in hand.values() for h in hs for m in re.findall(r"--guard ([\w-]+)", h["command"])})
        rows.append((OK, "Claude Code", f"by hand, {count} guard{'' if count == 1 else 's'} in {names}"))
        # Only the user's own file supplies a command to run: a project's settings
        # come with whatever repository was checked out, and the doctor runs in CI.
        for _, guard, _ in PROBES:
            flag = f"--guard {guard}"
            hook = next((h for h in hand.get(user_path, []) if flag in h["command"]), None)
            if hook:
                probed[guard] = hook
            elif any(flag in h["command"] for hs in hand.values() for h in hs):
                not_run[guard] = (f"the by-hand {guard} hook is in a project's settings, and the doctor runs no "
                                  "command a project supplies; the probe did not run")
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

    for p in PROBES:
        label, guard, sent = p
        hook = probed.get(guard)
        if guard in not_run:
            rows.append((WARN, label, not_run[guard]))
        elif hook is None:
            # A by-hand install may carry only some guards; a plugin's hooks.json carries both.
            absent = f"no {guard} hook {'in the install' if inst or hand else 'installed'} to send the probe to"
            rows.append((FAIL if p == CANARY or inst else WARN, label, absent))
        else:
            t = hook.get("timeout")
            limit = t if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else HOOK_TIMEOUT
            denied, what, ms = probe(hook["command"], env, cwd, limit, sent)
            how = "through the hook command as installed"
            if denied and p == PARSE:
                rows.append((OK, label, f"`{sent}` was denied: {what}, {ms} ms"))
            elif denied:
                rows.append((OK, label, f"`{sent}` was denied {how}, {ms} ms of {limit:g} s"))
            else:
                rows.append((FAIL, label, f"`{sent}` was not denied {how}: {what}"))

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
