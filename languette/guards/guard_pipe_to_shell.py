"""guard-pipe-to-shell: the Python guard (it replaced
hooks/guard-pipe-to-shell.sh).

Blocks a download that is run as it arrives: curl, wget or fetch piped into
an interpreter that reads its program from stdin (`curl u | sh`, `| sudo bash
-s`, `| python3 -`), a download handed over as a file (`sh <(curl u)`,
`source <(curl u)`) and a download handed over as text (`eval "$(curl u)"`,
`bash -c "$(curl u)"`). An interpreter given a script of its own (`| python3 -c
...`, `| node -e ...`, `| sh install.sh`) is not reading the download as code.
"""

import json
import os
import re

from languette import scan as sw
from languette.verdict import deny

NAME = "guard-pipe-to-shell"

_DL = re.compile(r"(?:^|/)(?:curl|wget|fetch)\Z")
_INTERP = re.compile(r"(?:^|/)(?:sh|bash|dash|zsh|ksh|ash|fish|python[0-9.]*|perl[0-9.]*|node|ruby)\Z")
_SHELLS = re.compile(r"(?:sh|bash|dash|zsh|ksh|ash|fish)\Z")
_FED = ("(", "`")

# family -> (letters that mean "the program is given", options that take a value)
_NODE_SCRIPT = ("-e", "--eval", "-p", "--print", "-pe", "-ep", "-c", "--check")
_VALUE_OPTS = {"sh": ("-o", "-O", "+o", "+O", "--rcfile", "--init-file"), "python": ("-W", "-X"),
               "perl": ("-I",), "ruby": ("-I", "-r"), "node": ("-r", "--require", "--import", "--loader")}

_WAY_OUT = ("Download it to a file, read it, then run the file: `curl -fsSLo install.sh <url>`, read "
            "install.sh, `sh install.sh`. The same install, one more command, and the script has been "
            "seen before it ran.")


def _family(path):
    name = os.path.basename(path)
    return ("sh" if _SHELLS.fullmatch(name) else "python" if name.startswith("python") else
            "perl" if name.startswith("perl") else name)


def _program(s, g, b):
    """How the interpreter at g gets its program: (script_given, operands),
    where script_given means a -c, -e or -m the interpreter runs instead of
    stdin, and operands are the words that are neither options nor their values."""
    fam, given, ops = _family(s.w[g]), False, []
    i = g + 1
    while i <= b:
        x, at, i = s.w[i], i, i + 1
        if s.k[at] != "w":
            ops.append(x)
        elif x == "--":
            ops += s.w[i:b + 1]
            break
        elif x in _VALUE_OPTS.get(fam, ()):
            i += 1
        elif x == "-" or (len(x) > 1 and x[0] in "-+"):
            if fam == "node":
                given = given or x in _NODE_SCRIPT
            elif re.fullmatch(r"-[A-Za-z]+", x) and not (fam == "perl" and x[1] in "MmIiFd"):
                given = given or any(ch in x for ch in {"sh": "c", "python": "cm", "perl": "eE", "ruby": "e"}[fam])
        else:
            ops.append(x)
    return given, ops


def _reads_stdin(s, g, b):
    """The interpreter at g takes its program from stdin: no -c/-e/-m, and no
    script operand (a lone `-` is stdin)."""
    given, ops = _program(s, g, b)
    if _family(s.w[g]) == "sh":
        stdin_flag = any(re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", w) for w in s.w[g + 1:b + 1])
        return not given and (stdin_flag or not ops)
    return not given and (not ops or ops[0] == "-")


def _has_dl(s, a, b, nested):
    return sw.cmd_index(s, a, b, _DL, nested) is not None


def _text_downloads(raw):
    """A quoted word's text runs a download inside a substitution."""
    if "$(" not in raw and "`" not in raw:
        return False
    s = sw.Scan(raw)
    return any(a <= b and _has_dl(s, a, b, False) for a, b in s.segments())


def _judge(s, nested):
    """The reason this scanned text is a pipe-to-shell, or None."""
    segs = {a: b for a, b in s.segments() if a <= b}
    carried = False
    for a, b in sorted(segs.items()):
        sep = s.op[a - 1] if a > 0 else ""
        if "|" not in sep.replace("||", "").replace("&&", ""):
            carried = False
        c = sw.seg_cmd(s, a, b)
        g = sw.cmd_index(s, a, b, _INTERP, nested)
        fed = (b + 1 < len(s.w) and s.op[b + 1].startswith(_FED)
               and (b + 2 in segs and _has_dl(s, b + 2, segs[b + 2], nested)))
        if g is not None:
            name = os.path.basename(s.w[g])
            if carried and _reads_stdin(s, g, b):
                return f"a download piped into `{name}`"
            given, ops = _program(s, g, b)
            if fed and (given or not ops):
                return f"`{name}` run on a download substituted into its command line"
            if given and any(s.k[i] == "q" and _text_downloads(s.q[i]) for i in range(g + 1, b + 1)):
                return f"`{name} -c` run on a download substituted into its command line"
        if c is not None and s.w[c] == "eval":
            if fed or any(s.k[i] == "q" and _text_downloads(s.q[i]) for i in range(c + 1, b + 1)):
                return "`eval` of a download"
        if c is not None and s.w[c] in ("source", ".") and fed and len(s.w[c + 1:b + 1]) == 0:
            return f"`{s.w[c]}` of a download"
        if _has_dl(s, a, b, nested):
            carried = True
    return None


def check(payload, env=os.environ):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if cmd is None or cmd is False:
        return None
    if not isinstance(cmd, str):
        cmd = json.dumps(cmd)                  # as `jq -r` would print it
    cmd = cmd.rstrip("\n")                     # as $(...) would leave it
    if not cmd:
        return None
    for text, nested in sw.texts_of(sw.strip_heredocs(cmd + "\n")):
        why = _judge(sw.Scan(text), nested)
        if why:
            return deny(f"guard-pipe-to-shell: {why} runs whatever the server sends, unread. {_WAY_OUT}")
    return None
