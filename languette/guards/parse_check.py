"""parse-check: a Bash command the parser refuses is denied, whole, before
anything in it runs.

The parser is the top rung of languette/scan.py's ladder (shfmt). Without it,
`bash -n` reads the command instead: it runs nothing, and says less. The deny
carries the parser's position and what it found, since an agent that is told
only "syntax error" guesses at the fix.

The other guards skip a command that does not parse (run.py), rather than
deny it a second time on a weaker reading.
"""

import os
import re
import subprocess

from languette import scan
from languette.verdict import deny

NAME = "parse-check"
BASH_TIMEOUT = 2                               # seconds


def refusal(command):
    """What the parser found wrong with `command`, or None when it parses
    (or no parser could read it)."""
    try:
        rung, _ = scan.parse(command)
    except scan.Unparseable as e:
        return f"shfmt: {e}"
    if rung == "shfmt":
        return None
    try:
        r = subprocess.run(["bash", "-n"], input=command.encode("utf-8", "surrogatepass"), capture_output=True,
                           timeout=BASH_TIMEOUT, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    except (OSError, subprocess.SubprocessError):
        return None                            # no bash -n: the awk rung's reading, which denies no parse

    if r.returncode == 0:
        return None
    err = r.stderr.decode("utf-8", "replace").strip().splitlines()
    return "bash -n: " + re.sub(r"^(?:\S*bash: )+", "", err[0]) if err else "bash -n: syntax error"


def check(payload, env):
    ti = payload.get("tool_input")
    command = ti.get("command") if isinstance(ti, dict) else None
    found = refusal(command) if isinstance(command, str) else None
    if found:
        return deny(f"parse-check: this command does not parse ({found}). Nothing ran: "
                    "bad input is a deny; fix the syntax and run it again")
    return None
