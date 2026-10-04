"""no-bypass-labels: a label that waives a CI gate is a human's to apply.

`churn-ok` waives the churn gate and `mixed-loops-ok` the mixed-loops gate.
A gate whose bypass the gated party can apply to its own PR is not a gate, so
a session may not apply either label, in any repo, public or private. The
list is the bypass_labels option (CLAUDE_PLUGIN_OPTION_BYPASS_LABELS),
comma-separated; unset, empty or blank is the default list, so a
misconfiguration cannot open the gate. Names are compared case-folded, as
GitHub compares label names.

Three routes reach a label, and each is read:

- gh's flags: --label, --add-label and -l on `gh pr|issue create|new|edit`,
  --name/-n on `gh label edit`, since a rename puts the new name on every
  issue and PR that carries the old one, and the expansion of `gh alias
  set`, which is those flags for later;
- gh api: a write whose -f/-F/--field/--raw-field key names a label (or
  `new_name` on a labels/ path), a JSON payload passed by --input (a file,
  or `-` fed by a heredoc) on any path, and a graphql mutation that applies
  or renames labels by ID, which the guard cannot map to names;
- an MCP tool's field whose name says label, at any depth, and every string
  field of a tool whose name says label, unless the tool's name leads with a
  read verb (list, get, search, read) and says nothing that writes. An
  unknown tool is a write.

The gh is found through wrappers, `sh -c`, `eval`, a pipe into a shell, and
a heredoc fed to a shell, which is code; a heredoc fed to anything else is
text. A label the guard cannot read (built at run time, in a file it cannot
open, from stdin with no heredoc, by ID) is a deny that says why. A file is
read at hook time, so it is trusted only when nothing else in the command
runs before gh and could rewrite it. A label
named in text (a body, a title, a commit message, a heredoc) is not a label
applied: the scanner never descends into the quoted text of a gh or git
command.
"""

import json
import os
import re
import stat

from languette import scan as sw
from languette.verdict import Refuse, deny

NAME = "no-bypass-labels"
OPTION = "CLAUDE_PLUGIN_OPTION_BYPASS_LABELS"
DEFAULT = ("churn-ok", "mixed-loops-ok")

GH = re.compile(r"(?:^|/)gh\Z")
WRITES = frozenset("create new edit".split())
LABEL_FLAGS = frozenset("--label --add-label -l".split())
# gh api flags whose value is not a field, a method or the path.
API_VALUED = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
# Paths whose write can carry labels in an --input payload.
REPO = r"(?:repos/[^/]+/[^/]+|repositories/[^/]+)"
LABEL_PATH = re.compile(REPO + r"/(?:issues(?:/[^/]+(?:/labels)?)?|labels/[^/]+)/?")
RENAME_PATH = re.compile(REPO + r"/labels/[^/]+/?")
GRAPHQL_LABELS = re.compile(r"addLabelsToLabelable|labelIds|updateLabel")
GRAPHQL_WHY = "the graphql mutation applies or renames labels by ID, and label IDs are names the guard cannot read"
DEPTH = 4                                      # heredocs feeding shells feeding heredocs
READS = frozenset("list get search read".split())
# A word after the read verb that makes the tool a write after all.
WRITE_WORDS = frozenset("add set create update edit write apply put post patch assign rename replace "
                        "upsert merge modify change toggle attach tag mark link insert append save store "
                        "mutate sync push commit delete remove clear reset move copy and or then".split())
# Commands that may share the call with a gh that reads a file. None writes a
# byte to stdout that could become labels, so a redirect on one only
# truncates the file (pushd and popd print the directory stack).
INERT = frozenset("cd true :".split())
MAX_READ = 1 << 20
WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def _words(name):
    """snake_case, kebab-case and camelCase split into lower-case words."""
    return [w.lower() for w in WORDS.findall(name)]


def _reads(tool):
    w = _words(tool.rsplit("__", 1)[-1])
    return bool(w) and w[0] in READS and not WRITE_WORDS.intersection(w[1:])


def bypass_labels(env):
    got = [x.strip().casefold() for x in (env.get(OPTION) or "").split(",") if x.strip()]
    return tuple(got) or DEFAULT


def _split(v):
    return [x.strip() for x in v.split(",") if x.strip()]


