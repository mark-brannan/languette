"""The parser ladder (docs/decisions.md, "Parse check") picks who reads the
text: a user-installed shfmt when it is on PATH and new enough, then `bash
-n`, then the awk port in languette.lexer. Each rung that reads the text either accepts it
or refuses it (Unparseable), and a refusal is final; a rung that is missing,
crashed or cannot say passes the text down. A pip parser, if installed, only
adds the column to a refusal from below shfmt. Only shfmt's tree is mapped to words: a real parser decides where
words and quotes begin and end, the awk lexer still shapes each piece, so the
tokens are the same contract whichever rung read them. Below shfmt the awk
lexer reads the words; the rung above it only accepts or refuses.

The one module that runs programs (tests/test_purity.py, LADDER).
"""

import functools
import json
import os
import re
import shutil
import subprocess

from .quoting import strip_heredocs, _qopen


# 3.6.0 has `--to-json` in the shape mvdan/sh#900 gave it; Ubuntu jammy's
# 3.4.3 has only `-tojson`, in the older shape.
SHFMT_MIN = (3, 6, 0)
SHFMT_TIMEOUT = 2                              # seconds; a parse measures ~6 ms
BASH_TIMEOUT = 2                               # seconds
RUNGS = ("shfmt", "bash -n", "awk")            # tests narrow this to one rung
# The pip parsers asked for a refusal's column, in turn. Which comes first is
# open (#4); tree-sitter-bash first is an assumption.
PIP = ("tree-sitter-bash", "bashlex")


class Unparseable(Exception):
    """A rung read the command and refused it. Bad input is a deny, never a
    reason to try a weaker parser. `rung` names the reader."""

    def __init__(self, why, rung=None):
        super().__init__(why)
        self.rung = rung


class RunFailed(Unparseable):
    """The parser's run failed, not the text: a timeout, a signal, the OS.
    Scan re-raises it rather than read the text with awk."""


class TooBig(Unparseable):
    """The text is over a size or weight limit, so no parser reads it: a
    parser's time grows with nesting, and a limit on the text, unlike a
    timeout, gives the same answer on every machine. Scan re-raises it."""


class TooMany(TooBig):
    """The text holds more nested shell strings than texts_of reads
    (NESTED_CAP texts, the command itself among them): one past the cap
    could be the one that runs."""


LENGTH_MAX = 64 * 1024                         # bytes
WEIGHT_MAX = 10_000                            # ~450 ms of shfmt on a quarter CPU, 4x under its timeout
_KEYWORD_CLOSER = {"if": "fi", "case": "esac", "do": "done"}
KEYWORD_LEADS = frozenset("if then else elif do while until ! time".split())
_CODE_TOKEN = re.compile(r"""\\.|\$'(?:[^'\\]|\\.)*'|'[^']*'|"|\$\(\(|\$\(|\$\{|&&|\|\||\|&|;;|"""
                         r"""[|&;\n(){}`]|#|[^\s;|&(){}<>`'"\\$#]+""", re.S)
_DQ_TOKEN = re.compile(r"""\\.|"|\$\(\(|\$\(|\$\{|`""", re.S)


def weight(text):
    """How hard `text` is for a parser, in one linear pass: every `$(`, `$((`,
    `${`, `(`, `{`, backtick, `if`, `case` and `do`, and every `&&`, `||` and
    `|`, adds the depth it stands at. A chain operator nests the rest of its
    list one level deeper; `;`, `&` and a newline end the chain. Quoted text
    adds nothing but the substitutions a double quote keeps, and heredoc
    bodies are read as strip_heredocs leaves them. A closer that does not
    match the innermost opener is ignored, so a stray `)` or `done` never
    lowers the depth."""
    text = strip_heredocs(text)
    frames = [[None, 0, True]]                  # [closer, chain, is code]
    depth, w, i, at_cmd = 1, 0, 0, True         # depth: code frames plus their chains

    def push(closer):
        nonlocal depth, w
        frames.append([closer, 0, True])
        depth += 1
        w += depth

    while True:
        code = frames[-1][2]
        m = (_CODE_TOKEN if code else _DQ_TOKEN).search(text, i)
        if not m:
            return w
        k, i = m.group(), m.end()
        if not code:
            if k == '"':
                frames.pop()
            elif k == "$((":
                push(")"); push(")")
            elif k in ("$(", "`"):
                push(k[-1] if k == "`" else ")")
            elif k == "${":
                push("}")
            continue
        top = frames[-1]
        if k == "#" and m.start() and text[m.start() - 1] not in " \t\n;|&()`":
            continue                            # mid-word: not a comment
        if k == "#":
            e = text.find("\n", i)
            i = len(text) if e < 0 else e
        elif k == '"':
            frames.append(['"', 0, False])
        elif k in ("$((", "$(", "(", "{", "${") or (k == "`" and top[0] != "`"):
            for c in {"$((": "))", "${": "}", "{": "}", "`": "`"}.get(k, ")"):
                push(c)
            at_cmd = k != "${"
        elif k in (")", "}", "`") or k in _KEYWORD_CLOSER.values() and at_cmd:
            if top[0] == k and len(frames) > 1:
                frames.pop()
                depth -= 1 + top[1]
            at_cmd = k == "`" or k in _KEYWORD_CLOSER.values()
        elif k in ("&&", "||", "|", "|&"):
            top[1] += 1
            depth += 1
            w += depth
            at_cmd = True
        elif k in (";", ";;", "&", "\n"):
            depth -= top[1]
            top[1] = 0
            at_cmd = True
        elif at_cmd and k in _KEYWORD_CLOSER:
            push(_KEYWORD_CLOSER[k])
        elif not (at_cmd and k in KEYWORD_LEADS):
            at_cmd = False


