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
never a traceback. A ✗ never stops a later check; the exit is decided after the
last row. For guard-private-terms it also writes: --init-redacted-terms and
--init-blocked-terms a missing file, --restore-redacted-terms the defaults into
one on a yes; --redact prints what a post would become. Standard library only.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from languette import scan, terms
from languette.paths import config_dir

OK, WARN, FAIL = "✓", "!", "✗"
# A probe is (row label, guard, command): the command goes to the guard's hook as a payload.
PARSE = ("parse check", "require-well-formed", 'echo "unclosed')
CANARY = ("fail-closed", "guard-recursive-delete", "rm -rf /fake/languette-doctor")
PROBES = (PARSE, CANARY)
REASON_MAX = 100                   # characters of a deny reason the parse check row shows
HOOK_TIMEOUT = 600                 # seconds: Claude Code's default for a command hook
WAIT_MAX = 60                      # seconds the doctor waits on a probe, whatever the hook's limit
# Forge clients, gh first: name -> (sign-in probe, whether it must list a login, note). gh's
# note shows when the guards cannot read through it; another client's when the agent can act through it.
FORGES = {
    "gh": (("auth", "status"), False, "some guards ask instead"),
    "glab": (("auth", "status"), False, "partly guarded (see issue #288)"),
    "tea": (("whoami",), False, "not yet guarded (see issue #288)"),
    "fj": (("auth", "list"), True, "not yet guarded (see issue #288)"),
}
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


def _config_dir():
    return Path(config_dir({**os.environ, "HOME": str(_home())}))


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
    path = _config_dir() / "plugins/installed_plugins.json"
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
    paths = [_config_dir() / "settings.json"]
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


