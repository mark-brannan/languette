"""Command rules (docs/design/guard-rules.md, "Command rules"): loading a
guard's rules and matching a rule against the command's words.
"""

import re

from .quoting import UNREADABLE, _ASSIGN
from .lexicon import (basename, EXEC, LAUNCH, LAUNCH_SUB, LOOP, PM, PROSE_PROCESS, RUN, WRAP, _FIND_EXECS,
                      _FIND_WRAPPERS)
from .texts import cmd_index, segments
from .cd_tracking import cd_present, cwds, _abspath
from .stops import stop_of, unit_test


# Command rules: docs/design/guard-rules.md, "Command rules". A rule's match is
# a command word (`cmd`, by basename) and any of: `args`, a run of its
# non-option words; `script`, a later word that is it or ends in `/script`;
# `flags`, short option letters each present in a short-option cluster;
# `at: "command"`, the word only where it runs, never as another command's operand;
# `except`, words any one of which, as a whole argument of the segment, exempts the run.
_CLUSTER = re.compile(r"-[A-Za-z]+")


def _run_of(words, a):
    """Is `a` a contiguous run inside `words`?"""
    return any(words[i:i + len(a)] == a for i in range(len(words) - len(a) + 1))


def _script_word(w, sc, place):
    """Is word `w` the listed script `sc`? It is when it reads as `sc` or ends in `/sc`; with
    `place`, (the directories the word may run in, the root `sc` is written from), also when
    it resolves there to the script. Where a directory is unknown (None), or the word is
    live, any word naming the script's file may be it, so it is."""
    if w == sc or w.endswith("/" + sc):
        return True
    if place is None:
        return False
    here, root = place
    want, name = _abspath(root + "/" + sc), basename(sc)
    if UNREADABLE.search(w) or w.startswith("~"):
        return basename(w) == name
    if w.startswith("/"):
        return _abspath(w) == want
    return any(_abspath(h + "/" + w) == want if h else basename(w) == name for h in here)


def _hit(match, name, rest, place=None):
    """Does match fit command word `name` followed by words `rest`? `place`: _script_word's."""
    words = [w for w in rest if not w.startswith("-")]
    cmd = match["cmd"]
    if name in PM:
        words = ["run" if w in RUN else w for w in words]
    if name != cmd and not (cmd in PM and name in PM):
        if name in LAUNCH:
            if words and words[0] in LAUNCH_SUB:
                words = words[1:]
            # The first word naming cmd: an option's value (npx -p x cmd) may come first.
            w = next((w for w in words if basename(w) == cmd), None)
            if w is not None:
                return _hit(match, cmd, rest[rest.index(w) + 1:], place)
        return False
    if any(w in match.get("except", ()) for w in rest):
        return False
    ok = True
    if "args" in match:
        a = match["args"]
        ok = _run_of(words, a) or (name in PM - {"npm"} and a[0] == "run" and len(a) > 1 and _run_of(words, a[1:]))
    if ok and "script" in match:
        sc = match["script"]
        while sc.startswith("./"):
            sc = sc[2:]
        ok = any(_script_word(w, sc, place) for w in rest)
    if ok and "flags" in match:
        held = {c for w in rest if _CLUSTER.fullmatch(w) for c in w[1:]}
        ok = all(f in held for f in match["flags"])
    return ok


class BadRules(ValueError):
    """A rule set that does not load; the message names the fault."""


_MATCH_KEYS = ("args", "cmd", "flags", "script")
# A match ask-first reads: `except` too, the words that exempt a run, as a usage flag does.
ASK_MATCH_KEYS = (*_MATCH_KEYS, "except")
# A match the rules engine reads (languette/engine.py): `at` too, and `cmd` alone is the whole program.
ENGINE_MATCH_KEYS = (*_MATCH_KEYS, "at")
# A shipped rule set's: a stop of a unit too (stop_of), which no tier but the shipped one may say.
SHIPPED_MATCH_KEYS = (*ENGINE_MATCH_KEYS, "program", "unit", "verbs", "host_verbs", "test")


