"""Path words, as the guards that judge a target path share them: resolve one
word of a command to a single absolute path, or say why it cannot be one; the
agent's own areas. What the disk says about a path is a Need("physical", p),
which a guard plans and the runner answers. Standard library only."""

import json
import os
import re

from languette import scan as sw
from languette.messages import say
from languette.verdict import Need, Refuse, context, deny, planned

MAX_READ = 1 << 20                             # bytes a read Need may return


class Unresolved(Exception):
    """A word that cannot be resolved to one path; str() says what the guard saw."""


def normalize(p):
    """Collapse "." segments and duplicate slashes. `..` is never passed in."""
    out = "".join("/" + s for s in p.split("/") if s not in ("", "."))
    return out or "/"


def lexical(p):
    """normalize, with `..` applied as text (the filesystem is not consulted)."""
    parts = []
    for s in p.split("/"):
        if s in ("", "."):
            continue
        if s == "..":
            if parts:
                parts.pop()
            continue
        parts.append(s)
    return "/" + "/".join(parts)


def resolve(word, quoted, cwd, home, moved):
    """One word of a command, as the absolute path it names, or Unresolved."""
    t = word
    if quoted:
        raise Unresolved(say("rd_quoted_space"))
    if re.search(r"[*?\[{}]", t):
        raise Unresolved(say("rd_glob"))
    if re.search(r"[$`]", t):
        raise Unresolved(say("rd_substitution"))
    if re.search(r"[\t\n\r]", t):
        raise Unresolved(say("rd_tab_newline"))
    if t == ".." or re.search(r"(?:^|/)\.\.(?:/|\Z)", t):
        raise Unresolved(say("rd_dotdot"))
    if "~" in t:
        if t == "~":
            t = home
        elif t.startswith("~/"):
            t = home + t[1:]
        else:
            raise Unresolved(say("rd_tilde"))
    if not t.startswith("/"):
        if moved:
            raise Unresolved(say("rd_cd_moved"))
        t = cwd + "/" + t
    return normalize(t)


def resolve_target(word, quoted, cwd, home, moved):
    """resolve, for a guard that judges a target: `/` and $HOME itself are Unresolved too."""
    t = resolve(word, quoted, cwd, home, moved)
    if t == "/":
        raise Unresolved(say("rd_root"))
    if t == normalize(home):
        raise Unresolved(say("rd_home"))
    return t


_ALLOW_CHARS = re.compile(r"[A-Za-z0-9._@+/-]*")


def parse_allow(value, home, home_p, physical, bare_names=False):
    """An allow var -> (roots, names, error or None): absolute paths, and with
    `bare_names` directory names too. `physical` resolves each path entry
    through the disk."""
    roots, names = [], []
    for ent in value.split(":"):
        if ent == "":
            return roots, names, "an empty entry"
        if not _ALLOW_CHARS.fullmatch(ent):
            return roots, names, f"unsupported character in '{ent}'"
        if ent.startswith("/"):
            if ent.endswith(("/.", "/..")) or "/./" in ent or "/../" in ent or "//" in ent:
                return roots, names, f"'{ent}' has an empty, . or .. segment"
            if ent.endswith("/"):
                ent = ent[:-1]
            if ent in ("", home):
                return roots, names, f"'{ent}' is / or $HOME"
            ent_p = physical(ent)
            if ent_p in ("", home, home_p):
                return roots, names, f"'{ent}' resolves to / or $HOME"
            roots += [ent, ent_p]
        elif not bare_names:
            return roots, names, f"'{ent}' is not an absolute path"
        elif "/" in ent:
            return roots, names, f"'{ent}' is neither a bare name nor an absolute path"
        elif ent in (".", ".."):
            return roots, names, f"'{ent}' is not a name"
        else:
            names.append(ent)
    return roots, names, None


def host_tmp_roots(env):
    """Where the host keeps its scratch directories: its temporary directory
    (CLAUDE_CODE_TMPDIR), else the system's (TMPDIR), else /tmp."""
    named = [d.rstrip("/") for d in (env.get("CLAUDE_CODE_TMPDIR"), env.get("TMPDIR")) if d and d.startswith("/")]
    return [d for d in dict.fromkeys(named) if d] + ["/tmp"]


def own_bases(env, cwd):
    """Where the agent works and nothing of the user's lives, as written: /tmp,
    the host's scratch roots, and the host's worktree directory,
    <project>/.claude/worktrees, for the project the host names (CLAUDE_PROJECT_DIR)
    and for the one the session stands in when it runs inside a worktree. What
    the host names is judged in own_roots."""
    proj = (env.get("CLAUDE_PROJECT_DIR") or "").rstrip("/")
    i = cwd.find("/.claude/worktrees/")
    wt = ([proj + "/.claude/worktrees"] if proj.startswith("/") else []) + ([cwd[:i] + "/.claude/worktrees"] if i >= 0 else [])
    return list(dict.fromkeys(["/tmp"] + host_tmp_roots(env) + wt))