def signed_in(path, args, lists):
    """True, False, or None when the client did not answer. `args` exits 0 when signed in;
    when `lists`, it exits 0 either way and prints a login only when there is one."""
    try:
        r = subprocess.run([path, *args], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0 and not (lists and not r.stdout.strip())


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
    # The one hooks.json command runs every guard and joins their denies, so another guard's
    # own fail-closed deny can sit beside the probed guard's: only a deny that is all
    # fallback means no guard judged the probe.
    judged = [p for p in reason.split("\n\n") if not FALLBACK.search(p)] if isinstance(reason, str) else []
    if decision == "deny" and isinstance(reason, str) and not judged:
        return False, f"only the fallback denied it, so the guard never judged it: {reason.split('. ')[0]}", ms
    if decision == "deny":
        return True, (one_line(judged[0]) if judged else "") or "no reason given", ms
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


def _options(files, user_path, inst):
    """The installed plugin's options from the user's settings file; Unreadable when it will not say."""
    user = files[user_path]
    if isinstance(user, Unreadable):
        raise user
    return _dig(user, ["pluginConfigs", inst.get("id") or "languette@languette", "options"],
                f"pluginConfigs in {_tilde(user_path)}")


def _option_env(options):
    """Each option as the environment variable Claude Code gives the plugin's hooks."""
    return {terms.option_env(k): _env_value(v) for k, v in options.items()
            if isinstance(k, str) and re.fullmatch(r"\w+", k) and v is not None}


def gates(hooks):
    """Option name -> its gate, `=` (on unless false) or `!=` (on only if true), as run.py
    reads them, and the first hook of each probed guard, from a hooks.json object. A
    command that names no guard (the plugin's) runs every guard, so it takes every probe."""
    pre = hooks.get("hooks") if isinstance(hooks, dict) else None
    if not isinstance(pre, dict):
        raise Unreadable("hooks.json has a shape the doctor does not know")
    try:
        from languette import run
        found = run.gates()
    except BaseException as e:  # noqa: BLE001 -- run.py exits when a guard will not import
        raise Unreadable(f"the guards did not load ({type(e).__name__}: {e})")
    probed = {}
    for h in _commands(hooks):
        if "languette/run.py" not in h["command"]:
            continue
        for _, guard, _ in PROBES:
            if f"--guard {guard}" in h["command"] or "--guard" not in h["command"]:
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


def _titles(root):
    """Option name -> its one-line title from the install's plugin.json; {} when it will not say."""
    try:
        conf = _json(Path(root) / ".claude-plugin/plugin.json").get("userConfig")
    except (Unreadable, AttributeError):
        return {}
    return {k: v["title"] for k, v in conf.items() if isinstance(v, dict) and isinstance(v.get("title"), str)} \
        if isinstance(conf, dict) else {}


def line(mark, text, *children):
    """A detail line beneath a row: its mark ("" for a bare line), text and its own lines."""
    return mark, text, list(children)


def worst(marks):
    return FAIL if FAIL in marks else WARN if WARN in marks else OK


def check(cwd):
    """[(mark, label, text, [detail lines])] for this machine, from cwd, in the order printed:
    version, shell parser, the probes, Claude Code with its guards beneath, the forge clients,
    the terms files. A ✗ never stops a later check."""
    files = settings_files(cwd)
    user_path = _config_dir() / "settings.json"
    hand = {p: hs for p, hs in by_hand(files).items() if hs}
    try:
        inst = in_effect(installs(files), cwd)
        problem = None
    except Unreadable as e:
        inst, problem = None, str(e)

    options = {}
    claude = None                            # the Claude Code row
    probed, env, not_run = {}, None, {}      # guard -> trusted hook; guard -> why its probe did not run
    # A probe's environment is an allowlist, not the doctor's own.
    base_env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    if inst:
        where = f"plugin {_version(inst)}, {inst.get('scope', '?')} scope"
        root = str(inst.get("installPath") or "")
        if hand:
            names = ", ".join(_tilde(p) for p in hand)
            claude = (FAIL, "Claude Code", f"{where}, and by-hand run.py hooks in {names}: every guard "
                                           "runs twice; remove the by-hand entries", [])
        elif inst.get("enabled") is False:
            claude = (FAIL, "Claude Code", f"{where}, is disabled: claude plugin enable {inst.get('id')}", [])
        try:
            options = _options(files, user_path, inst)
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
        if claude is None:
            if hooks_problem or opt_problem:
                claude = (WARN, "Claude Code", f"{where}; {hooks_problem or opt_problem}, so which guards "
                                               "are on is unknown", [])
            else:
                on = [k for k, g in found.items() if is_on(g, options.get(k))]
                # Disabled is a default-on guard turned off; an opt-in guard nobody opted into is not.
                off = sorted(k for k, g in found.items() if g == "=" and k not in on)
                titles = _titles(root)
                claude = (OK, "Claude Code", where, [
                    line(OK, f"guards enabled: {len(on)}"),
                    line(WARN if off else OK, f"guards disabled: {len(off)}",
                         *(line(WARN, f"(off) {k}: {titles.get(k, '')}".rstrip()) for k in off))])
        for _, guard, sent in PROBES:
            key = guard.replace("-", "_")
            if inst.get("enabled") is False:
                not_run[guard] = "the plugin is disabled, so its hooks do not run; the probe did not run"
            elif not is_on(found.get(key, "="), options.get(key)):
                not_run[guard] = f"{guard} is off, so `{sent}` would go through; the probe did not run"
        env = {**base_env, "CLAUDE_PLUGIN_ROOT": root, **_option_env(options)}
    elif hand:
        names = ", ".join(_tilde(p) for p in hand)
        count = len({m for hs in hand.values() for h in hs for m in re.findall(r"--guard ([\w-]+)", h["command"])})
        claude = (OK, "Claude Code", f"by hand, {count} guard{'' if count == 1 else 's'} in {names}", [])
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
        claude = (WARN, "Claude Code", problem, [])
    else:
        claude = (FAIL, "Claude Code", "languette is not installed for this directory", [])

    rows = []
    if inst:
        v = str(inst.get("version") or "")
        rows.append((WARN, "version", f"plugin at commit {v[:7]}, from main; not a release" if SHA.fullmatch(v) else
                     f"plugin at {v or 'an unknown version'}; not checked against the latest release", []))
    elif hand:
        rows.append((WARN, "version", "installed by hand; not checked", []))

    try:
        path = scan.shfmt()
    except scan.Unparseable as e:
        rows.append((WARN, "shell parser", f"shfmt did not answer: {e}", []))
    else:
        if path:
            rows.append((OK, "shell parser", f"shfmt {shfmt_version(path) or '(version unread)'}", []))
        else:
            fallback = "bash -n checks the parse" if shutil.which("bash") else "the built-in lexer reads commands"
            rows.append((WARN, "shell parser", f"no shfmt {'.'.join(map(str, scan.SHFMT_MIN))} or newer on PATH; "
                                               f"{fallback} instead", []))

    for p in PROBES:
        label, guard, sent = p
        hook = probed.get(guard)
        if guard in not_run:
            rows.append((WARN, label, not_run[guard], []))
        elif hook is None:
            # A by-hand install may carry only some guards; a plugin's hooks.json carries both.
            absent = f"no {guard} hook {'in the install' if inst or hand else 'installed'} to send the probe to"
            rows.append((FAIL if p == CANARY or inst else WARN, label, absent, []))
        else:
            t = hook.get("timeout")
            limit = t if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 else HOOK_TIMEOUT
            denied, what, ms = probe(hook["command"], env, cwd, limit, sent)
            how = "through the hook command as installed"
            if denied and p == PARSE:
                rows.append((OK, label, f"`{sent}` was denied: {what}, {ms} ms", []))
            elif denied:
                rows.append((OK, label, f"`{sent}` was denied {how}, {ms} ms of {limit:g} s", []))
            else:
                rows.append((FAIL, label, f"`{sent}` was not denied {how}: {what}", []))
    rows.append(claude)

    paths = {name: shutil.which(name) for name in FORGES}
    # The probes may reach the network: in parallel, a dead one costs one timeout, not one per client.
    with ThreadPoolExecutor() as pool:
        answers = {name: pool.submit(signed_in, path, *FORGES[name][:2]) for name, path in paths.items() if path}
    for name, (_, _, note) in FORGES.items():
        if name not in answers:
            if name == "gh":
                rows.append((WARN, name, f"not installed; {note}", []))
            continue
        signed = answers[name].result()
        state = {True: "signed in", False: "installed, not signed in", None: "installed, not answering"}[signed]
        quiet = signed is True if name == "gh" else signed is False
        rows.append((OK, name, state, []) if quiet else (WARN, name, f"{state}; {note}", []))
    return rows + terms_rows(options)


def render(rows):
    """The lines printed for rows: a row, then its detail lines indented beneath it."""
    def details(lines, depth):
        for mark, text, sub in lines:
            yield f"{'    ' * depth}{mark + ' ' if mark else '  '}{text}"
            yield from details(sub, depth + 1)
    for mark, label, text, lines in rows:
        yield f"{mark} {label:<13} {text}"
        yield from details(lines, 1)


# --- guard-private-terms' files, through the guard's own loader --------------

# What each accepted re: is timed over; shown, never the verdict.
SAMPLE = Path(__file__).resolve().parent.parent / "features/fixtures/private-terms/bad-comment.md"
FIRST = 32                                 # characters of a refused line shown beneath its reason
LABELS = {"redacted": "redacted terms", "blocked": "blocked terms"}


def _env(options):
    """The guard's environment, as the installed plugin's options give it."""
    return {**os.environ, "HOME": str(_home()), **_option_env(options)}


def _terms(options):
    """(penv, kind -> (text, path, whether an option named it, the exception or None)): each terms
    file read as the guard reads it, and the environment its $NAMEs are filled from."""
    from languette.run import drive          # run.py exits when a guard will not import
    from languette.world import World
    env = _env(options)
    world = World(env, {})
    penv = drive(terms.environment(env), world, [])
    return penv, {kind: drive(terms.read(kind, env), world, []) for kind in terms.KINDS}


def _ms(rx, text):
    start = time.perf_counter()
    rx.sub("", text)
    return (time.perf_counter() - start) * 1000


def _file_lines(kind, text, path, penv):
    """(the detail lines for a terms file that loaded, its entry count): the count, every line the
    guard would refuse with the start of that line beneath it, and its re: lines counted and timed."""
    found = list(terms.entries(text, kind, penv))
    bad = [(n, raw, item) for n, raw, item in found if isinstance(item, terms.BadTerms)]
    good = [item for _, _, item in found if isinstance(item, terms.Term)]
    count = f"{len(found)} entr{'y' if len(found) == 1 else 'ies'}"
    out = [line(WARN if not found else OK, f"{_tilde(path)} ({count})")]
    for n, raw, err in bad:
        first = raw if len(raw) <= FIRST else raw[:FIRST - 1] + "…"
        out.append(line(FAIL, f"line {n}: {err.why}", line("", first)))
    invalid = sum(err.is_re for _, _, err in bad)
    res = sum(t.is_re for t in good) + invalid
    if res:
        try:
            sample = SAMPLE.read_text(encoding="utf-8")
        except OSError:
            sample = None
        times = [_ms(t.rx, sample) for t in good if t.is_re and t.rx] if sample is not None else []
        timed = f" (min={min(times):.2f}ms, max={max(times):.2f}ms, avg={sum(times) / len(times):.2f}ms)" \
            if times else ""
        out.append(line(FAIL if invalid else OK, f"{res} regular expression{'' if res == 1 else 's'}"
                        f"{f', {invalid} invalid' if invalid else ''}{timed}"))
    return out, count


def terms_rows(options):
    """A row per terms file, as the guard would read it: the entries in it counted, each line it
    would refuse named, its re: lines timed; what loads but is empty is a !; what does not load is
    a ✗, since every public post is denied until it does; off, the files are reported and nothing
    is a ✗."""
    on = is_on("=", options.get("guard_private_terms"))
    penv, read = _terms(options)
    rows = []
    for kind, label in LABELS.items():
        text, path, named, err = read[kind]
        option, where = terms.option_name(kind), _tilde(path)
        if err:
            why = "is a directory" if isinstance(err, ValueError) and os.path.isdir(path) else terms.why_not(err)
            until = "does" if why == "does not exist" else "is fixed"
            text_ = (f"{option} is {where}, which {why}: every public post is denied until it {until}" if named
                     else f"{where} {why}: every public post is denied until it {until}")
            rows.append((FAIL if on else WARN, label, text_ if on else f"off, and {where} {why}", []))
        elif text is None and not on:
            rows.append((OK, label, f"off, and none at {where}", []))
        elif text is None and kind == "redacted":
            rows.append((WARN, label, f"none at {where}: nothing is redacted",
                         [line(WARN, "run `languette doctor --init-redacted-terms` to write the defaults")]))
        elif text is None:
            rows.append((WARN, label, f"none at {where}, and {option} is unset: no term is blocked", []))
        else:
            lines, count = _file_lines(kind, text, path, penv)
            if on:
                rows.append((worst([m for m, _, _ in lines]), label, "enabled", lines))
            else:
                bad = any(m == FAIL for m, _, _ in lines)
                rows.append((WARN if bad else OK, label, f"off, and {where} ({count})", []))
    return rows


def _loaded(kind, text, path, penv):
    """The kind's terms, or None after printing each line the guard would refuse."""
    found = list(terms.entries(text, kind, penv))
    bad = [item for _, _, item in found if isinstance(item, terms.BadTerms)]
    for err in bad:
        print(f"{FAIL} {_tilde(path)} {err}")
    return None if bad else [item for _, _, item in found]


def redact(file, options):
    """Print `file`, stdin for none or "-", as a post would leave through the files as loaded, then
    which blocked terms it holds. Exits 1 when any, or when a file would not load."""
    try:
        text = sys.stdin.read() if file in (None, "-") else Path(file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{FAIL} {file} {terms.why_not(e)}")
        return 1
    penv, read = _terms(options)
    loaded = {}
    for kind, (body, path, _, err) in read.items():
        if err:
            print(f"{FAIL} {_tilde(path)} {terms.why_not(err)}")
            return 1
        loaded[kind] = [] if body is None else _loaded(kind, body, path, penv)
        if loaded[kind] is None:
            return 1
    print(terms.redact(text, terms.pairs(loaded["redacted"])).rstrip("\n"))
    found = terms.hits(text, loaded["blocked"])
    print("blocked: " + (terms.named(found) if found else "none"))
    return 1 if found else 0


def _defaults():
    return terms.defaults(Path(terms.DEFAULTS).read_text(encoding="utf-8"))


def write_initial(kind, options):
    """(mark, text): write the kind's file where the guard reads it, the redacted file with every
    default, the blocked one with a header and no terms; None where a file is already there."""
    path, _ = terms.where(kind, _env(options))
    if os.path.lexists(path):
        return None
    where = _tilde(path)
    if kind == "redacted":
        groups = _defaults()
        body, what = terms.initial(groups), f"{len(groups)} defaults"
    else:
        body = terms.header("blocked") + "\n# A term that denies a whole public post: find, a message for the agent, comment.\n"
        what = "no terms yet"
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(body, encoding="utf-8")
    except OSError as e:
        return FAIL, f"{where} cannot be written ({e.strerror or e})"
    return OK, f"wrote {where} ({what})"


def default_terms_rows(cwd):
    """[(mark, label, text)]: the default redacted terms file written where the installed plugin's
    options say the guard reads it, as --init-redacted-terms does; a file already there is left
    alone and says nothing."""
    options = installed_options(cwd)
    if not terms.where("redacted", _env(options))[0]:
        return []
    done = write_initial("redacted", options)
    return [(done[0], "redacted terms", done[1])] if done else []


def init(kind, options):
    """Write the kind's file, never over one that exists."""
    done = write_initial(kind, options)
    if done is None:
        path, _ = terms.where(kind, _env(options))
        repair = "; to repair it: languette doctor --restore-redacted-terms" if kind == "redacted" else ""
        done = FAIL, f"{_tilde(path)} exists{repair}"
    print(f"{done[0]} {done[1]}")
    return 1 if done[0] == FAIL else 0


def restore(options):
    """Repair the defaults in the redacted terms file: show the diff, write it on a yes."""
    import difflib
    path, _ = terms.where("redacted", _env(options))
    where = _tilde(path)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"{FAIL} none at {where}; to create it: languette doctor --init-redacted-terms")
        return 1
    except (OSError, UnicodeDecodeError) as e:
        print(f"{FAIL} {where} {terms.why_not(e)}")
        return 1
    new, notes = terms.restore(text, _defaults())
    for note in notes:
        print(f"{WARN if 'edited' in note else OK} {note}")
    if new == text:
        print(f"{OK} {where} holds every default as it is now; nothing to write")
        return 0
    sys.stdout.writelines(difflib.unified_diff(text.splitlines(True), new.splitlines(True), where, where))
    try:
        answer = input("Write it? [y/N] ")
    except EOFError:
        answer = ""
    if answer.strip().lower() not in ("y", "yes"):
        print(f"{WARN} {where} left as it was")
        return 0
    # Whole or untouched: a cut-off write would leave the only file that redacts half gone.
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        Path(tmp).write_text(new, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        print(f"{FAIL} {where} cannot be written ({e.strerror or e})")
        return 1
    print(f"{OK} wrote {where}")
    return 0


def installed_options(cwd):
    """The options of the plugin in effect for cwd, {} where there is none or its settings will not say."""
    files = settings_files(cwd)
    try:
        inst = in_effect(installs(files), cwd)
        return _options(files, _config_dir() / "settings.json", inst) if inst else {}
    except Unreadable:
        return {}


def main(args=None):
    """`args`: the parsed doctor options (redact, init_redacted_terms, init_blocked_terms,
    restore_redacted_terms); none runs the checks."""
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        cwd = os.getcwd()
    except OSError as e:
        print(f"{FAIL} {'doctor':<13} the current directory is unreadable ({e.strerror or e})")
        return 1
    if args is not None:
        if args.redact is not False:
            return redact(args.redact, installed_options(cwd))
        if args.init_redacted_terms:
            return init("redacted", installed_options(cwd))
        if args.init_blocked_terms:
            return init("blocked", installed_options(cwd))
        if args.restore_redacted_terms:
            return restore(installed_options(cwd))
    rows = check(cwd)
    for text in render(rows):
        print(text)
    problems = sum(mark == FAIL for mark, _, _, _ in rows)
    code = 1 if problems else 0
    print(f"{problems} problem{'' if problems == 1 else 's'}; exit {code}")
    return code
