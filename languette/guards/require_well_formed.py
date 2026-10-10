"""require-well-formed: a Bash command the parser refuses is denied, whole, before
anything in it runs.

The parser is languette/scan.py's ladder, read top down: shfmt, `bash -n`,
then the awk lexer, which refuses only a quote that never closes. The deny
names the rung that refused and what it found, with the position when the
rung gives one or a pip parser adds it, since an agent that is told only
"syntax error" guesses at the fix. A command over the size or nesting limit
(scan.TooBig) is denied before any rung reads it, with what to change, and
so is one holding more nested shell strings than the guards read
(scan.TooMany): the guards would pass the ones past the cap unread.

The other guards skip a command that does not parse (run.py), rather than
deny it a second time on a weaker reading.
"""

from languette import scan
from languette.verdict import deny

NAME = "require-well-formed"


def check(doc):
    """The deny for the Bash command, or None when it reads. The ladder runs
    once per call, in the document: a timeout or a kill need not repeat, and
    run.py drops the other guards on this same reading."""
    e = doc.refusal
    if isinstance(e, scan.TooMany):
        return deny(f"require-well-formed: this command is too big to check: {e}. Nothing ran. "
                    "Every quoted string that may run as shell, and every $( ) inside double quotes, "
                    "is one; the guards read only so many. Split it into several smaller commands, "
                    "or put the script in a file and run that")
    if isinstance(e, scan.TooBig):
        return deny(f"require-well-formed: this command is too big to check: {e}. Nothing ran. "
                    "Every $( ), ( ), { }, backtick, if, case and do adds the depth it stands at, "
                    "and so does every &&, || and | (a chain nests one level per operator). "
                    "Split it into several smaller commands, or nest less")
    if e is not None:
        return deny(f"require-well-formed: this command does not parse ({e.rung}: {e}). Nothing ran: "
                    "bad input is a deny; fix the syntax and run it again")
    return None
