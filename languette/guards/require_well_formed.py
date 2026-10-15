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
from languette.messages import say
from languette.verdict import deny

NAME = "require-well-formed"


def check(doc):
    """The deny for the Bash command, or None when it reads. The ladder runs
    once per call, in the document: a timeout or a kill need not repeat, and
    run.py drops the other guards on this same reading."""
    e = doc.refusal
    if isinstance(e, scan.TooMany):
        return deny(say("too_many", err=e))
    if isinstance(e, scan.TooBig):
        return deny(say("too_deep", err=e))
    if e is not None:
        return deny(say("unparsed", rung=e.rung, err=e))
    return None