class _Found:
    """What a command or call applies: label names, and the reasons some
    label could not be read."""

    def __init__(self):
        self.labels, self.unseen = [], []

    def value(self, v, live, what="the label"):
        if live:
            self.unseen.append(f"{what} `{v}` is built at run time")
        else:
            self.labels.extend(_split(v))

    def names(self, v, what):
        """A labels value in JSON: a list of names or {"name": ...}, or one
        comma-separated string."""
        if v is None or v == []:
            return
        if isinstance(v, str):
            self.labels.extend(_split(v))
        elif isinstance(v, list) and all(isinstance(x, str) or isinstance(x, dict) and isinstance(x.get("name"), str)
                                         for x in v):
            self.labels.extend((x if isinstance(x, str) else x["name"]).strip() for x in v)
        else:
            self.unseen.append(f"{what} is not a list of label names")


def _glued(t):
    """The value of a glued short flag: pflag reads -lx and -l=x alike."""
    return t[3:] if t[2:3] == "=" else t[2:]


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def _read(path, ctx):
    """The text of the file `path` names, as the shell will open it; raises
    Refuse, with what is wrong with the path, when the guard cannot open the
    same file, or when another command in the call could rewrite it first."""
    cwd, env, moved = ctx["cwd"], ctx["env"], ctx["moved"]
    if not ctx["alone"]:
        raise Refuse("is read at hook time, and another command in the same call could rewrite it before gh "
                     "reads it; run the gh on its own")
    p = path
    if p == "~" or p.startswith("~/"):
        if not env.get("HOME"):
            raise Refuse("names a home directory the guard cannot see")
        p = env["HOME"] + p[1:]
    if not os.path.isabs(p):
        if moved or not (isinstance(cwd, str) and os.path.isabs(cwd)):
            raise Refuse("is a relative path, and the guard cannot tell where the command stands")
        p = os.path.join(cwd, p)
    try:
        # Non-blocking, so a FIFO cannot stall the hook into its timeout.
        fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        raise Refuse(f"cannot be read ({e.strerror or e})")
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Refuse("is not a regular file")
    with os.fdopen(fd, "rb") as f:
        data = f.read(MAX_READ + 1)
    if len(data) > MAX_READ:
        raise Refuse(f"is over {MAX_READ} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Refuse(f"cannot be read ({e})")


def _payloads(src, live, ctx):
    """The JSON texts an --input value feeds gh api."""
    if live:
        raise Refuse(f"the --input path `{src}` is built at run time")
    if src == "-":
        if not ctx["bodies"]:
            raise Refuse("the --input payload comes from stdin and no heredoc in the command feeds it")
        if any(live for _, live in ctx["bodies"]):
            raise Refuse("the heredoc feeding --input is built at run time (an unquoted delimiter and a $ or backtick)")
        return [body for body, _ in ctx["bodies"]]
    try:
        return [_read(src, ctx)]
    except Refuse as e:
        raise Refuse(f"the --input file `{src}` {e}")


def _input(f, src, live, path, ctx):
    try:
        texts = _payloads(src, live, ctx)
    except Refuse as e:
        f.unseen.append(str(e))
        return
    for t in texts:
        if path == "graphql":
            if GRAPHQL_LABELS.search(t):
                f.unseen.append(GRAPHQL_WHY)
            continue
        try:
            doc = json.loads(t)
        except ValueError:
            if src != "-" and LABEL_PATH.fullmatch(path):  # a heredoc may feed another command
                f.unseen.append(f"the --input payload `{src}` is not JSON")
            continue
        if isinstance(doc, list):
            f.names(doc, "the --input payload")
        elif isinstance(doc, dict):
            for key in ("labels", "new_name"):
                if key in doc and (key == "labels" or RENAME_PATH.fullmatch(path)):
                    f.names(doc[key], f"the --input payload's {key}")
    if src == "-" and not any(_parses(t) for t in texts) and LABEL_PATH.fullmatch(path):
        f.unseen.append("no heredoc in the command holds the JSON the --input payload reads from stdin")


def _parses(t):
    try:
        json.loads(t)
        return True
    except ValueError:
        return False


def _api(f, s, i, b, ctx):
    method, path, fields, inputs = None, None, [], []
    j = i
    while j <= b:
        t = _wv(s, j)
        nxt = (_wv(s, j + 1), s.live[j + 1]) if j < b else None
        if t in ("-X", "--method"):
            method, j = (nxt[0].upper() if nxt else method), j + 1
        elif t.startswith("--method="):
            method = t[9:].upper()
        elif t.startswith("-X") and len(t) > 2:
            method = _glued(t).upper()
        elif t in ("-f", "-F", "--field", "--raw-field"):
            fields.append((t, *nxt) if nxt else (t, "", False))
            j += 1
        elif t[:2] in ("-f", "-F") and len(t) > 2:
            fields.append((t[:2], _glued(t), s.live[j]))
        elif t.startswith(("--field=", "--raw-field=")):
            fields.append((t.split("=", 1)[0], t.split("=", 1)[1], s.live[j]))
        elif t == "--input":
            inputs.append(nxt or ("", False))
            j += 1
        elif t.startswith("--input="):
            inputs.append((t[8:], s.live[j]))
        elif t in API_VALUED:
            j += 1
        elif not t.startswith("-") and s.k[j] != ";" and path is None:
            path = t
        j += 1
    if method in ("GET", "HEAD") or (method is None and not fields and not inputs):
        return
    p = re.sub(r"^https?://[^/]+/", "", path or "").lstrip("/").split("?", 1)[0]
    if p == "graphql":
        for flag, kv, live in fields:
            v = kv.split("=", 1)[1] if "=" in kv else kv
            if v.startswith("@") and flag in ("-F", "--field"):
                try:
                    v = _read(v[1:], ctx)
                except Refuse as e:
                    f.unseen.append(f"the graphql field reads the file `{v[1:]}`, which {e}")
                    continue
            if GRAPHQL_LABELS.search(v):
                f.unseen.append(GRAPHQL_WHY)
        for src, live in inputs:
            _input(f, src, live, p, ctx)
        return
    for flag, kv, live in fields:
        if "=" not in kv:
            continue
        key, v = kv.split("=", 1)
        if "label" not in key.lower() and not (key == "new_name" and RENAME_PATH.fullmatch(p)):
            continue
        if v.startswith("@") and flag in ("-F", "--field"):
            try:
                f.value(_read(v[1:], ctx).strip(), live)
            except Refuse as e:
                f.unseen.append(f"the field {key} reads the file `{v[1:]}`, which {e}")
        else:
            f.value(v, live, f"the field {key}")
    for src, live in inputs:
        _input(f, src, live, p, ctx)


def _gh(f, s, g, b, ctx):
    if g + 2 > b:
        return
    group, act = s.w[g + 1], s.w[g + 2]
    if group == "api":
        _api(f, s, g + 2, b, ctx)
        return
    if group == "alias":
        _alias(f, s, g, b, act)
        return
    if group in ("pr", "issue") and act in WRITES:
        flags, glued = LABEL_FLAGS, ("--label=", "--add-label=")
    elif group == "label" and act == "edit":
        flags, glued = frozenset(("--name", "-n")), ("--name=",)
    else:
        return
    short = next(x for x in flags if len(x) == 2)
    j = g + 3
    while j <= b:
        t = _wv(s, j)
        if t in flags:
            if j == b:
                f.unseen.append(f"`{t}` has no value the guard can see")
            else:
                f.value(_wv(s, j + 1), s.live[j + 1])
            j += 1
        elif t.startswith(glued):
            f.value(t.split("=", 1)[1], s.live[j])
        elif t.startswith(short) and len(t) > 2 and not t.startswith("--"):
            f.value(_glued(t), s.live[j])
        j += 1


def _alias(f, s, g, b, act):
    """`gh alias set NAME EXPANSION` stores gh arguments for later: every word
    of the expansion is read as one. `gh alias import FILE` stores aliases the
    guard cannot see."""
    if act == "set":
        for j in range(g + 4, b + 1):
            if s.live[j]:
                f.unseen.append(f"the alias expansion `{_wv(s, j)}` is built at run time")
            else:
                f.labels.extend(x for x in re.split(r"[\s,=]+", _wv(s, j)) if x)
    elif act == "import":
        src = _wv(s, g + 3) if g + 3 <= b else "stdin"
        f.unseen.append(f"the alias file `{src}` may define an alias that applies a label")


def _alone(scans):
    """One segment is the gh, and every other is a shell running quoted text
    the scan already holds (not built at run time) or a command that writes
    no file."""
    ghs = 0
    for s, nested in scans:
        for a, b in s.segments():
            if a > b:
                continue
            if sw.cmd_index(s, a, b, GH, nested) is not None:
                ghs += 1                       # a second gh can download into the file
                if ghs > 1:
                    return False
                continue
            c = sw.seg_cmd(s, a, b)
            w = s.w[c].rsplit("/", 1)[-1] if c is not None else None
            quoted = [j for j in range(c, b + 1) if s.k[j] == "q"] if c is not None else []
            if w not in INERT and not (w in sw.SHELL and quoted and not any(s.live[j] for j in quoted)):
                return False
    return True


def _bash(f, cmd, cwd, env, depth=0, alone=True):
    text = sw.strip_heredocs(cmd + "\n")
    texts = sw.texts_of(text)
    scans = [(sw.Scan(t), nested) for t, nested in texts]
    bodies = sw.heredocs(cmd + "\n")
    ctx = {"cwd": cwd, "env": env, "bodies": bodies,
           "moved": any(k == "w" and w in ("cd", "pushd", "popd") for s, _ in scans for k, w in zip(s.k, s.w)),
           "alone": alone and _alone(scans)}
    for s, nested in scans:
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, GH, nested)
            if g is not None:
                _gh(f, s, g, b, ctx)
    # A heredoc fed to a shell (`sh <<EOF`, `cat <<EOF | sh`) is a command of
    # its own; fed to anything else it is text.
    top, k = scans[0][0], 0
    for a, b in top.segments():
        for j in range(a, b + 1):
            if top.k[j] == "w" and top.w[j] == "HEREDOC":
                shell = top.shellseg or any(top.k[i] == "w" and top.w[i] in sw.SHELL for i in range(a, b + 1))
                if shell and k < len(bodies) and depth < DEPTH:
                    if bodies[k][1]:
                        f.unseen.append("the heredoc fed to a shell is built at run time (an unquoted delimiter and a $ or backtick)")
                    else:
                        _bash(f, bodies[k][0], cwd, env, depth + 1, ctx["alone"])
                k += 1


