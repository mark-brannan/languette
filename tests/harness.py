"""The harness the step vocabulary and fixtures share: engines, the scrubbed
environment, a scenario's Ctx, and the hooks.json lookups."""

import json
import os
import random
import shutil
import socket
import string
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from languette import run, verdict  # noqa: E402
from hamcrest import assert_that, equal_to, has_length
from matchers import Verdict

ENGINES = ("python", "shfmt", "hook")
IN_PROCESS = {"python": ("awk",), "shfmt": ("shfmt",)}   # engine -> scan.RUNGS
# Never inherited from the caller's shell: each would change a verdict.
SCRUB = ("LANGUETTE_RM_ALLOW", "LANGUETTE_PERM_ALLOW", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "GH_FAIL", "GH_TAB",
         "TIMEOUT_HANG", "LANGUETTE_STUB_LOG", "PROSE_BUDGET_FAIL", "PROSE_BUDGET_CRASH", "CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMAND",
         "CLAUDE_CODE_TMPDIR", "CLAUDE_CONFIG_DIR", "GH_RULES", "GH_PROTECTION", "GH_TIMELINE", "GH_LOGIN", "GH_THREADS", "XDG_CACHE_HOME", "XDG_CONFIG_HOME")


_REAL_HOME = os.environ.get("HOME")
# Ctx.arg -> the hook event it stands for.
EVENTS = {"prompt": "UserPromptSubmit", "post": "PostToolUse"}


ELSEWHERE = None                              # the run's root for directories outside $HOME
GUARD_NAMES = sorted({g.NAME for _, _, gs in run.GUARDS for g in gs})
# Every opt-in guard's option, switched on for every in-process scenario.
OPT_INS = sorted({g.OPT_IN for _, _, gs in run.GUARDS for g in gs if getattr(g, "OPT_IN", None)})




def scattered(seed, role):
    """A fresh directory under the run's root, outside $HOME: a random name
    at a random depth, seeded from `seed` (the test's id), so a failure
    reproduces. `role` keeps the scenario's directories apart: none is
    another's ancestor, and none is $HOME's."""
    rng = random.Random(f"{seed}\0{role}")
    parts = ["".join(rng.choices(string.ascii_lowercase + string.digits, k=rng.randint(3, 10)))
             for _ in range(rng.randint(1, 5))]
    d = Path(ELSEWHERE, role, *parts)
    d.mkdir(parents=True, exist_ok=True)
    return str(d)



FIXTURES = ROOT / "features/fixtures/private-terms"


def fill_names(text, home):
    """{HOME}, {USER} (the home directory's last part) and {HOSTNAME} (this machine's), as the fixtures spell them."""
    return text.replace("{HOME}", home).replace("{USER}", Path(home).name).replace("{HOSTNAME}", socket.gethostname())


def fixture_text(name, home):
    return fill_names((FIXTURES / name.removeprefix(FIXTURES.name + "/")).read_text(), home)