def own_roots(home, bases, physical, extra=()):
    """own_bases, as written and as the filesystem has them (/tmp is
    /private/tmp on macOS); `physical` maps a path to its physical answer.
    A base the host names is dropped when it is empty, /, $HOME or holds $HOME,
    as written or as the filesystem has it: a link to $HOME is not the agent's
    own. A base's physical form counts only as an alias of that base, and only when
    its last segment is not itself a link (its parents may be: /tmp is /private/tmp),
    else a link the agent makes would turn any directory into its own. /tmp is the
    agent's own wherever $HOME lies."""
    homes = {home, physical(home)}

    def fits(p, tmp):
        return p not in ("", "/") and p not in homes and (tmp or not any(h.startswith(p + "/") for h in homes))
    roots = []
    for b in bases:
        tmp = b == "/tmp"
        if fits(b, tmp):
            p = physical(b)
            keep = tmp or p == physical(os.path.dirname(b)) + "/" + os.path.basename(b)
            roots += [b] + [p for p in (p,) if keep and fits(p, tmp)]
    return roots + list(extra)


def base_needs(bases):
    """The paths own_roots asks the disk about: each base and its directory."""
    return [p for b in bases for p in (b, os.path.dirname(b))]


def physical_of(answers):
    """Path -> its planned Need("physical") answer. One the world could not
    have is raised."""
    def physical(p):
        got = answers[Need("physical", p)]
        if isinstance(got, Exception):
            raise got
        return got
    return physical


def under(p, roots):
    return any(p == r or p.startswith(r + "/") for r in roots)


_CHDIR_WRAP = re.compile(r"(?:^|/)(?:sudo|doas|env)\Z")
# env -C, sudo -D and sudo -R (a chroot: `.` is somewhere else there too), in every spelling getopt
# takes: detached, attached (-C/etc), clustered (-nD /etc), and a long option or any prefix of it.
_CHDIR_OPT = re.compile(r"-[A-Za-z]*[CDR].*|--c(?:h(?:d(?:ir?)?|r(?:o(?:ot?)?)?)?)?(?:=.*)?")
# Options of env, sudo and doas that take the next word as their value.
_VALUE_LETTERS = "uSghprtTU"
_VALUE_LONG = ("unset", "split-string", "close-from", "group", "host", "prompt", "role", "type",
               "command-timeout", "user", "other-user")


def chdir_wrapper(s, a, b):
    """A wrapper that runs its command in another directory: `env -C dir`, `sudo -D dir`, `sudo -R dir`.
    Only the wrapper's own options are read, up to the command it runs, so that command's own -R is
    not taken for one. A wrapper option this does not know errs toward True, which only denies a
    relative path."""
    for i in range(a, b + 1):
        if s.k[i] != "w" or not _CHDIR_WRAP.search(s.w[i]):
            continue
        value = False
        for j in range(i + 1, b + 1):
            x = s.w[j]
            if s.k[j] != "w":
                break
            if _CHDIR_OPT.fullmatch(x):
                return True
            if x.startswith("--") and len(x) > 2:
                value = "=" not in x and any(o.startswith(x[2:]) for o in _VALUE_LONG)
            elif x.startswith("-") and len(x) > 1:
                value = x[-1] in _VALUE_LETTERS
            elif value or sw._ASSIGN.match(x):
                value = False
            else:
                break
    return False


def moves_directory(scans):
    """True when some segment of some scanned text is a cd, pushd or popd, or a
    wrapper with a chdir option: every relative path in the command is then
    unresolvable."""
    return any(a <= b and (sw.cmd_index(s, a, b, sw.CD, True) is not None or chdir_wrapper(s, a, b))
               for s, _ in scans for a, b in s.segments())


def find_starts(s, g, b):
    """The start paths of the `find` at word g: every word before its first option or test."""
    i = g + 1
    while i <= b and not s.w[i].startswith(("-", "!")):
        i += 1
    return range(g + 1, i)


def judge_segments(judge, scans):
    """judge.segment on every non-empty segment of every scanned text."""
    for s, nested in scans:
        for a, b in s.segments():
            if a <= b:
                judge.segment(s, a, b, nested)


