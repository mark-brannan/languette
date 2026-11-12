"""The host layer: what `languette install`, `uninstall`, `doctor` and `config` read of the
coding agent they wire languette into, how they run its command, and how they ask the user.
Only Claude Code is a host today; other hosts are planned (#5).

Claude Code owns its files: this reads its settings and its plugin listing, and runs the
`claude` command, but writes nothing. Each command lists the plugins once: the answer is kept
for the rest of the process, since only install's own `claude plugin install` changes it, and
install reads nothing of the listing after that. Like the commands it serves, this sits
outside the guard pipeline: no guard imports it. Standard library only.
"""

import functools
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from languette import terms
from languette.paths import config_dir as _config_dir

OK, WARN, FAIL = "✓", "!", "✗"
HOSTS = ("claude",)                        # the coding agents languette installs into
MARKETPLACE = "languette"                  # the name in .claude-plugin/marketplace.json
HOME_PAGE = "https://github.com/mark-brannan/languette"
REPO = HOME_PAGE.removeprefix("https://github.com/")
SOURCE = REPO + "#release"                 # owner/repo#ref, as `claude` reads it
PLUGIN = "languette@languette"
STEP_TIMEOUT = 120                         # seconds for each `claude plugin` command
LIST_TIMEOUT = 30                          # seconds for `claude plugin list --json`
SHA = re.compile(r"[0-9a-f]{7,40}")        # a version that is a commit


class Unreadable(Exception):
    """A file the host layer needs is missing, not JSON, or not in a shape it knows."""


# --- where things are, and how a path is shown --------------------------------

def home():
    return Path(os.environ.get("HOME") or Path.home())


def config_dir():
    """The host's configuration directory, ~/.claude unless CLAUDE_CONFIG_DIR moves it."""
    return Path(_config_dir({**os.environ, "HOME": str(home())}))


def user_settings():
    return config_dir() / "settings.json"


def tilde(path):
    """`path` as the user would write it: ~ for $HOME at its start."""
    h, p = str(home()), str(path)
    return "~" + p[len(h):] if p == h or p.startswith(h.rstrip("/") + "/") else p


def read_json(path, missing=None):
    """The JSON in `path`, `missing` when there is no file, or Unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if missing is not None:
            return missing
        raise Unreadable(f"{tilde(path)} is missing") from None
    except (OSError, UnicodeDecodeError) as e:
        raise Unreadable(f"{tilde(path)} is unreadable ({getattr(e, 'strerror', None) or e})") from None
    except ValueError:
        raise Unreadable(f"{tilde(path)} is not JSON") from None


def dig(value, keys, where):
    """value[k0][k1]... where each level is an object; {} past a missing key."""
    for k in keys:
        if not isinstance(value, dict):
            raise Unreadable(f"{where} has a shape the doctor does not know")
        value = value.get(k, {})
    if not isinstance(value, dict):
        raise Unreadable(f"{where} has a shape the doctor does not know")
    return value


# --- the claude command ------------------------------------------------------

def first_line(r):
    """The first line a finished command said, stderr before stdout."""
    for text in (r.stderr, r.stdout):
        for ln in (text or "").splitlines():
            if ln.strip():
                return ln.strip()
    return f"exit {r.returncode}, no output"


def call(claude, *args, stdin=None):
    """(CompletedProcess or None, what went wrong when it did not run)."""
    try:
        return subprocess.run([claude, *args], input=stdin, capture_output=True, text=True, timeout=STEP_TIMEOUT), None
    except subprocess.TimeoutExpired:
        return None, f"`claude {' '.join(args)}` ran past {STEP_TIMEOUT} s"
    except OSError as e:
        return None, f"`claude {' '.join(args)}` could not start ({e.strerror or e})"


def ours_source(source):
    """`source` names this repo: owner/repo, or a GitHub URL of it, any case, with or without .git."""
    s = source.lower().split("#")[0].rstrip("/").removesuffix(".git")
    return s == REPO.lower() or s.endswith("github.com/" + REPO.lower()) or s.endswith("github.com:" + REPO.lower())


def ours_plugin(pid):
    """`pid` is a languette plugin id, from whichever marketplace."""
    return isinstance(pid, str) and pid.split("@")[0] == "languette"


def _source(m):
    """Where a listed marketplace comes from: owner/repo for GitHub, else its url or path."""
    for key in ("repo", "url", "path"):
        if isinstance(m.get(key), str) and m[key]:
            return m[key]
    return str(m.get("source") or "an unknown source")


def marketplace(claude):
    """(source of the marketplace named languette or None when none is listed, why the list is unknown)."""
    r, why = call(claude, "plugin", "marketplace", "list", "--json")
    if why or r.returncode != 0:
        return None, why or f"`claude plugin marketplace list --json` failed: {first_line(r)}"
    try:
        listed = json.loads(r.stdout)
    except ValueError:
        return None, "`claude plugin marketplace list --json` printed no JSON"
    found = [m for m in listed if isinstance(m, dict) and m.get("name") == MARKETPLACE] \
        if isinstance(listed, list) else []
    return (_source(found[0]) if found else None), None


# --- what is installed -------------------------------------------------------

@functools.cache
def _plugin_list(claude):
    """`claude plugin list --json` as a list of objects, or None when it will not say; once a process."""
    try:
        r = subprocess.run([claude, "plugin", "list", "--json"], capture_output=True, text=True, timeout=LIST_TIMEOUT)
        listed = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return listed if isinstance(listed, list) and all(isinstance(x, dict) for x in listed) else None


def installs(files):
    """languette's installs, each {id, version, scope, enabled, installPath[, projectPath]}:
    `claude plugin list --json`, else ~/.claude/plugins/installed_plugins.json. `files` is
    settings_files' answer, for the enabled flag the second has not got."""
    claude = shutil.which("claude")
    listed = _plugin_list(claude) if claude else None
    if listed is not None:
        return [x for x in listed if ours_plugin(x.get("id"))]
    path = config_dir() / "plugins/installed_plugins.json"
    plugins = dig(read_json(path, missing={}), ["plugins"], tilde(path))
    out = []
    for pid, entries in plugins.items():
        if not ours_plugin(pid):
            continue
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise Unreadable(f"{tilde(path)} has a shape the doctor does not know")
        # The file has no enabled flag: an install counts as enabled unless a
        # settings file sets enabledPlugins[id] to false.
        off = any(isinstance(s, dict) and isinstance(s.get("enabledPlugins"), dict)
                  and s["enabledPlugins"].get(pid) is False for s in files.values())
        out += [{**e, "id": pid, "enabled": not off} for e in entries]
    return out


