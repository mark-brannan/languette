"""guard-bypass-labels: a label named in the bypass_labels option is a human's
to apply.

A label that waives a CI gate is the user's to apply unless the option names
it. The list is the bypass_labels option (CLAUDE_PLUGIN_OPTION_BYPASS_LABELS),
comma-separated, and it is empty by default: unset, empty or blank guards no
label and the guard allows every command. A deployment that
wants the gate names its labels; a gate whose bypass the gated party can
apply to its own PR is not a gate, so a session may then not apply a named
label, in any repo, public or private. Names are compared case-folded, as
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

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import Need, Refuse, deny, planned

NAME = "guard-bypass-labels"
OPTION = "CLAUDE_PLUGIN_OPTION_BYPASS_LABELS"
DEFAULT = ()                                   # no label is guarded until the option names one

WRITES = frozenset("create new edit".split())
LABEL_FLAGS = frozenset("--label --add-label -l".split())
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
WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def _words(name):
    """snake_case, kebab-case and camelCase split into lower-case words."""
    return [w.lower() for w in WORDS.findall(name)]


def _reads(tool):
    w = _words(tool.rsplit("__", 1)[-1])
    return bool(w) and w[0] in READS and not WRITE_WORDS.intersection(w[1:])


def bypass_labels(env):
    got = [x.casefold() for x in sw.listed(env.get(OPTION))]
    return tuple(got) or DEFAULT


class _Found:
    """What a command or call applies: label names, and the reasons some
    label could not be read. `files` is what the runner read so far, path ->
    text or the Refuse it came to; a path the walk needs and `files` lacks
    goes on `wanted`, for plan to ask for and judge to walk the command again."""

    def __init__(self, files):
        self.labels, self.unseen = [], []
        self.files, self.wanted = files, []

    def value(self, v, live, what="the label"):
        if live:
            self.unseen.append(f"{what} `{v}` is built at run time")
        else:
            self.labels.extend(sw.listed(v))

    def names(self, v, what):
        """A labels value in JSON: a list of names or {"name": ...}, or one
        comma-separated string."""
        if v is None or v == []:
            return
        if isinstance(v, str):
            self.labels.extend(sw.listed(v))
        elif isinstance(v, list) and all(isinstance(x, str) or isinstance(x, dict) and isinstance(x.get("name"), str)
                                         for x in v):
            self.labels.extend((x if isinstance(x, str) else x["name"]).strip() for x in v)
        else:
            self.unseen.append(f"{what} is not a list of label names")


def _glued(t):
    """The value of a glued short flag: pflag reads -lx and -l=x alike."""
    return t[3:] if t[2:3] == "=" else t[2:]


def _read(path, ctx):
    """The text of the file `path` names, as the shell will open it and the
    runner read it (ctx's files); raises Refuse, with what is wrong with the
    path, when the guard cannot have the same file, or when another command in
    the call could rewrite it first."""
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
    if p not in ctx["files"]:
        ctx["wanted"].append(p)
        raise Refuse("is not read yet")        # plan asks for it, judge walks the command again
    got = ctx["files"][p]
    if isinstance(got, Refuse):
        raise Refuse(str(got))
    return got


def _text(got):
    """A planned read's answer: the file's text, or the Refuse the world's
    exception comes to."""
    if isinstance(got, UnicodeDecodeError):
        return Refuse(f"cannot be read ({got})")
    if isinstance(got, OSError):
        return Refuse(f"cannot be read ({got.strerror or got})")
    if isinstance(got, ValueError):            # not a regular file, or past MAX_READ
        return Refuse(str(got))
    if isinstance(got, Exception):
        raise got
    return got


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
    api = sw.gh_api(s, i, b)
    if api.method in ("GET", "HEAD") or (api.method == "" and not api.sends):
        return
    fields = [(a.flag, a.text or "", a.live) for a in api.args if a.flag != "--input"]
    inputs = [(a.text or "", a.live) for a in api.args if a.flag == "--input"]
    # The first operand, even an empty one, where gh_api.path skips it.
    p = sw.gh_api_path(api.operands[0]) if api.operands else ""
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
        t = sw.word(s, j)
        if t in flags:
            if j == b:
                f.unseen.append(f"`{t}` has no value the guard can see")
            else:
                f.value(sw.word(s, j + 1), s.live[j + 1])
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
                f.unseen.append(f"the alias expansion `{sw.word(s, j)}` is built at run time")
            else:
                f.labels.extend(x for x in re.split(r"[\s,=]+", sw.word(s, j)) if x)
    elif act == "import":
        src = sw.word(s, g + 3) if g + 3 <= b else "stdin"
        f.unseen.append(f"the alias file `{src}` may define an alias that applies a label")


def _bash(f, doc, cmd, cwd, env, depth=0, alone=True):
    scans = [(doc.scan(t), nested) for t, nested in doc.texts(text=cmd)]
    bodies = doc.heredocs(cmd)
    ctx = {"cwd": cwd, "env": env, "bodies": bodies, "files": f.files, "wanted": f.wanted,
           "moved": any(sw.cd_present(s) for s, _ in scans),
           "alone": alone and sw.alone(scans, sw.GH)}
    for s, nested in scans:
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, sw.GH, nested)
            if g is not None:
                _gh(f, s, g, b, ctx)
    # A heredoc fed to a shell (`sh <<EOF`, `cat <<EOF | sh`) is a command of
    # its own; fed to anything else it is text.
    # Its pipeline is its own segment and every segment piped on from it.
    top, k = scans[0][0], 0
    for a, b in top.segments():
        e = b
        while e + 1 in top.pipes:
            e = next(y for x, y in top.segments() if x == e + 2)
        for j in range(a, b + 1):
            if top.k[j] == "w" and top.w[j] == "HEREDOC":
                shell = any(top.k[i] == "w" and top.w[i] in sw.SHELL for i in range(a, e + 1))
                if shell and k < len(bodies) and depth < DEPTH:
                    if bodies[k][1]:
                        f.unseen.append("the heredoc fed to a shell is built at run time (an unquoted delimiter and a $ or backtick)")
                    else:
                        _bash(f, doc, bodies[k][0], cwd, env, depth + 1, ctx["alone"])
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
        f.labels.extend(sw.listed(v))


def parse(doc):
    """One walk of the call with no file read yet: (what it found, the
    document, Bash command and cwd to walk again once its files are read, or
    None; env)."""
    payload, env, tool, inp = doc.payload, doc.env, doc.tool, doc.tool_input
    f = _Found({})
    if tool == "Bash":
        cmd = inp.get("command") if isinstance(inp, dict) else None
        if not isinstance(cmd, str) or not cmd.strip():
            return None
        _bash(f, doc, cmd, payload.get("cwd"), env)
        return f, (doc, cmd, payload.get("cwd")), env
    if isinstance(tool, str) and tool.startswith("mcp__"):
        if not isinstance(inp, dict) or _reads(tool):
            return None
        _mcp(f, inp, "label" in _words(tool.rsplit("__", 1)[-1]) or "labels" in _words(tool.rsplit("__", 1)[-1]))
        return f, None, env
    return None


def plan(parsed):
    """The files the walk could not read."""
    if parsed is None or not bypass_labels(parsed[2]):
        return []                              # nothing is guarded: no file is worth reading
    return [Need("read", p, paths.MAX_READ) for p in dict.fromkeys(parsed[0].wanted)]


def judge(parsed, answers):
    if parsed is None:
        return None
    f, rewalk, env = parsed
    bad = bypass_labels(env)
    if not bad:
        return None
    if f.wanted:
        # No file's contents lead to another read: one more walk, with every file, is the last.
        f = _Found({p: _text(answers[Need("read", p, paths.MAX_READ)]) for p in f.wanted})
        _bash(f, *rewalk, env)
    hit = next((x.casefold() for x in f.labels if x.casefold() in bad), None)
    if hit:
        return deny(say("bypass_label", guard=NAME, label=hit))
    if f.unseen:
        return deny(say("bypass_label_unseen", guard=NAME, unseen=f.unseen[0], labels=", ".join(bad)))
    return None


def check(doc):
    return (yield from planned(doc, parse, plan, judge))
