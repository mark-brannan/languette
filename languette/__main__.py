"""The `languette` command: `languette doctor` or `languette scan`; from a
clone, `python3 -m languette ...`; from a plugin install, `python3 -I
"$PLUGIN_ROOT/languette/__main__.py" ...`. `scan` is experimental: its
output may change in any release while "languette_scan" is a v0 version."""

import argparse
import json
import os
import re
import sys

if not __package__:                            # run as a file: -I leaves the plugin root off sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SCAN_VERSION = "v0.1-alpha"


def scan_doc(text, command=None):
    """The command read as the guards read it, heredoc bodies dropped:
    {"languette_scan": SCAN_VERSION, "segments": [{"nested": bool, "words":
    [{"text": str, "quoted": bool}, ...]}, ...]}, one segment for each of the
    command's own and of every nested text it runs; "quoted" marks a quoted
    word holding whitespace, its raw text. `command`, a regex, keeps only the
    segments whose command word it matches (scan.cmd_index), their words from
    that word on. Raises scan.Unparseable when the scanner will not read the
    text."""
    from languette import scan
    rx = re.compile(command) if isinstance(command, str) else command
    segments = []
    for t, nested in scan.texts_of(scan.strip_heredocs(text + "\n")):
        s = scan.Scan(t)
        for a, b in s.segments():
            if a > b:
                continue
            c = a if rx is None else scan.cmd_index(s, a, b, rx, nested)
            if c is not None:
                segments.append({"nested": nested, "words": [
                    {"text": s.q[i] if s.k[i] == "q" else s.w[i], "quoted": s.k[i] == "q"}
                    for i in range(c, b + 1)]})
    return {"languette_scan": SCAN_VERSION, "segments": segments}


def _regex(text):
    try:
        return re.compile(text)
    except re.error as e:
        raise argparse.ArgumentTypeError(f"not a regex: {e}") from None


def main(argv=None):
    p = argparse.ArgumentParser(prog="languette", description="Guards against risky actions by coding agents.")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("doctor", help="say whether languette protects Claude Code here; exits 1 on any ✗",
                   description="Say whether languette protects Claude Code on this machine, from the current "
                               "directory. Exits 1 on any ✗.")
    sc = sub.add_parser("scan", help="(experimental) read a shell command on stdin and print its segments as JSON",
                        description="Read a shell command on stdin, as the Bash tool would run it, and print one "
                                    "JSON document of the segments the guards would judge, nested texts included. "
                                    "Exits 1, printing nothing, when the scanner will not read the command. "
                                    "Experimental: the output may change in any release.")
    sc.add_argument("--command", dest="match", metavar="REGEX", type=_regex,
                    help="only segments whose command word matches REGEX, their words from that word on")
    args = p.parse_args(argv)
    if args.command == "scan":
        from languette import scan
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
        try:
            doc = scan_doc(text, args.match)
        except scan.Unparseable as e:
            print(f"languette scan: {e}", file=sys.stderr)
            return 1
        print(json.dumps(doc, indent=2))
        return 0
    from languette import doctor
    return doctor.main()


if __name__ == "__main__":
    sys.exit(main())
