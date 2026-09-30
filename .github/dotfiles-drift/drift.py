#!/usr/bin/env python3
"""Keep the copied guards honest against their source in mark-brannan/dotfiles.

languette's copies are deliberately not byte-equal to dotfiles': house
material was stripped. "Equal" therefore means: the dotfiles file on main,
with the reviewed edits in edits/<name>.edits applied, is byte-for-byte the
languette file. An edit names the dotfiles lines it replaces by line range and
sha256, never by content, so the stripped text does not come back in here.

  drift.py check [--source DIR]   fail, with the diff, when either side moved
  drift.py regen [--source DIR]   rewrite every edits file from the current
                                  files; review the result, then commit it

--source DIR reads dotfiles files from DIR/<path> (a local checkout) instead
of raw.githubusercontent.com; nothing is written there.
"""
import difflib, hashlib, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BASE = os.environ.get("DRIFT_BASE", "https://raw.githubusercontent.com/mark-brannan/dotfiles/main")


def read_map():
    pairs = []
    for line in open(os.path.join(HERE, "map.txt"), encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            ours, theirs = line.split()
            pairs.append((ours, theirs))
    return pairs


def fetch(theirs, source):
    if source:
        return open(os.path.join(source, theirs), "rb").read()
    err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(BASE + "/" + theirs, timeout=30) as r:
                return r.read()
        except Exception as e:  # network blips must not read as drift
            err = e
            time.sleep(2 * (attempt + 1))
    sys.exit("cannot fetch %s/%s: %s" % (BASE, theirs, err))


def lines(data):
    out = data.splitlines(keepends=True)
    if out and not out[-1].endswith(b"\n"):
        sys.exit("a file without a trailing newline is not supported by the edit format")
    return out


def sha(ls):
    return hashlib.sha256(b"".join(ls)).hexdigest()


def edits_path(ours):
    return os.path.join(HERE, "edits", os.path.basename(ours) + ".edits")


def parse_edits(path):
    hunks, cur = [], None
    for raw in open(path, "rb").read().splitlines(keepends=True):
        if raw.startswith(b"#"):
            continue
        if raw.startswith(b"@@ -"):
            rng, digest = raw[4:].decode().split()
            start, _, count = rng.partition(",")
            cur = [int(start) - 1, int(count), digest.split(":", 1)[1], []]
            hunks.append(cur)
        elif raw.startswith(b"+") and cur is not None:
            cur[3].append(raw[1:])
        else:
            sys.exit("%s: unreadable line %r" % (path, raw))
    return hunks


def apply(theirs_lines, hunks):
    """Returns (result lines, [(start, count, current lines) for each hunk whose hash moved])."""
    out, pos, moved = [], 0, []
    for start, count, digest, repl in hunks:
        if start < pos:
            sys.exit("overlapping hunks")
        out += theirs_lines[pos:start]
        cur = theirs_lines[start:start + count]
        if sha(cur) != digest:
            moved.append((start + 1, count, cur))
        out += repl
        pos = start + count
    return out + theirs_lines[pos:], moved


def udiff(a, b, la, lb):
    t = lambda ls: [l.decode("utf-8", "replace") for l in ls]
    return "".join(difflib.unified_diff(t(a), t(b), la, lb))


def check(source):
    pairs = read_map()
    bad = 0
    mapped = {ours for ours, _ in pairs}
    for f in sorted(os.listdir(os.path.join(ROOT, "hooks"))):
        if f != "hooks.json" and "hooks/" + f not in mapped:
            print("UNMAPPED: hooks/%s is not in .github/dotfiles-drift/map.txt" % f)
            bad += 1
    nh = 0
    for ours, theirs in pairs:
        d = lines(fetch(theirs, source))
        mine = lines(open(os.path.join(ROOT, ours), "rb").read())
        hunks = parse_edits(edits_path(ours))
        nh += len(hunks)
        got, moved = apply(d, hunks)
        if moved:
            bad += 1
            print("DRIFT: dotfiles moved under %s (%s)" % (ours, theirs))
            for start, count, cur in moved:
                print("  the reviewed edit covered lines %d-%d; dotfiles main now has:" % (start, start + count - 1))
                print("".join("    | " + l.decode("utf-8", "replace") for l in cur), end="")
        elif got != mine:
            bad += 1
            print("DRIFT: %s is not dotfiles main + its reviewed edits. Diff (dotfiles main + edits -> languette):" % ours)
            print(udiff(got, mine, "dotfiles/" + theirs, ours))
    if bad:
        print("\n%d file(s) drifted. If dotfiles changed, port the change into languette; if languette changed on" % bad)
        print("purpose, it is a fork now. Either way run `.github/dotfiles-drift/drift.py regen`, review the")
        print("edits diff, and commit it (or make the two match again).")
        sys.exit(1)
    print("ok: %d files equal dotfiles main after %d reviewed hunks" % (len(pairs), nh))


def regen(source):
    os.makedirs(os.path.join(HERE, "edits"), exist_ok=True)
    for ours, theirs in read_map():
        d = lines(fetch(theirs, source))
        mine = lines(open(os.path.join(ROOT, ours), "rb").read())
        body = b""
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, d, mine, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            body += b"@@ -%d,%d sha256:%s\n" % (i1 + 1, i2 - i1, sha(d[i1:i2]).encode())
            body += b"".join(b"+" + l for l in mine[j1:j2])
        head = b"# %s (dotfiles) -> %s. Each hunk replaces the named dotfiles lines\n# (sha256-checked) with the + lines; nothing else differs.\n" % (theirs.encode(), ours.encode())
        open(edits_path(ours), "wb").write(head + body if body else head)
    print("edits rewritten; running the check")
    check(source)


if __name__ == "__main__":
    args = sys.argv[1:]
    source = None
    if "--source" in args:
        i = args.index("--source")
        source = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or args[0] not in ("check", "regen"):
        sys.exit(__doc__)
    (check if args[0] == "check" else regen)(source)