def parse_targets(doc, name, judge, allow_var):
    """The parse of a guard that judges target paths: `judge(cwd, home)` walks the
    command and gathers its targets; `allow_var` names the env var of extra
    allowed paths. "found" is a finding parse alone comes to."""
    payload, env = doc.payload, doc.env
    out = {"found": None, "home": None, "allow": None, "targets": [], "refused": None, "bases": []}
    if doc.text is None:
        return out
    cwd = payload["cwd"]
    home = env.get("HOME", "")
    if not home.startswith("/"):
        out["found"] = deny(say("home_not_absolute", guard=name))
        return out
    walker = judge(cwd, home)
    try:
        walker.run(doc)
    except Refuse as e:
        out["refused"] = str(e)
    out.update(home=home, allow=env.get(allow_var) or None, targets=walker.targets, bases=own_bases(env, cwd))
    return out


def plan_targets(parsed, parse_allow):
    """The physical path of $HOME and each allow entry, when the allow var is set;
    of the agent's own areas and every target, when there are targets to judge.
    `parse_allow(value, home, home_p, physical)` reads the allow var."""
    if parsed["found"] or parsed["home"] is None:
        return []
    home, want = parsed["home"], []
    if parsed["allow"]:
        want.append(home)
        parse_allow(parsed["allow"], home, home, lambda p: want.append(p) or p)
    if parsed["refused"] is None and parsed["targets"]:
        want += [home] + base_needs(parsed["bases"]) + [t for t, _, _ in parsed["targets"]]
    return [Need("physical", p) for p in dict.fromkeys(want)]


def judge_targets(parsed, answers, name, parse_allow, malformed, verdict):
    """The judge of a guard that judges target paths, up to the targets
    themselves: a malformed allow var (`malformed`, a function of the guard name and the error, returning its text)
    is context when there is nothing to judge and a deny otherwise; a refused
    parse is a deny. Past that, `verdict(targets, home, bases, physical, *extras)`
    judges the targets, `bases` being own_bases, extras being what parse_allow found besides its error
    (none when the allow var is unset)."""
    if parsed["found"] or parsed["home"] is None:
        return parsed["found"]
    home, physical = parsed["home"], physical_of(answers)
    extras, allow_err = [], None
    if parsed["allow"]:
        *extras, allow_err = parse_allow(parsed["allow"], home, physical(home), physical)
    allow_msg = malformed(name, allow_err) if allow_err else None
    refused = parsed["refused"]
    if refused is None and not parsed["targets"]:
        return context(allow_msg) if allow_msg else None
    if allow_msg:
        return deny(allow_msg)
    if refused is not None:
        return deny(refused)
    return verdict(parsed["targets"], home, parsed["bases"], physical, *extras)


def check_targets(doc, name, judge, allow_var, parse_allow, malformed, verdict):
    """The whole check of a guard that judges target paths: parse_targets,
    plan_targets and judge_targets, in planned's order."""
    return (yield from planned(doc, lambda d: parse_targets(d, name, judge, allow_var),
                               lambda p: plan_targets(p, parse_allow),
                               lambda p, a: judge_targets(p, a, name, parse_allow, malformed, verdict)))


def project_config(payload, env, name):
    """The project's `name` file: the nearest at or above cwd, stopping at the repo
    root, because the agent may have cd'd into another repo; then
    $CLAUDE_PROJECT_DIR's. Returns (path or None, whether cwd was a usable directory)."""
    cwd = payload.get("cwd")
    usable = isinstance(cwd, str) and cwd.startswith("/") and (yield Need("path", "isdir", cwd))
    if usable:
        d = yield Need("path", "realpath", cwd)
        while True:
            if (yield Need("path", "lexists", os.path.join(d, name))):
                return os.path.join(d, name), True
            if (yield Need("path", "lexists", os.path.join(d, ".git"))) or os.path.dirname(d) == d:
                break
            d = os.path.dirname(d)
    proj = env.get("CLAUDE_PROJECT_DIR")
    if proj and (yield Need("path", "lexists", os.path.join(proj, name))):
        return os.path.join(proj, name), bool(usable)
    return None, bool(usable)


def read_json(path):
    """The file at path, parsed as JSON, or Refuse naming why it cannot be."""
    try:
        return json.loads((yield Need("read", path)))
    except ValueError as e:
        raise Refuse(f"not JSON ({e})")
    except RecursionError:
        raise Refuse("not JSON (nested too deep to parse)")
    except OSError as e:
        raise Refuse(f"unreadable ({e.strerror})")


def read_rules(path, *args, **kwargs):
    """The command rules of the file at path (scan.load_rules, given args and
    kwargs after cfg), or Refuse naming why they cannot be had."""
    cfg = yield from read_json(path)
    try:
        return sw.load_rules(cfg, *args, **kwargs)
    except sw.BadRules as e:
        raise Refuse(str(e))
