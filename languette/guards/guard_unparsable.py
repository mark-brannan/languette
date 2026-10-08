"""guard-unparsable: a Bash command the parser refuses is denied, whole, before
anything in it runs.

The parser is languette/scan.py's ladder, read top down: shfmt, `bash -n`,
then the awk lexer, which refuses only a quote that never closes. The deny
names the rung that refused and what it found, with the position when the
rung gives one or a pip parser adds it, since an agent that is told only
"syntax error" guesses at the fix. A command over the size or nesting limit
(scan.TooBig) is denied before any rung reads it, with what to change.

The other guards skip a command that does not parse (run.py), rather than
deny it a second time on a weaker reading.
"""

from languette import scan
from languette.verdict import deny

NAME = "guard-unparsable"


def refusal(command):
    """What the ladder's top rung on hand found wrong with `command`, or None
    when it reads."""
    try:
        scan.check(command)
    except scan.Unparseable as e:
        return f"{e.rung}: {e}"
    return None


def check(payload, env):
    ti = payload.get("tool_input")
    command = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(command, str):
        return None
    try:
        scan.check(command)
    except scan.TooBig as e:
        return deny(f"guard-unparsable: this command is too big to check: {e}. Nothing ran. "
                    "Every $( ), ( ), { }, backtick, if, case and do adds the depth it stands at, "
                    "and so does every &&, || and | (a chain nests one level per operator). "
                    "Split it into several smaller commands, or nest less")
    except scan.Unparseable as e:
        return deny(f"guard-unparsable: this command does not parse ({e.rung}: {e}). Nothing ran: "
                    "bad input is a deny; fix the syntax and run it again")
    return None