class Ctx:
    def __init__(self, engine, seed):
        self.engine = engine
        self.guard = None                      # the guard the feature names; None for a family
        self.also = set()                      # guards the row names as rightly firing too
        self.fired = set()                     # guards other than self.guard that gave a finding
        # The payload's cwd and the hook process's own directory: unrelated
        # to each other and to $HOME, so a guard that assumes otherwise fails.
        self.cwd = self.default_cwd = scattered(seed, "cwd")
        self.process_dir = scattered(seed, "process")
        # name -> value, or None for unset. The guard's own default guards no label, so
        # scenarios that expect guard-bypass-labels to fire start from a configured list.
        self.env = {"CLAUDE_PLUGIN_OPTION_BYPASS_LABELS": "churn-ok,mixed-loops-ok"}
        self.proj = self.tmp = self.stub_log = self.bare = self.cache = None
        self.project_env = True
        self.stubs = False
        self.hook = None                       # a hooks.json command, for wiring
        self.wired = None                      # the guard a wiring row is about: the one command runs them all
        self.arg = None                        # the hook event, as Claude Code names it, for the guard to read
        self.session = "s1"                    # session_id in the payload, for guard-github-issues; None leaves it out
        self.agent = None                      # agent_id in the payload: a subagent's call, for guard-worktrees
        self.mode = None                       # permission_mode in the payload, for guard-cross-session-send
        self._doordir = None
        self.calls = 0                         # tool_use_id in the payload: one per call, as Claude Code gives
        self.stdin = self.verdict = self.scanned = None
        self._dirs = []
        self.cleanups = []

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
        s = s.replace("{TAB}", "\t")
        if "{PROJ}" in s:
            assert self.proj, f"test setup: {s!r} names {{PROJ}} but the scenario has no project directory"
            s = s.replace("{PROJ}", str(self.proj))
        s = fill_names(s, os.environ["HOME"]).replace("{CWD}", self.default_cwd)
        s = s.replace("{UP}", "../" * self.default_cwd.count("/"))
        if "{TMP}" in s:
            self.tmp = self.tmp or self.mkdtemp()
            s = s.replace("{TMP}", self.tmp)
        return s

    def cleanup(self):
        for f in self.cleanups:
            f()
        for d in self._dirs:
            shutil.rmtree(d, ignore_errors=True)

    # --- running a guard -------------------------------------------------

    def payload(self, command):
        self.calls += 1
        p = {"tool_name": "Bash", "tool_input": {"command": self.expand(command)}, "cwd": self.expand(self.cwd),
             "session_id": self.session, "tool_use_id": f"toolu_call{self.calls}"}
        if self.proj:
            p["transcript_path"] = f"{self.proj}/t.jsonl"
        return json.dumps(self.as_sent(p))

    def as_sent(self, p):
        """`p` with what Claude Code puts in every payload: the cwd, and the mode when set."""
        p.setdefault("cwd", self.expand(self.cwd))
        if self.session is None:
            p.pop("session_id", None)
        if self.agent:
            p["agent_id"] = self.agent
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
            # A hook command only shapes a subprocess; in-process it would do nothing.
            assert not self.hook, "test setup: a hook command needs the hook engine (@hook)"
            # TMPDIR fresh per scenario, so a guard's per-session file starts
            # empty; PATH and the stub log as the stubs need.
            on = {k: "true" for k in OPT_INS if k not in self.env}
            env = {"HOME": os.environ["HOME"], "USER": Path(os.environ["HOME"]).name, "TMPDIR": self.doordir(), **on,
                   **self.scenario_env()}
            if self.bare or self.stubs:
                env["PATH"] = self.bare or str(ROOT / "tests/stubs") + os.pathsep + os.environ["PATH"]
            if self.stub_log:
                env["LANGUETTE_STUB_LOG"] = self.stub_log
            if self.arg:
                # The event is in the payload, as Claude Code sends it.
                stdin = json.dumps({**json.loads(stdin), "hook_event_name": EVENTS[self.arg]})
            here = os.getcwd()
            os.chdir(self.process_dir)
            seen = []
            try:
                self.verdict = Verdict(_respond_all(stdin, env, seen))
            finally:
                os.chdir(here)
            if self.guard and seen:
                others = {g: r for g, r, _ in seen if r and g != self.guard}
                self.fired |= others.keys()
                stray = {g: r for g, r in others.items() if g not in self.also}
                assert not stray, (f"every guard but {self.guard} should be silent; tag the row @also_<guard> "
                                   f"if it rightly trips another: {stray}")
                # The row's verdict is the named guard's own. With no finding at all, the hook
                # answered before any guard judged (no cwd, say), and that answer stands.
                event = json.loads(stdin).get("hook_event_name") or "PreToolUse"
                fields = verdict.verdict(event, [f for f in seen if f[0] == self.guard],
                                         json.loads(stdin).get("permission_mode"))
                self.verdict = Verdict(run._out(event, fields) if fields else "")
            return
        env = {k: v for k, v in os.environ.items() if k not in SCRUB and not k.startswith("CLAUDE_PLUGIN_OPTION_")}
        path = env["PATH"]
        if self.stubs:
            path = str(ROOT / "tests/stubs") + os.pathsep + path
        if self.stub_log:
            env["LANGUETTE_STUB_LOG"] = self.stub_log
        env["PATH"] = self.bare or path
        env["TMPDIR"] = self.doordir()
        assert self.hook, "test setup: the hook engine runs a hooks.json command"
        env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        argv = ["sh", "-c", self.hook]
        env.update(self.scenario_env())
        try:
            r = subprocess.run(argv, input=stdin, env=env, cwd=self.process_dir, capture_output=True, text=True,
                               timeout=5)
            self.verdict = Verdict(r.stdout, r.returncode, r.stderr)
        except subprocess.TimeoutExpired:
            self.verdict = Verdict("", 124, "TIMEOUT after 5 s")

    def stub_calls(self, name):
        try:
            return Path(self.stub_log, name).read_text().splitlines()
        except FileNotFoundError:
            return []


