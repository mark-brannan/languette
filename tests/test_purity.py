"""The purity check (docs/design/guard-pipeline.md): every guard and the
verdict, read as source and never run, may not open a file, start a program,
open a connection, read the clock or ask the disk about a path. What a guard
needs from the world it yields as a Need; languette.world answers it. A Need
reads only (docs/decisions.md, "Gather reads only"): a kind the world answers
with a write is an escape too, the shape #107 had.

A list of known ways out, not a proof: it catches the slip a well-meaning
author makes, not a deliberate escape (`eval`, a name built at run time)."""

import ast
from collections import Counter
from pathlib import Path

import pytest
from hamcrest import assert_that, empty, equal_to, is_not

ROOT = Path(__file__).resolve().parent.parent


def _pure():
    """The guards, the verdict, and every languette module they import, so a
    helper cannot carry the escape for them."""
    todo, seen = sorted((ROOT / "languette" / "guards").glob("*.py")) + [ROOT / "languette" / "verdict.py"], set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        pkg = ".".join(f.relative_to(ROOT).parent.parts)
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.ImportFrom):
                # `from . import x` / `from ..paths import y`, made absolute against f's package.
                base = ".".join(pkg.split(".")[:len(pkg.split(".")) - n.level + 1] + ([n.module] if n.module else [])) \
                    if n.level else n.module
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                ([base] if n.module else []) + [f"{base}.{a.name}" for a in n.names] \
                if isinstance(n, ast.ImportFrom) and base else []
            todo += [ROOT / (m.replace(".", "/") + ".py") for m in mods
                     if m.startswith("languette.") and (ROOT / (m.replace(".", "/") + ".py")).is_file()]
    return sorted(seen)


PURE = _pure()

# Whole modules whose every call reaches past the process.
MODULES = {"subprocess", "socket", "ssl", "time", "shutil", "glob", "tempfile", "fcntl", "select", "selectors",
           "asyncio", "multiprocessing", "pty", "urllib.request", "http.client", "ftplib", "smtplib", "sqlite3",
           "webbrowser", "random", "uuid", "secrets", "pwd", "grp", "getpass", "linecache", "fileinput", "zipfile",
           "tarfile", "platform", "signal", "threading", "ctypes", "importlib", "mmap"}
# Calls by dotted name. os.path is pure but for the ones that stat the disk or
# fold in the cwd or $HOME; os.environ passes, the env is an input.
CALLS = {"open", "io.open", "io.FileIO", "builtins.open", "codecs.open", "input", "breakpoint", "sys.stdin",
         "logging.FileHandler",
         "datetime.datetime.now",
         "datetime.datetime.utcnow", "datetime.datetime.today", "datetime.date.today",
         "pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"} | {
    f"os.{n}" for n in (
        "open fdopen read readv pread preadv write close pipe dup dup2 system popen fork forkpty openpty kill "
        "killpg getcwd getcwdb chdir isatty ttyname get_terminal_size getxattr listxattr "
        "stat lstat fstat statvfs access listdir scandir walk fwalk readlink "
        "getlogin remove unlink rmdir removedirs mkdir makedirs mkfifo mknod rename renames replace "
        "link symlink chmod chown lchown utime truncate ftruncate sync fsync startfile "
        "getpid getppid getuid geteuid getgid getegid urandom uname getloadavg cpu_count times "
        "pwrite lseek sendfile fchmod fchown umask waitpid").split()} | {
    f"os.{p}{n}" for p in ("exec", "spawn", "posix_spawn") for n in ("", "l", "le", "lp", "lpe", "v", "ve", "vp", "vpe", "p")} | {
    f"os.path.{n}" for n in (
        "exists lexists isdir isfile islink ismount isjunction realpath samefile sameopenfile "
        "getsize getmtime getatime getctime abspath relpath expanduser").split()}
# The Need constructor, and the kinds or (kind, op) pairs the world answers with
# a write: an approval spent, a record kept, a door taken. Act owns those.
NEED = ("Need", "verdict.Need")
# Door claim takes the door when it stands, a rename and a write (world._take).
WRITES = {"claim", "ruleset-keep", "send-keep", ("door", "open"), ("door", "spend"), ("door", "claim"),
          ("door", "take"), ("worktree", "arrive"), ("worktree", "keep"), ("worktree", "leave")}
