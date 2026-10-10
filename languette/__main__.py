"""The `languette` command: `languette doctor`, or `python3 -m languette doctor` from a clone."""

import argparse
import sys


def main(argv=None):
    p = argparse.ArgumentParser(prog="languette", description="Guards against risky actions by coding agents.")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("doctor", help="say whether languette protects Claude Code here; exits 1 on any ✗",
                   description="Say whether languette protects Claude Code on this machine, from the current "
                               "directory. Exits 1 on any ✗.")
    p.parse_args(argv)
    from languette import doctor
    return doctor.main()


if __name__ == "__main__":
    sys.exit(main())