def _respond_all(stdin, env, seen):
    """run.respond with every guard on; each guard's own finding goes on `seen`."""
    real = run._respond

    def spy(*a):
        out, judged = real(*a)
        seen.extend(judged[2])
        return out, judged
    run._respond = spy
    try:
        return run.respond(stdin, env)
    finally:
        run._respond = real



def hooks_json_commands():
    """guard name -> the PreToolUse command in hooks/hooks.json that judges it: the one
    command, which names no guard and runs every guard wired for the call."""
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [command] = [h["command"] for e in hj["hooks"]["PreToolUse"] for h in e["hooks"]]
    return {g.NAME: command for ev, _, gs in run.GUARDS for g in gs if ev == "PreToolUse"}


def hooks_json_event_command(event):
    """The one command hooks/hooks.json runs for `event`."""
    hj = json.loads((ROOT / "hooks/hooks.json").read_text())
    [command] = [h["command"] for e in hj["hooks"][event] for h in e["hooks"]]
    return command


def hooks_json_prompt_command():
    """The UserPromptSubmit command in hooks/hooks.json that opens the guard-github-issues door."""
    return hooks_json_event_command("UserPromptSubmit")


class FakeHome:
    """What the doctor and install steps share: a fake HOME and a directory
    beside it for stubs, run `python3 -m languette <command>` by subprocess,
    and the rows it prints. A subclass adds its own stubs and steps."""

    def __init__(self, kind, subdirs=()):
        # Not under /tmp: guard-recursive-delete allows all of /tmp.
        self.home = Path(tempfile.mkdtemp(prefix=f"languette-{kind}-home-", dir="/var/tmp"))
        for d in subdirs:
            (self.home / d).mkdir(parents=True)
        self.aside = Path(tempfile.mkdtemp(prefix=f"languette-{kind}-"))   # stubs and copies, outside HOME
        self.bin = self.aside / "bin"
        self.bin.mkdir()
        self.env = {}                          # set in the run's environment, over HOME and the rest
        self.out = self.err = self.code = self.before = None

    def snapshot(self):
        return sorted((str(p.relative_to(self.home)), p.stat().st_size) for p in self.home.rglob("*"))

    def invoke(self, args, cwd, path, stdin=None):
        """Run `python3 -m languette *args` in `cwd` with `path` after the stubs' directory on PATH,
        `stdin` as its input, nothing when None."""
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "LANGUETTE_")) and k not in SCRUB}
        env.update(HOME=str(self.home), USER=self.home.name, PATH=f"{self.bin}{os.pathsep}{path}", TMPDIR=str(self.aside),
                   PYTHONPATH=str(ROOT), **self.env)
        self.before = self.snapshot()
        r = subprocess.run([sys.executable, "-m", "languette", *args], cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=60, input=stdin or "")
        self.out, self.err, self.code = r.stdout, r.stderr, r.returncode

    def row(self, label):
        rows = [ln for ln in self.out.splitlines() if ln[2:].startswith(label + " ")]
        assert_that(rows, has_length(1), f"one {label!r} row in:\n{self.out}{self.err}")
        return rows[0][0], rows[0][2:][len(label):].strip()

    def assert_row(self, label, mark, text):
        assert_that(self.row(label), equal_to((mark, text)))

    def assert_exit(self, code):
        assert_that(self.code, equal_to(code), self.out + self.err)

    def assert_untouched(self):
        assert_that(self.snapshot(), equal_to(self.before))

    def cleanup(self):
        for d in (self.home, self.aside):
            shutil.rmtree(d, ignore_errors=True)
