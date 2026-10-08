"""Engines and the step vocabulary for features/*.feature.

Every scenario runs once per engine its feature is tagged with: @python runs
languette/ in-process twice, as the "python" engine on the parser ladder's awk
rung and as "shfmt" on its shfmt rung (skipped without a shfmt new enough,
except under CI); @shell runs hooks/<guard>.sh by subprocess (under
$AWK_PATH's awk when set). @shell_only narrows a scenario to the shell,
@shfmt_only to the shfmt rung; @no_shfmt drops the shfmt rung, for a row its
parse check denies before any guard reads it. The feature's name is the guard's name, except
guard-unparsable, which has its own guard. @python_only narrows a scenario to the
awk rung.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hamcrest import assert_that, equal_to
from pytest_bdd import given, parsers, then, when

from matchers import Verdict, asks, denies, is_silent, warns_about

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from languette import run, scan  # noqa: E402

ENGINES = ("python", "shfmt", "shell")
IN_PROCESS = {"python": ("awk",), "shfmt": ("shfmt",)}   # engine -> scan.RUNGS
# Never inherited from the caller's shell: each would change a verdict.
SCRUB = ("LANGUETTE_RM_ALLOW", "LANGUETTE_PERM_ALLOW", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "GH_FAIL", "GH_TAB",
         "TIMEOUT_HANG", "LANGUETTE_STUB_LOG", "PROSE_BUDGET", "PROSE_BUDGET_FAIL", "PROSE_BUDGET_CRASH",
         "CLAUDE_CODE_TMPDIR", "CLAIM_STAMP_BIN", "GH_RULES", "GH_PROTECTION", "XDG_CACHE_HOME")


_REAL_HOME = os.environ.get("HOME")


def pytest_configure(config):
    # A throwaway $HOME for the whole run, so no verdict depends on, and no
    # step can touch, the real one. {HOME}/project is the default cwd. Not
    # under /tmp: guard-recursive-delete allows all of /tmp, so every target would pass.
    home = tempfile.mkdtemp(prefix="languette-home-", dir="/var/tmp")
    os.mkdir(os.path.join(home, "project"))
    os.environ["HOME"] = home


def pytest_unconfigure(config):
    home = os.environ["HOME"]
    if _REAL_HOME is None:
        del os.environ["HOME"]
    else:
        os.environ["HOME"] = _REAL_HOME
    if os.path.basename(home).startswith("languette-home-"):
        shutil.rmtree(home, ignore_errors=True)


def pytest_generate_tests(metafunc):
    marks = {m.name for m in metafunc.definition.iter_markers()}
    engines = [e for e in ENGINES if e in marks or (e == "shfmt" and "python" in marks)]
    if "shell_only" in marks:
        engines = ["shell"]
    if "python_only" in marks:
        engines = ["python"]
    if "shfmt_only" in marks:
        engines = ["shfmt"]
    if "no_shfmt" in marks:
        engines = [e for e in engines if e != "shfmt"]
    if engines:
        metafunc.parametrize("engine", engines)


@pytest.fixture(autouse=True)
def engine():
    return None                                # plain tests in test_repo.py have no engine


@pytest.fixture(autouse=True)
def rungs(engine, monkeypatch):
    """Pin the parser ladder to the engine's one rung."""
    if engine not in IN_PROCESS:
        return
    if engine == "shfmt" and not scan.shfmt():
        if os.environ.get("CI"):
            pytest.fail(f"CI runs the shfmt engine: no shfmt >= {scan.SHFMT_MIN} on PATH")
        pytest.skip(f"no shfmt >= {scan.SHFMT_MIN} on PATH")
    monkeypatch.setattr(scan, "RUNGS", IN_PROCESS[engine])


def awk_path():
    return os.environ.get("AWK_PATH") or ""


def which_awk():
    return shutil.which("awk", path=awk_path() + os.pathsep + os.environ["PATH"] if awk_path() else None)