def _mcp(f, v, any_string, depth=0):
    """Every field, at any depth, whose name says label; in a tool whose name
    says label, every string too, since `add_label` may carry the name in
    `name` or `value`."""
    if depth > 16:
        f.unseen.append("the input nests too deep to read")
    elif isinstance(v, dict):
        for key, x in v.items():
            words = _words(key) if isinstance(key, str) else []
            if not ("label" in words or "labels" in words):
                _mcp(f, x, any_string, depth + 1)
            elif ("id" in words or "ids" in words) and x not in (None, []):
                f.unseen.append(f"the field {key} names labels by ID, which the guard cannot map to names")
            else:
                f.names(x, f"the field {key}")
    elif isinstance(v, list):
        for x in v:
            _mcp(f, x, any_string, depth + 1)
    elif isinstance(v, str) and any_string:
        f.labels.extend(_split(v))


def check(payload, env=os.environ):
    tool = payload.get("tool_name")
    inp = payload.get("tool_input")
    f = _Found()
    if tool == "Bash":
        cmd = inp.get("command") if isinstance(inp, dict) else None
        if not isinstance(cmd, str) or not cmd.strip():
            return None
        _bash(f, cmd, payload.get("cwd"), env)
    elif isinstance(tool, str) and tool.startswith("mcp__"):
        if not isinstance(inp, dict) or _reads(tool):
            return None
        _mcp(f, inp, "label" in _words(tool.rsplit("__", 1)[-1]) or "labels" in _words(tool.rsplit("__", 1)[-1]))
    else:
        return None
    bad = bypass_labels(env)
    hit = next((x.casefold() for x in f.labels if x.casefold() in bad), None)
    if hit:
        return deny(f"{NAME}: the label `{hit}` is a human's to apply, not a session's: it waives a CI gate, "
                    "and a gate whose bypass the gated party can apply is not a gate. Split the change "
                    "instead, or say in the PR body why it needs the waiver and leave the label for the "
                    "user to add by hand.")
    if f.unseen:
        return deny(f"{NAME}: {f.unseen[0]}, so the guard cannot tell whether it applies a bypass label "
                    f"({', '.join(bad)}). Write the label literally in the command, or leave it for the "
                    "user to add.")
    return None
