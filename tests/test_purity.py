"""The purity check (docs/design/guard-pipeline.md): every guard and the
verdict, read as source and never run, may not open a file, start a program,
open a connection, read the clock or ask the disk about a path. What a guard
needs from the world it yields as a Need; languette.world answers it.

A list of known ways out, not a proof: it catches the slip a well-meaning
author makes, not a deliberate escape (`eval`, a name built at run time)."""

import ast
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
        for n in ast.walk(ast.parse(f.read_text())):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else \
                [n.module] + [f"{n.module}.{a.name}" for a in n.names] if isinstance(n, ast.ImportFrom) and n.module else []
            todo += [ROOT / (m.replace(".", "/") + ".py") for m in mods
                     if m.startswith("languette.") and (ROOT / (m.replace(".", "/") + ".py")).is_file()]
    return sorted(seen)


PURE = _pure()

# Whole modules whose every call reaches past the process.
MODULES = {"subprocess", "socket", "ssl", "time", "shutil", "glob", "tempfile", "fcntl", "select", "selectors",
           "asyncio", "multiprocessing", "pty", "urllib.request", "http.client", "ftplib", "smtplib", "sqlite3",
           "webbrowser"}
# Calls by dotted name. os.path is pure but for the ones that stat the disk.
CALLS = {"open", "io.open", "builtins.open", "input", "breakpoint", "datetime.datetime.now",
         "datetime.datetime.utcnow", "datetime.datetime.today", "datetime.date.today",
         "pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"} | {
    f"os.{n}" for n in (
        "open fdopen read write close pipe dup dup2 system popen fork forkpty kill killpg getcwd getcwdb chdir "
        "stat lstat fstat statvfs access listdir scandir walk fwalk readlink "
        "remove unlink rmdir removedirs mkdir makedirs mkfifo mknod rename renames replace "
        "link symlink chmod chown lchown utime truncate ftruncate sync fsync startfile").split()} | {
    f"os.{p}{n}" for p in ("exec", "spawn", "posix_spawn") for n in ("", "l", "le", "lp", "lpe", "v", "ve", "vp", "vpe", "p")} | {
    f"os.path.{n}" for n in (
        "exists lexists isdir isfile islink ismount isjunction realpath samefile sameopenfile "
        "getsize getmtime getatime getctime").split()}
# Methods that do I/O on whatever they are called on: Path's, a file's.
METHODS = {"read_text", "read_bytes", "write_text", "write_bytes", "iterdir", "rglob", "touch", "unlink", "rmdir",
           "mkdir", "is_dir", "is_file", "is_symlink", "samefile", "readlink", "symlink_to",
           "hardlink_to", "lstat", "chmod", "exists", "stat"}

# Escapes at HEAD, file -> calls, each to become a Need. Remove a line when its
# guard yields instead; the test fails while a listed escape is gone, so the
# list only shrinks.
KNOWN = {
    "guards/guard_bypass_labels.py": {"os.open", "os.fstat", "os.close", "os.fdopen"},
    "guards/guard_disk.py": {"os.getcwd"},
    "guards/guard_permissions.py": {"os.getcwd"},
    "guards/guard_recursive_delete.py": {"os.path.lexists", "os.path.realpath", "os.getcwd"},
    "paths.py": {"os.path.lexists", "os.path.realpath"},
    # The parser ladder's shfmt rung (docs/decisions.md, "Runtime dependencies").
    "scan.py": {"import shutil", "import subprocess", "subprocess.run", "shutil.which"},
}


def _imports(tree):
    """Local name -> the dotted name it stands for, from every import in `tree`."""
    names = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                names[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            for a in n.names:
                names[a.asname or a.name] = f"{n.module}.{a.name}"
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
    return name in CALLS or any(name == m or name.startswith(m + ".") for m in MODULES)


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
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        name = _dotted(n.func, names)
        if name and _barred(name):
            out.append((n.lineno, name))
        elif isinstance(n.func, ast.Attribute) and n.func.attr in METHODS and not (name or "").startswith("os.path."):
            out.append((n.lineno, f".{n.func.attr}()"))
    return sorted(set(out))


def _found():
    return {str(f.relative_to(ROOT / "languette")): {w for _, w in escapes(f.read_text())} for f in PURE}


def test_no_guard_and_not_the_verdict_reaches_past_the_process():
    bad = [f"languette/{rel}:{line}: {what}" for f in PURE
           for rel in [str(f.relative_to(ROOT / "languette"))]
           for line, what in escapes(f.read_text()) if what not in KNOWN.get(rel, set())]
    assert_that(bad, empty())


def test_every_known_escape_is_still_there():
    found = _found()
    assert_that({rel: calls - found.get(rel, set()) for rel, calls in KNOWN.items() if calls - found.get(rel, set())},
                equal_to({}))


@pytest.mark.parametrize("source", [
    "open('x')",
    "import io\nio.open('x')",
    "import os\nos.path.exists('x')",
    "from os import path\npath.isdir('x')",
    "from os.path import realpath as r\nr('x')",
    "import os\nos.makedirs('x')",
    "import os\nos.replace('a', 'b')",
    "import os\nos.execvp('a', [])",
    "import subprocess",
    "import subprocess as sp\nsp.run(['ls'])",
    "from subprocess import run",
    "import socket",
    "import urllib.request",
    "from time import time",
    "import datetime\ndatetime.datetime.now()",
    "from datetime import date\ndate.today()",
    "from pathlib import Path\nPath('x')",
    "p.read_text()",
    "p.exists()",
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
])
def test_the_check_passes(source):
    assert_that(escapes(source), empty())