class Ctx:
    def __init__(self, engine):
        self.engine, self.guard = engine, None
        self.cwd = "{HOME}/project"
        self.env = {}                          # name -> value, or None for unset
        self.proj = self.tmp = self.stub_log = self.bare = self.cache = None
        self.project_env = True
        self.stubs = False
        self.hook = None                       # a hooks.json command, for wiring
        self.arg = None                        # an extra CLI argument to the guard script
        self.session = "s1"                    # session_id in the payload, for guard-github-issues
        self.mode = None                       # permission_mode in the payload, for guard-cross-session-send
        self._doordir = None
        self.calls = 0                         # tool_use_id in the payload: one per call, as Claude Code gives
        self.stdin = self.verdict = self.scanned = None
        self._dirs = []

    def mkdtemp(self):
        d = tempfile.mkdtemp(prefix="languette-", dir="/tmp")
        self._dirs.append(d)
        return d

    def doordir(self):
        # Lazy and once per scenario: the guard-github-issues state lives at
        # $TMPDIR/languette-guard-github-issues.<session>, and a scenario that opens
        # the door in one step and spends it in another needs that file to
        # survive across subprocess calls.
        if self._doordir is None:
            self._doordir = self.mkdtemp()
        return self._doordir

    def expand(self, s):
        if "{PROJ}" in s:
            assert self.proj, f"test setup: {s!r} names {{PROJ}} but the scenario has no project directory"
            s = s.replace("{PROJ}", str(self.proj))
        s = s.replace("{HOME}", os.environ["HOME"])
        if "{TMP}" in s:
            self.tmp = self.tmp or self.mkdtemp()
            s = s.replace("{TMP}", self.tmp)
        return s

    def cleanup(self):
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)

    # --- running a guard -------------------------------------------------

    def payload(self, command):
        self.calls += 1
        p = {"tool_name": "Bash", "tool_input": {"command": self.expand(command)}, "cwd": self.expand(self.cwd),
             "session_id": self.session, "tool_use_id": f"toolu_call{self.calls}"}
        if self.proj:
            p["transcript_path"] = f"{self.proj}/t.jsonl"
        return json.dumps(self.moded(p))

    def moded(self, p):
        if self.mode is not None:
            p["permission_mode"] = self.mode
        return p

    def scenario_env(self):
        env = {k: self.expand(v) for k, v in self.env.items() if v is not None}
        if self.proj and self.project_env and "CLAUDE_PROJECT_DIR" not in self.env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        if "TMPDIR" not in self.env:
            env["TMPDIR"] = self.doordir()     # the per-session state files, one place per scenario
        if "XDG_CACHE_HOME" not in self.env:
            self.cache = self.cache or self.mkdtemp()
            env["XDG_CACHE_HOME"] = self.cache
        return env

    def run(self, stdin):
        self.stdin = stdin
        if self.engine in IN_PROCESS:
            # These steps only shape a subprocess; in-process they would do nothing.
            assert not (self.hook or self.bare or self.stubs), \
                "test setup: a hook command, a bare PATH or the stubs need the shell engine (@shell_only)"
            env = {"HOME": os.environ["HOME"], **self.scenario_env()}
            self.verdict = Verdict(run.respond(stdin, env, only=self.guard))
            return
        env = {k: v for k, v in os.environ.items() if k not in SCRUB and not k.startswith("CLAUDE_PLUGIN_OPTION_")}
        path = env["PATH"]
        if awk_path():
            path = awk_path() + os.pathsep + path
        if self.stubs:
            path = str(ROOT / "tests/stubs") + os.pathsep + path
        if self.stub_log:
            env["LANGUETTE_STUB_LOG"] = self.stub_log
        env["PATH"] = self.bare or path
        env["TMPDIR"] = self.doordir()
        if self.hook:
            env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
            argv = ["sh", "-c", self.hook]
        else:
            argv = ["sh", str(ROOT / f"hooks/{self.guard}.sh")]
            if self.arg:
                argv.append(self.arg)
        env.update(self.scenario_env())
        try:
            r = subprocess.run(argv, input=stdin, env=env, capture_output=True, text=True, timeout=5)
            self.verdict = Verdict(r.stdout, r.returncode, r.stderr)
        except subprocess.TimeoutExpired:
            self.verdict = Verdict("", 124, "TIMEOUT after 5 s")

    def stub_calls(self, name):
        try:
            return Path(self.stub_log, name).read_text().splitlines()
        except FileNotFoundError:
            return []


@pytest.fixture
def ctx(engine):
    c = Ctx(engine)
    yield c
    c.cleanup()


def pytest_bdd_before_scenario(request, feature, scenario):
    request.getfixturevalue("ctx").guard = None if feature.name == "guard-unparsable" else feature.name


# --- Given ---------------------------------------------------------------

@given(parsers.parse('the working directory is "{path}"'))
@when(parsers.parse('the working directory is "{path}"'))
def _cwd(ctx, path):
    ctx.cwd = path