def _listed(v, what, each=r".+", of="non-empty strings"):
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and re.fullmatch(each, x) for x in v):
        raise BadRules(f"{what} must be a non-empty list of {of}")


def _check_match(m, w, keys=_MATCH_KEYS):
    if not isinstance(m, dict) or set(m) - set(keys):
        raise BadRules(f"{w} must be an object holding only {', '.join(keys)}")
    if "test" in m:                            # a named test (primitives.TESTS) stands alone
        if set(m) != {"test"} or not isinstance(m["test"], str):
            raise BadRules(f"{w}.test must be a test's name, alone in its entry")
        return
    cmds = m["cmd"] if isinstance(m.get("cmd"), list) and m["cmd"] and "unit" in m else [m.get("cmd")]
    if not all(isinstance(c, str) and re.fullmatch(r"[A-Za-z0-9._+-]+", c) for c in cmds):
        raise BadRules(f"{w}.cmd must be a bare command name")
    if "at" not in keys and not {"args", "script", "flags"} & set(m):
        raise BadRules(f"{w} needs args or script (or flags), or it would match every {m['cmd']}")
    if "at" in m and m["at"] != "command":
        raise BadRules(f'{w}.at must be "command"')
    if "args" in m:
        _listed(m["args"], f"{w}.args")
    if "flags" in m:
        _listed(m["flags"], f"{w}.flags", r"[A-Za-z]", "single option letters")
    if "except" in m:
        _listed(m["except"], f"{w}.except", r"\S+", "whole words")
    if "script" in m and (not isinstance(m["script"], str) or not m["script"].strip("./")):
        raise BadRules(f"{w}.script must be a non-empty path")


def load_rules(cfg, key, keys=(), check=None, many=False, taken=(), nonempty=False, match_keys=_MATCH_KEYS):
    """The one loader of command rules: the rules of `cfg[key]`, a read rule file, or BadRules
    naming the fault. A rule is an object with an `id` (unique, and not one of `taken`), a
    `match` and the other `keys` the guard names; `check(rule, where)` is the guard's own test
    of one rule. `match` is one entry, or with `many` a list of them; an entry is checked here,
    against `match_keys` (ENGINE_MATCH_KEYS for the rules engine's)."""
    if not isinstance(cfg, dict) or set(cfg) != {key} or not isinstance(cfg[key], list) or (nonempty and not cfg[key]):
        raise BadRules(f'the top level must be {{"{key}": [...]}}' + (" with at least one rule" if nonempty else ""))
    seen = set(taken)
    for n, r in enumerate(cfg[key]):
        where = f"{key}[{n}]"
        if not isinstance(r, dict):
            raise BadRules(f"{where} is not an object")
        if set(r) - {"id", "match", *keys}:
            raise BadRules(f"{where} has keys a rule does not: {', '.join(sorted(set(r) - {'id', 'match', *keys}))}")
        if not isinstance(r.get("id"), str) or not r["id"].strip():
            raise BadRules(f"{where}.id must be a non-empty string")
        if r["id"] in seen:
            tail = " is a default's; a rule set adds rules, it never replaces one" if r["id"] in taken else " is a duplicate"
            raise BadRules(f"{where}.id '{r['id']}'{tail}")
        seen.add(r["id"])
        if check:
            check(r, where)
        m = r.get("match")
        if not many:
            _check_match(m, f"{where}.match", match_keys)
        elif not isinstance(m, list) or not m:
            raise BadRules(f"{where}.match must be a non-empty list")
        else:
            for i, e in enumerate(m):
                _check_match(e, f"{where}.match[{i}]", match_keys)
    return cfg[key]


# Programs that run a command they are given: past one of these, `at: "command"` reads every
# later word as it would without `at`, since where their command starts is theirs to say.
_RUNS_A_COMMAND = EXEC | WRAP | LOOP | LAUNCH | _FIND_WRAPPERS | frozenset(
    "setsid ionice stdbuf chroot flock strace ltrace unshare nsenter runuser chrt taskset "
    "setpriv systemd-run fakeroot unbuffer sg capsh bwrap firejail proxychains torsocks caffeinate cgexec".split())