BUILTINS = {"open", "input", "breakpoint"}
# Methods that do I/O on whatever they are called on: Path's, a file's.
METHODS = {"read_text", "read_bytes", "write_text", "write_bytes", "iterdir", "rglob", "touch", "unlink", "rmdir",
           "mkdir", "is_dir", "is_file", "is_symlink", "samefile", "readlink", "symlink_to",
           "hardlink_to", "lstat", "chmod", "exists", "stat", "open", "glob"}

# Escapes at HEAD, file -> one entry per occurrence. Remove an entry when its
# guard stops escaping; the tests fail on one more or one fewer, so the list
# only shrinks. A direct read never goes on it: every read a guard makes is a
# Need (#114), and test_no_guard_is_let_off_a_direct_read holds it there.
KNOWN = {
    # Needs that write as they read, under one lock or rename; they move with
    # the approval spend (#84).
    "guards/ask_first.py": ["Need claim"],
    "guards/guard_github_issues.py": ["Need door claim", "Need door take"],
    "guards/guard_worktrees.py": ["Need worktree arrive"],
    # The parser ladder's shfmt rung (docs/decisions.md, "Runtime dependencies").
    "scan.py": ["import shutil", "import subprocess", "subprocess.run", "subprocess.TimeoutExpired", "shutil.which"],
}
# The design's one named exception to a pure step: parse runs programs.
LADDER = "scan.py"


def _imports(tree):
    """Local name -> the dotted name it stands for, from every import in `tree`."""
    names = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                names[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom):
            # A relative import is languette's own: `from ..verdict import Need as N` ->
            # languette.verdict.Need, never the stdlib `secrets` that `from . import secrets` would read as.
            pkg = "languette." if n.level else ""
            for a in n.names:
                names[a.asname or a.name] = f"{pkg}{n.module}.{a.name}" if n.module else f"{pkg}{a.name}"
    return names


def _dotted(node, names):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([names.get(node.id, node.id)] + parts[::-1])


def _barred(name):
    """`name` is barred, or hangs off one: `pathlib.Path.cwd` off `pathlib.Path`."""
    return any(name == m or name.startswith(m + ".") for m in CALLS | MODULES)