@given(parsers.parse('the session is "{session}"'))
@when(parsers.parse('the session is "{session}"'))
def _session(ctx, session):
    ctx.session = session


@given("a project directory")
def _project(ctx):
    ctx.proj = Path(ctx.mkdtemp())
    (ctx.proj / "sub").mkdir()
    subprocess.run(["git", "init", "-q", str(ctx.proj)], check=True)
    (ctx.proj / "t.jsonl").touch()             # a session has a transcript, if an empty one


@given(parsers.parse('the file "{rel}" holds:'))
def _file(ctx, rel, docstring):
    f = ctx.proj / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(docstring)


@given(parsers.parse('the file "{rel}" is committed'))
def _file_committed(ctx, rel):
    subprocess.run(["git", "-C", str(ctx.proj), "add", "--", rel], check=True)
    subprocess.run(["git", "-C", str(ctx.proj), "-c", "user.email=a@a", "-c", "user.name=a",
                     "commit", "-q", "-m", "x", "--", rel], check=True)


@given("the private terms file holds:")
def _terms(ctx, docstring):
    f = Path(ctx.mkdtemp()) / "private-terms.txt"
    f.write_text(ctx.expand(docstring) + "\n")
    ctx.env["CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE"] = str(f)


@given("the transcript holds:")
def _transcript(ctx, docstring):
    (ctx.proj / "t.jsonl").write_text(docstring + "\n")


@given("the transcript is missing")
def _no_transcript(ctx):
    (ctx.proj / "t.jsonl").unlink()


@given("the approvals already spent are:")
def _spent(ctx, docstring):
    (ctx.proj / "t.jsonl.languette-ask").write_text(docstring + "\n")


@given(parsers.re(r'(?P<var>[A-Z][A-Z0-9_]*) is "(?P<value>.*)"'))
def _setenv(ctx, var, value):
    ctx.env[var] = value


@given(parsers.re(r"(?P<var>[A-Z][A-Z0-9_]*) is unset"))
def _unsetenv(ctx, var):
    ctx.env[var] = None
    if var == "CLAUDE_PROJECT_DIR":
        ctx.project_env = False


@given(parsers.parse('the directory "{path}"'))
def _mkdir(ctx, path):
    Path(ctx.expand(path)).mkdir(parents=True, exist_ok=True)


@given(parsers.parse('a git repository at "{path}"'))
def _git_init(ctx, path):
    d = Path(ctx.expand(path))
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True)


@given(parsers.parse('a yadm-style repository at "{path}" whose work tree is "{wt}"'))
def _yadm_repo(ctx, path, wt):
    d = Path(ctx.expand(path))
    d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(d)], check=True)
    for k, v in (("core.bare", "false"), ("core.worktree", ctx.expand(wt))):
        subprocess.run(["git", "--git-dir", str(d), "config", k, v], check=True)


