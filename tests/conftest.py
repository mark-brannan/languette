"""Engines and the step vocabulary for features/*.feature.

Every scenario runs once per engine its feature is tagged with: @python runs
languette/ in-process, @shell runs hooks/<guard>.sh by subprocess (under
$AWK_PATH's awk when set). @shell_only narrows a scenario to the shell.
The feature's name is the guard's name.
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

ENGINES = ("python", "shell")
# Never inherited from the caller's shell: each would change a verdict.
SCRUB = ("LANGUETTE_RM_ALLOW", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "GH_FAIL", "GH_TAB",
         "TIMEOUT_HANG", "LANGUETTE_STUB_LOG", "PROSE_BUDGET", "PROSE_BUDGET_FAIL", "PROSE_BUDGET_CRASH",
         "CLAUDE_CODE_TMPDIR", "CLAIM_STAMP_BIN")


_REAL_HOME = os.environ.get("HOME")


def pytest_configure(config):
    # A throwaway $HOME for the whole run, so no verdict depends on, and no
    # step can touch, the real one. {HOME}/project is the default cwd. Not
    # under /tmp: no-rm-tree allows all of /tmp, so every target would pass.
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
    engines = [e for e in ENGINES if e in marks]
    if "shell_only" in marks:
        engines = ["shell"]
    if engines:
        metafunc.parametrize("engine", engines)


@pytest.fixture(autouse=True)
def engine():
    return None                                # plain tests in test_repo.py have no engine


def awk_path():
    return os.environ.get("AWK_PATH") or ""


def which_awk():
    return shutil.which("awk", path=awk_path() + os.pathsep + os.environ["PATH"] if awk_path() else None)


class Ctx:
    def __init__(self, engine):
        self.engine, self.guard = engine, None
        self.cwd = "{HOME}/project"
        self.env = {}                          # name -> value, or None for unset
        self.proj = self.tmp = self.stub_log = self.bare = None
        self.project_env = True
        self.stubs = False
        self.hook = None                       # a hooks.json command, for wiring
        self.arg = None                        # an extra CLI argument to the guard script
        self.session = "s1"                    # session_id in the payload, for issue-door
        self._doordir = None
        self.stdin = self.verdict = self.scanned = None
        self._dirs = []

    def mkdtemp(self):
        d = tempfile.mkdtemp(prefix="languette-", dir="/tmp")
        self._dirs.append(d)
        return d

    def doordir(self):
        # Lazy and once per scenario: issue-door's state lives at
        # $TMPDIR/languette-issue-door.<session>, and a scenario that opens
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
        p = {"tool_name": "Bash", "tool_input": {"command": self.expand(command)}, "cwd": self.expand(self.cwd),
             "session_id": self.session}
        if self.proj:
            p["transcript_path"] = f"{self.proj}/t.jsonl"
        return json.dumps(p)

    def scenario_env(self):
        env = {k: self.expand(v) for k, v in self.env.items() if v is not None}
        if self.proj and self.project_env and "CLAUDE_PROJECT_DIR" not in self.env:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        return env

    def run(self, stdin):
        self.stdin = stdin
        if self.engine == "python":
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
    request.getfixturevalue("ctx").guard = feature.name


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
    Path(ctx.doordir(), f"languette-issue-door.{ctx.session}").symlink_to(victim)


@then(parsers.parse('the door file is a plain file and "{target}" still holds "{content}"'))
def _door_replaced(ctx, target, content):
    door = Path(ctx.doordir(), f"languette-issue-door.{ctx.session}")
    assert not door.is_symlink(), "door file is still a symlink"
    assert Path(ctx.expand(target)).read_text() == content


@given('the stubs "gh" and "timeout" are first on PATH')
def _stubs(ctx):
    ctx.stubs, ctx.stub_log = True, ctx.mkdtemp()


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


@given(parsers.parse('the plugin\'s shell fallback for "{guard}" {state}'))
def _fallback(ctx, guard, state):
    root = Path(ctx.mkdtemp())
    (root / "hooks").mkdir()
    if state == "crashes":
        (root / f"hooks/{guard}.sh").write_text("exit 3\n")
    else:
        assert state == "is missing", f"test setup: unknown fallback state {state!r}"
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
    """The one UserPromptSubmit command in hooks/hooks.json (issue-door's)."""
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [h] = [h for e in hj["hooks"]["UserPromptSubmit"] for h in e["hooks"]]
    return h["command"]


# --- When ----------------------------------------------------------------

# Greedy to the last backtick, so a command may hold backticks of its own.
@when(parsers.re(r"the agent runs `(?P<command>.*)`", flags=re.S))
def _runs(ctx, command):
    ctx.run(ctx.payload(command))


@when("the agent runs:")
def _runs_doc(ctx, docstring):
    ctx.run(ctx.payload(docstring))


@when("the agent runs it again")
def _rerun(ctx):
    ctx.run(ctx.stdin)


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
    ctx.run(json.dumps({"session_id": ctx.session, "tool_name": tool, "tool_input": json.loads(inp)}))


@when(parsers.re(r'the agent calls tool "(?P<tool>[^"]+)" with input `(?P<inp>.*)`', flags=re.S))
def _tool_call(ctx, tool, inp):
    ctx.run(json.dumps({"session_id": ctx.session, "tool_name": tool, "tool_input": json.loads(ctx.expand(inp)),
                        "cwd": ctx.expand(ctx.cwd)}))


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
    if ctx.engine == "python":
        if mode == "tokens":
            return scan.Scan(ctx.scanned).tokens()
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