def escapes(source):
    """(line, what) for each way out of the process in `source`."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [(e.lineno or 0, f"cannot parse: {e.msg}")]
    names = _imports(tree)
    out = [(n.lineno, f"import {m}") for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
           for m in ([a.name for a in n.names] if isinstance(n, ast.Import) else
                     [n.module] if n.level == 0 and n.module else []) if _barred(m)]
    # A star import hides every name behind it.
    out += [(n.lineno, "import *") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
            if any(a.name == "*" for a in n.names)]
    # Any reference, called or not: `map(open, xs)` and `f = os.getcwd` escape too.
    inner = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Attribute, ast.Name)) and id(n) not in inner and isinstance(n.ctx, ast.Load):
            name = _dotted(n, names)
            if name and _barred(name) and (not isinstance(n, ast.Name) or n.id in names or n.id in BUILTINS):
                out.append((n.lineno, name))
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in METHODS \
                and not (_dotted(n.func, names) or "").startswith("os."):
            out.append((n.lineno, f".{n.func.attr}()"))
        elif isinstance(n, ast.Call) and (_dotted(n.func, names) or "").endswith(NEED) \
                and n.args and isinstance(n.args[0], ast.Constant):
            kind = n.args[0].value
            op = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else None
            # An op the source does not spell, on a kind with a write op, may be that op.
            if kind in WRITES:
                out.append((n.lineno, f"Need {kind}"))
            elif (kind, op) in WRITES or (op is None and any(w[0] == kind for w in WRITES if isinstance(w, tuple))):
                out.append((n.lineno, f"Need {kind} {'?' if op is None else op}"))
    return sorted(out)


def _found():
    return {str(f.relative_to(ROOT / "languette")): escapes(f.read_text()) for f in PURE}


def test_no_guard_and_not_the_verdict_reaches_past_the_process():
    bad = []
    for rel, found in _found().items():
        extra = Counter(w for _, w in found) - Counter(KNOWN.get(rel, []))
        bad += [f"languette/{rel}:{line}: {what}" for line, what in found if what in extra]
    assert_that(bad, empty())


def test_no_guard_is_let_off_a_direct_read():
    """Only the write Needs (#84) and the parser ladder stay on KNOWN: a guard,
    or a helper it imports, that reads for itself fails the check."""
    let_off = {rel: [w for w in calls if not w.startswith("Need ")] for rel, calls in KNOWN.items() if rel != LADDER}
    assert_that({rel: w for rel, w in let_off.items() if w}, equal_to({}))


def test_every_known_escape_is_still_there():
    found = _found()
    gone = {rel: sorted((Counter(calls) - Counter(w for _, w in found.get(rel, []))).elements())
            for rel, calls in KNOWN.items()}
    assert_that({rel: g for rel, g in gone.items() if g}, equal_to({}))


@pytest.mark.parametrize("source", [
    "open('x')",
    "import io\nio.open('x')",
    "import os\nos.path.exists('x')",
    "from os import path\npath.isdir('x')",
    "from os.path import realpath as r\nr('x')",
    "import os\nos.makedirs('x')",
    "import os\nos.replace('a', 'b')",
    "import os\nos.execvp('a', [])",
    "list(map(open, xs))",
    "import os\nf = os.getcwd\nf()",
    "import os\ncwd = payload.get('cwd') or os.getcwd()",
    "import os\nfd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)",
    "import os\nos.fstat(fd).st_mode",
    "import os\nwith os.fdopen(fd, 'rb') as f:\n    f.read()",
    "import os\nwhile not os.path.lexists(p):\n    p = os.path.dirname(p)",
    "import io\nio.FileIO('x')",
    "import codecs\ncodecs.open('x')",
    "import mmap",
    "import os\nos.preadv(fd, bufs, 0)",
    "import os\nsorted(xs, key=os.path.getmtime)",
    "import subprocess",
    "import subprocess as sp\nsp.run(['ls'])",
    "from subprocess import run",
    "import socket",
    "import urllib.request",
    "from time import time",
    "import datetime\ndatetime.datetime.now()",
    "from datetime import date\ndate.today()",
    "from pathlib import Path\nPath('x')",
    "from pathlib import Path\nPath.cwd()",
    "import pathlib\npathlib.Path.home()",
    "p.open()",
    "p.glob('*')",
    "p.read_text()",
    "p.exists()",
    "import os\nos.path.abspath('x')",
    "from os.path import expanduser\nexpanduser('~')",
    "import sys\nsys.stdin.read()",
    "import random",
    "from uuid import uuid4",
    "import os\nos.getpid()",
    "from languette.verdict import Need\nyield Need('claim', {})",
    "from languette import verdict\nyield verdict.Need('worktree', 'keep', r, t)",
    "yield Need('door', 'take', s, c)",
    "yield Need('door', 'claim', s, c)",
    "from ..verdict import Need as N\nyield N('claim', {})",
    "from os import *",
    "yield Need('door', op, s, c)",
    "import os\nos.uname()",
    "import platform",
    "import logging\nlogging.FileHandler('x')",
    "def f(:\n",
])
def test_the_check_catches(source):
    assert_that(escapes(source), is_not(empty()))


@pytest.mark.parametrize("source", [
    "import os\nos.path.join('a', 'b')",
    "import os\nos.path.dirname(os.path.normpath('a/b'))",
    "import os\nos.path.basename('a'); os.path.isabs('a'); os.path.splitext('a.b')",
    "import os\nos.environ.get('HOME')",
    "import os\nos.O_RDONLY",
    "import re\nre.compile('x').match('x')",
    "import json\njson.loads('{}')",
    "from urllib.parse import quote\nquote('x')",
    "from pathlib import PurePosixPath\nPurePosixPath('a') / 'b'",
    "d.get('exists')",
    "from languette import secrets\nsecrets.findings(s, [])",
    "yield Need('which', 'git')",
    "yield Need('worktree', 'recorded', r)",
    "import logging\nlogging.getLogger('x')",
    "from .. import paths\npaths.physical(x)",
    "from ..secrets import findings\nfindings(s, [])",
    "from . import secrets\nsecrets.findings(s, [])",
    "yield Need('which', name)",
    "yield Need('read', p, 1 << 20)",
    "yield Need('clock')",
    "yield Need('path', 'lexists', p)",
    "from .. import paths\nphys = yield from paths.physical(x)",
    "import codecs\ncodecs.decode(b, 'utf-8')",
    "import stat\nstat.S_ISREG(mode)",
])
def test_the_check_passes(source):
    assert_that(escapes(source), empty())