@given(parsers.parse('a linked worktree "{path}" of the repository at "{repo}"'))
def _linked_worktree(ctx, path, repo):
    r, d = ctx.expand(repo), ctx.expand(path)
    ident = ["-c", "user.email=t@e", "-c", "user.name=t"]
    if subprocess.run(["git", "-C", r, "rev-parse", "-q", "--verify", "HEAD"], capture_output=True).returncode:
        subprocess.run(["git", "-C", r, *ident, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    Path(d).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", r, "worktree", "add", "-q", "-b", Path(d).name, d], check=True)


@given(parsers.parse('the symlink "{path}" to "{target}"'))
def _symlink(ctx, path, target):
    Path(ctx.expand(path)).symlink_to(ctx.expand(target))


@given("the claude plugin's door file is already present")
def _claude_door_present(ctx):
    Path(ctx.doordir(), f"claude-issue-door.{ctx.session}").write_text("")


@then("the claude plugin's door file is still present")
def _claude_door_still(ctx):
    assert Path(ctx.doordir(), f"claude-issue-door.{ctx.session}").exists()


@given(parsers.parse('the door file is a symlink to "{target}"'))
def _door_symlink(ctx, target):
    victim = Path(ctx.expand(target))
    victim.write_text("keep")
    Path(ctx.doordir(), f"languette-guard-github-issues.{ctx.session}").symlink_to(victim)


@then(parsers.parse('the door file is a plain file and "{target}" still holds "{content}"'))
def _door_replaced(ctx, target, content):
    door = Path(ctx.doordir(), f"languette-guard-github-issues.{ctx.session}")
    assert not door.is_symlink(), "door file is still a symlink"
    assert Path(ctx.expand(target)).read_text() == content


@given('the stubs "gh" and "timeout" are first on PATH')
def _stubs(ctx):
    ctx.stubs, ctx.stub_log = True, ctx.mkdtemp()


@given('the stub "gh" is first on PATH, for a Python guard')
def _gh_stub_python(ctx):
    # The Python engine's guards get only the scenario's env, so PATH and the
    # stub log travel there rather than through the shell engine's subprocess.
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    ctx.env["PATH"] = str(ROOT / "tests/stubs") + os.pathsep + os.environ["PATH"]
    ctx.env["LANGUETTE_STUB_LOG"] = ctx.stub_log


@given(parsers.parse('a clone of "{url}" at "{path}" on branch "{branch}"'))
def _clone(ctx, url, path, branch):
    d = ctx.expand(path)
    git = ["git", "-C", d, "-c", "user.email=t@e", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", "-b", "main", d], check=True)
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    subprocess.run([*git, "remote", "add", "origin", url], check=True)
    if branch != "main":
        subprocess.run([*git, "checkout", "-q", "-b", branch], check=True)
    for b in {"main", branch}:
        subprocess.run([*git, "update-ref", f"refs/remotes/origin/{b}", "HEAD"], check=True)
        subprocess.run([*git, "config", f"branch.{b}.remote", "origin"], check=True)
        subprocess.run([*git, "config", f"branch.{b}.merge", f"refs/heads/{b}"], check=True)
    subprocess.run([*git, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"], check=True)


@given(parsers.parse('the remote HEAD of "{path}" points at "{branch}"'))
def _remote_head(ctx, path, branch):
    d = ctx.expand(path)
    subprocess.run(["git", "-C", d, "update-ref", f"refs/remotes/origin/{branch}", "HEAD"], check=True)
    subprocess.run(["git", "-C", d, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{branch}"],
                   check=True)


@given('the stub "prose-budget" is the engine')
def _prose_budget_stub(ctx):
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    ctx.env["PROSE_BUDGET"] = str(ROOT / "tests/stubs/prose-budget")


@given('the stub "prose-budget" is the engine, at a relative path')
def _prose_budget_stub_relative(ctx):
    assert ctx.proj, "test setup: a relative PROSE_BUDGET needs a project directory"
    ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
    dest = ctx.proj / "prose-budget"
    shutil.copy(ROOT / "tests/stubs/prose-budget", dest)
    dest.chmod(0o755)
    ctx.env["PROSE_BUDGET"] = "./prose-budget"


@given('the stub "prose-budget" is the engine, by bare name on PATH')
def _prose_budget_stub_bare(ctx):
    ctx.stubs, ctx.stub_log = True, ctx.stub_log or ctx.mkdtemp()
    ctx.env["PROSE_BUDGET"] = "prose-budget"


@given(parsers.re(r'PATH holds only "(?P<tools>[^"]*)"(?P<gh> and the stub "gh")?'))
def _bare_path(ctx, tools, gh):
    ctx.bare = ctx.mkdtemp()
    for t in tools.split():
        p = which_awk() if t == "awk" else shutil.which(t)
        assert p, f"test setup: no {t} on PATH"
        os.symlink(p, os.path.join(ctx.bare, t))
    if gh:
        ctx.stub_log = ctx.stub_log or ctx.mkdtemp()
        os.symlink(ROOT / "tests/stubs/gh", os.path.join(ctx.bare, "gh"))


@given(parsers.parse('the hook is the hooks.json command for "{guard}"'))
def _hooks_json(ctx, guard):
    ctx.hook = hooks_json_commands()[guard]


@given(parsers.parse('the hook is the hooks.json {event} command for "{guard}"'))
def _hooks_json_event(ctx, event, guard):
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [ctx.hook] = [h["command"] for e in hj["hooks"][event] for h in e["hooks"] if f"--guard {guard}" in h["command"]]


@when(parsers.parse('Claude Code fires {event} for tool "{tool}"'))
def _fires(ctx, event, tool):
    ctx.run(json.dumps(ctx.moded({"hook_event_name": event, "session_id": ctx.session, "tool_name": tool,
                                  "tool_input": {}, "tool_response": "..."})))


@then("the cross-session state file is gone")
def _send_state_gone(ctx):
    assert not _send_state_file(ctx).exists()


@then(parsers.parse('the cross-session state file names "{tool}"'))
def _send_state_names(ctx, tool):
    assert json.loads(_send_state_file(ctx).read_text())["read"] == tool


@given(parsers.parse('the plugin\'s script for "{guard}" crashes'))
def _crash(ctx, guard):
    root = Path(ctx.mkdtemp())
    if "languette/run.py" in hooks_json_commands()[guard]:
        (root / "languette").mkdir()
        (root / "languette/run.py").write_text("raise SystemExit(3)\n")
    else:
        (root / "hooks").mkdir()
        (root / f"hooks/{guard}.sh").write_text("exit 3\n")
    ctx.env["CLAUDE_PLUGIN_ROOT"] = str(root)


@given(parsers.parse('the plugin\'s part "{part}" crashes'))
def _crash_part(ctx, part):
    root = Path(ctx.mkdtemp())
    shutil.copytree(ROOT / "hooks", root / "hooks")
    (root / f"hooks/{part}.sh").write_text("exit 3\n")
    ctx.env["CLAUDE_PLUGIN_ROOT"] = str(root)


def hooks_json_commands():
    """guard name -> its command in hooks/hooks.json."""
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    out = {}
    for entry in hj["hooks"]["PreToolUse"]:
        for h in entry["hooks"]:
            m = re.search(r'/hooks/([a-z-]+)\.sh"|languette/run\.py" --guard ([a-z-]+)', h["command"])
            out[m.group(1) or m.group(2)] = h["command"]
    return out


def hooks_json_prompt_command():
    """The UserPromptSubmit command in hooks/hooks.json that opens the guard-github-issues door."""
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [h] = [h for e in hj["hooks"]["UserPromptSubmit"] for h in e["hooks"] if "guard-github-issues.sh" in h["command"]]
    return h["command"]


# --- When ----------------------------------------------------------------

# Greedy to the last backtick, so a command may hold backticks of its own.
def _ran(ctx):
    """Claude Code fires PostToolUse only for a call that ran: when this guard
    let it through, spend the door as the post hook would. The verdict the
    scenario judges stays the PreToolUse one."""
    if ctx.guard == "guard-cross-session-send" and not ctx.hook:
        _post(ctx, "PostToolUse")
    if ctx.guard != "guard-github-issues" or ctx.hook or ctx.verdict.decision == "deny":
        return
    pre, ctx.arg = ctx.verdict, "post"
    ctx.run(ctx.stdin)
    ctx.arg, ctx.verdict = None, pre


def _post(ctx, event):
    """The call ran: fire `event` on its payload, keeping the PreToolUse verdict."""
    pre, p = ctx.verdict, json.loads(ctx.stdin)
    ctx.run(json.dumps({**p, "hook_event_name": event, "tool_response": "..."}))
    assert ctx.verdict.stdout == "", f"{event} hook printed {ctx.verdict.stdout!r}"
    ctx.verdict = pre


@when(parsers.re(r"the agent runs `(?P<command>.*)`, which fails", flags=re.S))
def _runs_failing(ctx, command):
    ctx.run(ctx.payload(command))
    _post(ctx, "PostToolUseFailure")


@when(parsers.re(r"the agent runs `(?P<command>.*)`", flags=re.S))
def _runs(ctx, command):
    ctx.run(ctx.payload(command))
    _ran(ctx)


def _transcript(ctx):
    if not ctx.proj:
        ctx.proj = Path(ctx.mkdtemp())
    (ctx.proj / "t.jsonl").touch()


@when(parsers.re(r"another guard denies `(?P<command>.*)`", flags=re.S))
def _denied_elsewhere(ctx, command):
    # This guard's PreToolUse ran, the call did not: Claude Code records the
    # deny as its result, and fires no PostToolUse.
    _transcript(ctx)
    ctx.run(ctx.payload(command))
    _record_result(ctx, "guard-private-terms: denied")


@when("that call ran, but its post hook never did")
def _ran_unspent(ctx):
    _record_result(ctx, "https://github.com/o/r/issues/9", is_error=False)


@then(parsers.parse('"{target}" still holds "{content}"'))
def _still_holds(ctx, target, content):
    assert Path(ctx.expand(target)).read_text() == content


@when(parsers.re(r"the agent starts `(?P<command>.*)`", flags=re.S))
def _starts(ctx, command):
    # PreToolUse ran and the call is still running: no result, no PostToolUse.
    _transcript(ctx)
    ctx.run(ctx.payload(command))


@when("the agent runs:")
def _runs_doc(ctx, docstring):
    ctx.run(ctx.payload(docstring))


@when("the agent runs it again")
def _rerun(ctx):
    p = json.loads(ctx.stdin)
    if "tool_use_id" in p:
        ctx.calls += 1
        p["tool_use_id"] = f"toolu_call{ctx.calls}"
    ctx.run(json.dumps(p))


def _record_result(ctx, content, is_error=True, **extra):
    call = json.loads(ctx.stdin)["tool_use_id"]
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call, "content": content, "is_error": is_error}]}, **extra}
    with (ctx.proj / "t.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")


@when(parsers.parse('Claude Code records that call\'s result as "{content}"'))
def _call_result(ctx, content):
    _record_result(ctx, content)


@when("the user declines that call")
def _call_declined(ctx):
    _record_result(ctx, "The user doesn't want to proceed with this tool use. The tool use was rejected.",
                   toolUseResult="User rejected tool use")


@when("the human speaks, opening the door")
def _open_door(ctx):
    ctx.arg = "prompt"
    ctx.run(json.dumps({"session_id": ctx.session, "prompt": "yes, file it"}))
    ctx.arg = None


@when("the human speaks, through the hooks.json prompt hook")
def _open_door_via_hooks_json(ctx):
    # The UserPromptSubmit command exactly as hooks.json writes it, run the way
    # Claude Code runs it; the PreToolUse hook is restored for the next step.
    pretool, ctx.hook = ctx.hook, hooks_json_prompt_command()
    ctx.run(json.dumps({"session_id": ctx.session, "prompt": "yes, file it"}))
    ctx.hook = pretool


@when(parsers.re(r'the agent calls MCP tool "(?P<tool>[^"]+)" with input `(?P<inp>.*)`', flags=re.S))
def _mcp_call(ctx, tool, inp):
    ctx.run(json.dumps(ctx.moded({"session_id": ctx.session, "tool_name": tool, "tool_input": json.loads(inp)})))
    _ran(ctx)


@when(parsers.re(r'the agent calls tool "(?P<tool>[^"]+)" with input `(?P<inp>.*)`', flags=re.S))
def _tool_call(ctx, tool, inp):
    ctx.run(json.dumps(ctx.moded({"session_id": ctx.session, "tool_name": tool,
                                  "tool_input": json.loads(ctx.expand(inp)), "cwd": ctx.expand(ctx.cwd)})))
    _ran(ctx)


@given(parsers.parse('the permission mode is "{mode}"'))
@when(parsers.parse('the permission mode is "{mode}"'))
def _mode(ctx, mode):
    ctx.mode = mode


@given("the payload carries no permission mode")
def _no_mode(ctx):
    ctx.mode = None


@when("the human speaks")
def _speaks(ctx):
    ctx.run(json.dumps(ctx.moded({"hook_event_name": "UserPromptSubmit", "session_id": ctx.session,
                                  "prompt": "go on"})))
    assert ctx.verdict.stdout == "", f"UserPromptSubmit printed {ctx.verdict.stdout!r}"


@when(parsers.parse('subagent "{agent}" starts'))
def _subagent_starts(ctx, agent):
    ctx.run(json.dumps(ctx.moded({"hook_event_name": "SubagentStart", "session_id": ctx.session,
                                  "agent_id": agent, "agent_type": "general-purpose"})))
    assert ctx.verdict.stdout == "", f"SubagentStart printed {ctx.verdict.stdout!r}"


def _send(ctx, to, message, **extra):
    ctx.calls += 1
    ctx.run(json.dumps(ctx.moded({"hook_event_name": "PreToolUse", "session_id": ctx.session, "tool_name": "SendMessage",
                                  "tool_input": {"to": to, "message": message},
                                  "tool_use_id": f"toolu_call{ctx.calls}", **extra})))


@when(parsers.re(r'the agent sends "(?P<to>[^"]*)" the message `(?P<message>.*)`', flags=re.S))
def _sends(ctx, to, message):
    _send(ctx, to, message.replace("\\n", "\n"))


@when(parsers.re(r'subagent "(?P<agent>[^"]+)" sends "(?P<to>[^"]*)" the message `(?P<message>.*)`', flags=re.S))
def _subagent_sends(ctx, agent, to, message):
    _send(ctx, to, message, agent_id=agent)


def _send_state_file(ctx):
    return Path(ctx.doordir(), f"languette-guard-cross-session-send.{ctx.session}")


@given(parsers.parse("the cross-session state file holds `{text}`"))
@when(parsers.parse("the cross-session state file holds `{text}`"))
def _send_state(ctx, text):
    _send_state_file(ctx).write_text(text)


@when("the cross-session state file is open to others")
def _send_state_open(ctx):
    _send_state_file(ctx).chmod(0o666)


@given(parsers.parse('the cross-session state file is a symlink to "{target}"'))
def _send_state_link(ctx, target):
    victim = Path(ctx.expand(target))
    victim.write_text("keep")
    _send_state_file(ctx).symlink_to(victim)


@when("the payload is:")
def _raw(ctx, docstring):
    ctx.run(docstring)


@when(parsers.re(r"the scanner reads `(?P<command>.*)`", flags=re.S))
def _scan(ctx, command):
    ctx.scanned = command


@when("the scanner reads:")
def _scan_doc(ctx, docstring):
    ctx.scanned = docstring


@when(parsers.re(r"the scanner reads the JSON string (?P<js>\".*\")"))
def _scan_json(ctx, js):
    ctx.scanned = json.loads(js)


def scanned(ctx, mode):
    if ctx.engine in IN_PROCESS:
        if mode == "tokens":
            s = scan.Scan(ctx.scanned)
            assert s.rung == IN_PROCESS[ctx.engine][0], f"the {s.rung} rung read it"
            return s.tokens()
        return [("1:" if nested else "0:") + t for t, nested in scan.texts_of(scan.strip_heredocs(ctx.scanned + "\n"))]
    lib, prog = ROOT / "hooks/lib-shell-words.awk", ROOT / "tests/scan_json.awk"
    r = subprocess.run([which_awk(), "-v", f"mode={mode}", "-f", str(lib), "-f", str(prog)],
                       input=ctx.scanned, capture_output=True, text=True, timeout=5)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- Then ----------------------------------------------------------------

@then("the guard denies")
def _denies(ctx):
    assert_that(ctx.verdict, denies())


@then(parsers.re(r'the guard denies, naming "(?P<text>.*)"'))
def _denies_naming(ctx, text):
    assert_that(ctx.verdict, denies(naming=ctx.expand(text)))


@then(parsers.re(r'the guard asks, naming "(?P<text>.*)"'))
def _asks_naming(ctx, text):
    assert_that(ctx.verdict, asks(naming=ctx.expand(text)))


@then("the guard asks")
def _asks(ctx):
    assert_that(ctx.verdict, asks())


@then("the guard is silent")
def _silent(ctx):
    assert_that(ctx.verdict, is_silent())


@then(parsers.re(r'the guard warns about "(?P<text>.*)"'))
def _warns(ctx, text):
    assert_that(ctx.verdict, warns_about(text))


@then(parsers.re(r'the guard allows, rewriting the command to "(?P<text>.*)"'))
def _rewrites(ctx, text):
    assert ctx.verdict.decision == "allow", ctx.verdict.show()
    got = ctx.verdict.out.get("updatedInput", {}).get("command")
    assert got == ctx.expand(text), f"rewritten to {got!r}, want {ctx.expand(text)!r}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was called with "(?P<text>.*)"'))
def _called_with(ctx, name, text):
    calls = ctx.stub_calls(name)
    assert any(text in c for c in calls), f"{name} was never called with {text!r}; calls: {calls}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was not called with "(?P<text>.*)"'))
def _not_called_with(ctx, name, text):
    calls = ctx.stub_calls(name)
    assert not any(text in c for c in calls), f"{name} was called with {text!r}; calls: {calls}"


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was not called'))
def _not_called(ctx, name):
    assert_that(ctx.stub_calls(name), equal_to([]))


@then(parsers.re(r'the stub "(?P<name>[a-z-]+)" was called (?P<n>\d+) times'))
def _called_n(ctx, name, n):
    assert_that(len(ctx.stub_calls(name)), equal_to(int(n)))


@then(parsers.re(r"its (?P<mode>tokens|texts) are (?P<want>\[.*\])"))
def _scanned(ctx, mode, want):
    assert_that(scanned(ctx, mode), equal_to(json.loads(want)))