def _placed_index(s, a, b, rx):
    """Index in a..b of the word `rx` describes where it runs: the command word, past
    assignments, or once that word is a program that runs a command, any later word."""
    i = a
    while i <= b and s.k[i] == "w" and _ASSIGN.match(s.w[i]):
        i += 1
    if i > b or s.k[i] != "w":
        return None
    if rx.search(s.w[i]):
        return i
    if basename(s.w[i]) == "find":                # find's -exec and kin start a command of their own
        return next((j for k in range(i + 1, b) if s.k[k] == "w" and s.w[k] in _FIND_EXECS
                     for j in [_placed_index(s, k + 1, b, rx)] if j is not None), None)
    if basename(s.w[i]) not in _RUNS_A_COMMAND:
        return None
    return next((j for j in range(i + 1, b + 1) if s.k[j] == "w" and rx.search(s.w[j])), None)


def _word_hit(doc, match, prose, launchers, at=None):
    """(how many times the command runs `match`, whether any text holds a LOOP word). With
    `at: "command"`, a word another command takes as its argument does not count (_placed_index).
    With `at`, (the directory the command starts in, or None, the root a `script` is written
    from), a word is resolved where it runs (cwds): the start, moved by the text's cd; a
    nested text starts there only when no outer text moves."""
    placed = match.get("at") == "command"
    launchers = launchers and not placed
    names = {match["cmd"]} | (LAUNCH if launchers else set()) | (PM if match["cmd"] in PM else set())
    rx = re.compile(r"(?:^|/)(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\Z")
    n, (segs, loop) = 0, segments(doc, prose)
    places = {}
    if at is not None and "script" in match:
        (cwd, root), env = at, doc.env
        cwd = _abspath(cwd) if isinstance(cwd, str) and cwd.startswith("/") else None
        moved = any(cd_present(s) for s, _, _, nested in segs if not nested)
        cdpath = bool(env.get("CDPATH")) or any("CDPATH=" in w for s, *_ in segs for w in s.w)
        for s, _, _, nested in segs:
            if id(s) not in places:
                start = None if nested and moved else cwd
                places[id(s)] = cwds(s, start, env.get("HOME"), cdpath)
    for s, a, b, nested in segs:
        place = (places[id(s)][a], root) if places else None
        nested = nested or placed
        g = _placed_index(s, a, b, rx) if placed else cmd_index(s, a, b, rx, nested, prose=prose)
        # cmd_index stops at the first launcher; a later word may be the command.
        while g is not None:
            if _hit(match, basename(s.w[g]), s.w[g + 1:b + 1], place):
                n += 1
                break
            if nested:
                break
            g = next((i for i in range(g + 1, b + 1) if s.k[i] == "w" and rx.search(s.w[i])), None)
    return n, loop


def _stop_hit(doc, match, prose):
    """`<command> <stop>` for the first command in the text that `match` fits, or None."""
    hit = unit_test(match["unit"])
    if hit is None:
        return None
    for t, _ in doc.texts(prose):
        s = doc.scan(t)
        for a, b in s.segments():
            got = a <= b and stop_of(s, a, b, match, hit, match.get("host_verbs", ()))
            if got:
                return " ".join(got)
    return None


def match_rule(doc, match, prose=PROSE_PROCESS, launchers=True, at=None):
    """The one matcher of command rules: (how many times the command runs `match`, whether any
    text holds a LOOP word, what it did, as the segment reads: `<command> <stop>`, or None). A
    match with a `unit` is a stop on a unit the condition accepts (stop_of), counted once;
    any other is a command word and its words (_hit). `prose` names the commands whose words
    are not commands; launchers (npx, `pnpm exec`) run `cmd` unless `launchers` is False. With
    `at`, (start directory, root), a `script` is the file at root/script wherever the command
    runs it from (_word_hit)."""
    if "unit" in match:
        said = _stop_hit(doc, match, prose)
        return (1 if said else 0), False, said
    n, loop = _word_hit(doc, match, prose, launchers, at)
    return n, loop, None