def settings_files(cwd):
    """path -> parsed JSON (or the Unreadable) for the user's settings.json and every
    .claude/settings{,.local}.json from cwd up to, not including, $HOME. Wider than the files
    Claude Code reads, which `layers` lists."""
    h = home()
    paths = [user_settings()]
    d = Path(cwd)
    for d in (d, *d.parents):
        if d == h:
            break
        paths += [d / ".claude/settings.json", d / ".claude/settings.local.json"]
    out = {}
    for p in paths:
        try:
            out[p] = read_json(p, missing={})
        except Unreadable as e:
            out[p] = e
    return out


# Where an administrator's managed-settings.json sits (code.claude.com/docs/en/managed-settings).
MANAGED = {"darwin": "/Library/Application Support/ClaudeCode/managed-settings.json",
           "win32": r"C:\Program Files\ClaudeCode\managed-settings.json"}
MANAGED_ELSE = "/etc/claude-code/managed-settings.json"     # Linux and WSL


def platform():
    """This platform as Claude Code names it in sandbox.enabledPlatforms: macos, windows, wsl or linux."""
    if sys.platform in ("darwin", "win32"):
        return {"darwin": "macos", "win32": "windows"}[sys.platform]
    try:
        wsl = "microsoft" in Path("/proc/version").read_text(encoding="utf-8").lower()
    except OSError:
        wsl = False
    return "wsl" if wsl else "linux"


def _repo_root(cwd):
    """Where Claude Code keeps .claude/settings.local.json: the git root above cwd, the main
    checkout's for a worktree, or cwd itself outside a repository, where the root is $HOME, or on
    Windows."""
    h, d = home(), Path(cwd)
    if sys.platform == "win32":
        return d
    for p in (d, *d.parents):
        if (p / ".git").exists():
            try:                                # a worktree's .git is a file: gitdir: <main>/.git/worktrees/<name>
                m = re.match(r"gitdir: (.+)", (p / ".git").read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                m = None
            gitdir = Path(m[1].strip()) if m else None
            if gitdir and gitdir.parent.name == "worktrees" and gitdir.parents[1].name == ".git":
                p = gitdir.parents[2]
            return d if p == h else p
    return d


def layers(cwd):
    """[(scope, path, parsed JSON or the Unreadable)], highest precedence first, for the settings
    files Claude Code reads in a session started at cwd: managed, project local (the repo root's,
    then an earlier version's beside cwd), shared project, user. MDM, server-managed settings and
    --settings are not files here, so a key none of these sets is not known to be unset."""
    local = [_repo_root(cwd) / ".claude/settings.local.json"]
    if Path(cwd) / ".claude/settings.local.json" != local[0]:
        local.append(Path(cwd) / ".claude/settings.local.json")
    found = [("managed", Path(MANAGED.get(sys.platform, MANAGED_ELSE))), *(("local", p) for p in local),
             ("project", Path(cwd) / ".claude/settings.json"), ("user", user_settings())]
    out = []
    for scope, p in found:
        try:
            out.append((scope, p, read_json(p, missing={})))
        except Unreadable as e:
            out.append((scope, p, e))
    return out


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


def version(inst):
    """An install's version, a commit shortened to seven characters."""
    v = str(inst.get("version") or "?")
    return v[:7] if SHA.fullmatch(v) else v


def env_value(v):
    """An option's value as the hook's environment gives it."""
    return "true" if v is True else "false" if v is False else v if isinstance(v, str) else json.dumps(v)


def plugin_options(files, inst):
    """The plugin's options from the user's settings file; Unreadable when it will not say."""
    path = user_settings()
    user = files[path]
    if isinstance(user, Unreadable):
        raise user
    return dig(user, ["pluginConfigs", inst.get("id") or PLUGIN, "options"], f"pluginConfigs in {tilde(path)}")


def installed_options(cwd):
    """The options of the plugin in effect for cwd, {} where there is none or its settings will not say."""
    files = settings_files(cwd)
    try:
        inst = in_effect(installs(files), cwd)
        return plugin_options(files, inst) if inst else {}
    except Unreadable:
        return {}


def option_env(options):
    """Each option as the environment variable Claude Code gives the plugin's hooks."""
    return {terms.option_env(k): env_value(v) for k, v in options.items()
            if isinstance(k, str) and re.fullmatch(r"\w+", k) and v is not None}


def guard_env(options):
    """The guards' environment, as the installed plugin's options give it."""
    return {**os.environ, "HOME": str(home()), **option_env(options)}


# --- the user ----------------------------------------------------------------

def confirm(question):
    """Ask `question` [y/N] on stdin: True only for y or yes. Off a terminal, the answer
    read ends the question's line, since no echoed Enter does."""
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:
        answer = ""
    if not sys.stdin.isatty():
        print()
    return answer.strip().lower() in ("y", "yes")
