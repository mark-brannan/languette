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
  and --name/-n on `gh label edit`, since a rename puts the new name on
  every issue and PR that carries the old one;
- gh api: a write whose -f/-F/--field/--raw-field key names a label (or
  `new_name` on a labels/ path), a JSON payload passed by --input (a file,
  or `-` fed by a heredoc), and a graphql mutation that applies label IDs,
  which the guard cannot map to names;
- an MCP tool's `labels` field, unless the tool's name says it reads
  (list, get, search, read).

A label the guard cannot read (built at run time, in a file it cannot open,
from stdin with no heredoc) is a deny that says why. A label named in text
(a body, a title, a commit message, a heredoc) is not a label applied: the
scanner never descends into the quoted text of a gh or git command.
"""

import json
import os
import re

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
LABEL_PATH = re.compile(r"repos/[^/]+/[^/]+/(?:issues(?:/[^/]+(?:/labels)?)?|labels/[^/]+)/?")
RENAME_PATH = re.compile(r"repos/[^/]+/[^/]+/labels/[^/]+/?")
GRAPHQL_LABELS = re.compile(r"addLabelsToLabelable|labelIds")
READ_TOOL = re.compile(r"(?:^|_)(?:list|get|search|read)(?:_|\Z)")


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
        if isinstance(v, str):
            self.labels.extend(_split(v))
        elif isinstance(v, list) and all(isinstance(x, str) or isinstance(x, dict) and isinstance(x.get("name"), str)
                                         for x in v):
            self.labels.extend(x if isinstance(x, str) else x["name"] for x in v)
        else:
            self.unseen.append(f"{what} is not a list of label names")


def _wv(s, i):
    return s.q[i] if s.k[i] == "q" else s.w[i]


def _read(path, cwd, env, moved):
    """The text of the file `path` names, as the shell will open it; raises
    Refuse, with what is wrong with the path, when the guard cannot open the
    same file."""
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
        with open(p, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise Refuse(f"cannot be read ({getattr(e, 'strerror', None) or e})")


def _payloads(src, live, ctx):
    """The JSON texts an --input value feeds gh api."""
    if live:
        raise Refuse(f"the --input path `{src}` is built at run time")
    if src == "-":
        if not ctx["bodies"]:
            raise Refuse("the --input payload comes from stdin and no heredoc in the command feeds it")
        return ctx["bodies"]
    try:
        return [_read(src, ctx["cwd"], ctx["env"], ctx["moved"])]
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
                f.unseen.append("the graphql payload applies label IDs, which the guard cannot map to names")
            continue
        try:
            doc = json.loads(t)
        except ValueError:
            if src != "-":                     # a heredoc may feed another command
                f.unseen.append(f"the --input payload `{src}` is not JSON")
            continue
        if isinstance(doc, list):
            f.names(doc, "the --input payload")
        elif isinstance(doc, dict):
            for key in ("labels", "new_name"):
                if key in doc and (key == "labels" or RENAME_PATH.fullmatch(path)):
                    f.names(doc[key], f"the --input payload's {key}")
    if src == "-" and not any(_parses(t) for t in texts) and path != "graphql":
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
            method = t[2:].upper()
        elif t in ("-f", "-F", "--field", "--raw-field"):
            fields.append((t, *nxt) if nxt else (t, "", False))
            j += 1
        elif t[:2] in ("-f", "-F") and len(t) > 2:
            fields.append((t[:2], t[2:], s.live[j]))
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
        if any(GRAPHQL_LABELS.search(v) for _, v, _ in fields):
            f.unseen.append("the graphql mutation applies label IDs, which the guard cannot map to names")
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
                f.value(_read(v[1:], ctx["cwd"], ctx["env"], ctx["moved"]).strip(), live)
            except Refuse as e:
                f.unseen.append(f"the field {key} reads the file `{v[1:]}`, which {e}")
        else:
            f.value(v, live, f"the field {key}")
    if LABEL_PATH.fullmatch(p):
        for src, live in inputs:
            _input(f, src, live, p, ctx)


def _gh(f, s, g, b, ctx):
    if g + 2 > b:
        return
    group, act = s.w[g + 1], s.w[g + 2]
    if group == "api":
        _api(f, s, g + 2, b, ctx)
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
            f.value(t[2:], s.live[j])
        j += 1


def _bash(f, cmd, cwd, env):
    text = sw.strip_heredocs(cmd + "\n")
    texts = sw.texts_of(text)
    scans = [(sw.Scan(t), nested) for t, nested in texts]
    ctx = {"cwd": cwd, "env": env, "bodies": sw.heredoc_bodies(cmd + "\n"),
           "moved": any(k == "w" and w in ("cd", "pushd", "popd") for s, _ in scans for k, w in zip(s.k, s.w))}
    for s, nested in scans:
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, GH, nested)
            if g is not None:
                _gh(f, s, g, b, ctx)


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
        if not isinstance(inp, dict) or "labels" not in inp or READ_TOOL.search(tool.rsplit("__", 1)[-1]):
            return None
        f.names(inp["labels"], "the labels field")
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