def _limit(text):
    """Raise TooBig when `text` is over LENGTH_MAX bytes or WEIGHT_MAX weight."""
    n = len(text.encode("utf-8", "surrogatepass"))
    if n > LENGTH_MAX:
        raise TooBig(f"it is {n:,} bytes, over the limit of {LENGTH_MAX:,}", "limit")
    n = weight(text)
    if n > WEIGHT_MAX:
        raise TooBig(f"its nesting weighs {n:,}, over the limit of {WEIGHT_MAX:,}", "limit")


def _run(argv, text, timeout, **kw):
    """subprocess.run on `text`, or None when the program is not there.
    Raises Unparseable when the run failed rather than the program: past its
    timeout, killed by a signal, or refused by the OS. Those turn on the
    machine's load, not the command, so they deny; passing the command down a
    rung would let the clock pick its reader."""
    name = os.path.basename(argv[0])
    try:
        r = subprocess.run(argv, input=text.encode("utf-8", "surrogatepass") if text is not None else None,
                           capture_output=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        raise RunFailed(f"{name} took over {timeout} s; a busy machine can cause this, so retry") from None
    except FileNotFoundError:
        return None
    except OSError as e:
        raise RunFailed(f"{name} could not run ({e.strerror or e}); retry") from None
    if r.returncode < 0:
        raise RunFailed(f"{name} was killed by signal {-r.returncode}; retry")
    return r


@functools.lru_cache(maxsize=1)
def shfmt():
    """Path of a usable shfmt, or None: missing, too old, or no version.
    Raises Unparseable when asking it failed (_run); that is not cached."""
    path = shutil.which("shfmt")
    if not path:
        return None
    r = _run([path, "--version"], None, SHFMT_TIMEOUT)
    if r is None:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", r.stdout.decode("utf-8", "replace"))
    return path if r.returncode == 0 and m and tuple(map(int, m.groups())) >= SHFMT_MIN else None


@functools.lru_cache(maxsize=256)
def _shfmt_tree(text):
    """shfmt's AST of `text`, or None when shfmt is missing or crashed on this
    text. Raises Unparseable when shfmt reports a syntax error (exit 1,
    "line:col: why") or the run failed (_run)."""
    path = shfmt()
    if not path:
        return None
    r = _run([path, "--to-json", "-ln=bash"], text, SHFMT_TIMEOUT)
    if r is None:
        return None
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode == 1 and re.match(r"(?:<standard input>:)?\d+:\d+: ", err):
        raise Unparseable(err.splitlines()[0])
    if r.returncode:
        return None
    try:
        tree = json.loads(r.stdout)
    except ValueError:
        return None
    return tree if isinstance(tree, dict) and tree.get("Type") == "File" else None


@functools.lru_cache(maxsize=1)
def _ts_parser():
    """A tree-sitter parser for bash, or None when either package is missing
    or will not load."""
    try:
        import tree_sitter
        import tree_sitter_bash
        return tree_sitter.Parser(tree_sitter.Language(tree_sitter_bash.language()))
    except Exception:  # noqa: BLE001 -- any failure to load is a missing rung
        return None


@functools.lru_cache(maxsize=256)
def _tree_sitter(text):
    """The line:col of the first thing tree-sitter-bash could not read in
    `text`, or None: no package, a crash, or a clean tree. tree-sitter never
    fails a parse; it recovers, marking what it could not read with an ERROR
    node and what it had to supply with a MISSING one. It locates; it never
    decides."""
    parser = _ts_parser()
    if parser is None:
        return None
    try:
        tree = parser.parse(text.encode("utf-8", "surrogatepass"))
        bad = _ts_error(tree.root_node) if tree.root_node.has_error else None
    except Exception:  # noqa: BLE001 -- a crash adds no column
        return None
    if bad is None:
        return None
    row, col = bad.start_point
    if not bad.is_missing:                     # an ERROR node takes the blank before it
        raw = bad.text
        col += len(raw) - len(raw.lstrip(b" \t"))
    return f"{row + 1}:{col + 1}"


@functools.lru_cache(maxsize=1)
def _bashlex_mod():
    """The bashlex module, or None when it is missing or will not load."""
    try:
        import bashlex
        return bashlex
    except Exception:  # noqa: BLE001 -- any failure to load is a missing parser
        return None


@functools.lru_cache(maxsize=256)
def _bashlex(text):
    """The line:col where bashlex stopped reading `text`, or None: no
    package, a crash, a clean parse, or an error with no position (an
    unsupported construct raises NotImplementedError). It locates; it never
    decides."""
    m = _bashlex_mod()
    if m is None:
        return None
    try:
        m.parse(text)
    except Exception as e:  # noqa: BLE001 -- only a positioned error gives a column
        pos = getattr(e, "position", None)
        if not isinstance(pos, int) or isinstance(pos, bool):
            return None
        pos = min(max(pos, 0), len(text))
        return f"{text.count(chr(10), 0, pos) + 1}:{pos - text.rfind(chr(10), 0, pos)}"
    return None


def _ts_error(root):
    """The first ERROR or MISSING node under root, in source order."""
    stack = [root]
    while stack:
        n = stack.pop()
        if n.is_error or n.is_missing:
            return n
        if n.has_error:
            stack.extend(reversed(n.children))
    return None


@functools.lru_cache(maxsize=256)
def _bash_n(text):
    """True when `bash -n` accepts `text`, None when there is no bash to ask.
    Raises Unparseable with bash's first line, its "bash: " prefixes dropped,
    or when the run failed (_run). It runs nothing, and says less than shfmt:
    a line, no column."""
    r = _run(["bash", "-n"], text, BASH_TIMEOUT, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    if r is None:
        return None
    if r.returncode == 0:
        return True
    err = r.stderr.decode("utf-8", "replace").strip().splitlines()
    raise Unparseable(re.sub(r"^(?:\S*bash: )+", "", err[0]) if err else "syntax error")


def _awk(text):
    """The awk rung's one refusal (docs/decisions.md, "Parser ladder
    refusals"): a quote still open at the end of the text, heredoc bodies
    aside, read by the lexer's own rules (_qopen)."""
    t = strip_heredocs(text)
    q, i = _qopen(t)
    if q:
        snip = t[i:i + 24].split("\n")[0]
        raise Unparseable(f"the {q} opened at `{snip}` never closes")


def _column(text):
    """(parser, line:col) from the first pip parser that locates a fault in
    `text`, or None."""
    for name in PIP:
        at = {"tree-sitter-bash": _tree_sitter, "bashlex": _bashlex}[name](text)
        if at:
            return name, at
    return None


def parse(text, words=False):
    """(rung, tree) from the first rung that reads the text; the tree is None
    on the awk rung and True from bash -n. Raises Unparseable, naming the
    rung, when one refuses the text; below shfmt, a pip parser adds the
    column, never to a failed run. words: only the rungs whose reading Scan
    maps to words, shfmt and awk. A text over a limit is refused before any
    rung reads it (TooBig)."""
    _limit(text)
    for rung in RUNGS:
        if words and rung not in ("shfmt", "awk"):
            continue
        read = {"shfmt": _shfmt_tree, "bash -n": _bash_n, "awk": _awk}[rung]
        try:
            tree = read(text)
        except Unparseable as e:
            e.rung = rung
            at = _column(text) if rung != "shfmt" and not isinstance(e, RunFailed) else None
            if at:
                e.args = (f"{e}, at {at[1]} per {at[0]}",)
            raise
        if rung == "awk" or tree is not None:
            return rung, tree
    raise RuntimeError(f"no parser rung read the text (rungs: {', '.join(RUNGS)})")


def check(command):
    """Raise Unparseable when the top rung refuses the command itself."""
    parse(command)
