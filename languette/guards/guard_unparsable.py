"""guard-unparsable: a Bash command the parser refuses is denied, whole, before
anything in it runs.

The parser is languette/scan.py's ladder, read top down: shfmt, `bash -n`,
then the awk lexer, which refuses only a quote that never closes. The deny
names the rung that refused and what it found, with the position when the
rung gives one or a pip parser adds it, since an agent that is told only
"syntax error" guesses at the fix.

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
    found = refusal(command) if isinstance(command, str) else None
    if found:
        return deny(f"guard-unparsable: this command does not parse ({found}). Nothing ran: "
                    "bad input is a deny; fix the syntax and run it again")
    return None
