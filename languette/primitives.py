"""The named tests a rule set's `{"test": name}` entry may use (docs/design/guard-rules.md,
"Primitives"): each a pure function of the Document that gives the fields of its
rule's message when the call is one it describes, else None. A test that needs facts
of the world (the physical path of a target) is a generator that yields them as Needs
and gives the verdict itself, deny or context, else None. A test one guard needs
lives here, named, until a second guard asks for it; the registry is closed, and
only a shipped rule set may name one.
"""

import functools
import inspect
import os
import re

from languette import paths
from languette import scan as sw
from languette.messages import say
from languette.verdict import Refuse, deny

_POWER = re.compile(r"(?:^|/)(?:shutdown|reboot|halt|poweroff)\Z")
_FORK = re.compile(r"([A-Za-z_:][A-Za-z0-9_:]*)\s*\(\s*\)\s*\{\s*\1\s*\|\s*\1\s*&")


def _power(s, a, b):
    g = sw.cmd_index(s, a, b, _POWER, True)
    if g is None:                              # `sh -c reboot`: a one-word script is not a nested text
        g = next((i for i in range(a + 1, b + 1) if s.k[i] == "w" and _POWER.search(s.w[i])
                  and re.fullmatch(r"-[A-Za-z]*c", s.w[i - 1])), None)
    return None if g is None else os.path.basename(s.w[g])


def power_word(doc):
    """shutdown, reboot, halt or poweroff at command position, or as the one-word script of `sh -c`."""
    for t, _ in doc.texts():
        s = doc.scan(t)
        for a, b in s.segments():
            what = a <= b and _power(s, a, b)
            if what:
                return {"what": what}
    return None


def fork_bomb(doc):
    """The fork-bomb shape. It is raw text, so a commit message that quotes it must not trip it:
    only a text with a segment that is not led by a prose consumer is read."""
    for t, _ in doc.texts():
        s = doc.scan(t)
        segs = [(a, b) for a, b in s.segments() if a <= b]
        if any(sw.seg_cmd(s, a, b) is None or s.w[sw.seg_cmd(s, a, b)] not in sw.PROSE or s.shellseg
               for a, b in segs) and _FORK.search(t):
            return {}
    return None


_DL = re.compile(r"(?:^|/)(?:curl|wget|fetch)\Z")
_INTERP = re.compile(r"(?:^|/)(?:sh|bash|dash|zsh|ksh|ash|fish|python[0-9.]*|perl[0-9.]*|node|ruby)\Z")
_SHELLS = re.compile(r"(?:sh|bash|dash|zsh|ksh|ash|fish)\Z")
_FED = ("(", "`")

# family -> (letters that mean "the program is given", options that take a value)
_NODE_SCRIPT = ("-e", "--eval", "-p", "--print", "-pe", "-ep", "-c", "--check")
_VALUE_OPTS = {"sh": ("-o", "-O", "+o", "+O", "--rcfile", "--init-file"), "python": ("-W", "-X"),
               "perl": ("-I",), "ruby": ("-I", "-r"), "node": ("-r", "--require", "--import", "--loader")}


def _family(path):
    name = os.path.basename(path)
    return ("sh" if _SHELLS.fullmatch(name) else "python" if name.startswith("python") else
            "perl" if name.startswith("perl") else name)


def _program(s, g, b):
    """How the interpreter at g gets its program: (script_given, operands),
    where script_given means a -c, -e or -m the interpreter runs instead of
    stdin, and operands are the words that are neither options nor their values."""
    fam, given, ops = _family(s.w[g]), False, []
    i = g + 1
    while i <= b:
        x, at, i = s.w[i], i, i + 1
        if s.k[at] != "w":
            ops.append(x)
        elif x == "--":
            ops += s.w[i:b + 1]
            break
        elif x in _VALUE_OPTS.get(fam, ()):
            i += 1
        elif x == "-" or (len(x) > 1 and x[0] in "-+"):
            if fam == "node":
                given = given or x in _NODE_SCRIPT
            elif re.fullmatch(r"-[A-Za-z]+", x) and not (fam == "perl" and x[1] in "MmIiFd"):
                given = given or any(ch in x for ch in {"sh": "c", "python": "cm", "perl": "eE", "ruby": "e"}[fam])
        else:
            ops.append(x)
    return given, ops


def _reads_stdin(s, g, b):
    """The interpreter at g takes its program from stdin: no -c/-e/-m, and no
    script operand (a lone `-` is stdin)."""
    given, ops = _program(s, g, b)
    if _family(s.w[g]) == "sh":
        stdin_flag = any(re.fullmatch(r"-[A-Za-z]*s[A-Za-z]*", w) for w in s.w[g + 1:b + 1])
        return not given and (stdin_flag or not ops)
    return not given and (not ops or ops[0] == "-")


def _has_dl(s, a, b, nested):
    return sw.cmd_index(s, a, b, _DL, nested) is not None


def _text_downloads(doc, raw):
    """A quoted word's text runs a download inside a substitution."""
    if "$(" not in raw and "`" not in raw:
        return False
    s = doc.scan(raw)
    return any(a <= b and _has_dl(s, a, b, False) for a, b in s.segments())


def _pipe_why(doc, s, nested):
    """The reason this scanned text is a pipe-to-shell, or None."""
    segs = {a: b for a, b in s.segments() if a <= b}
    carried = False
    for a, b in sorted(segs.items()):
        sep = s.op[a - 1] if a > 0 else ""
        if "|" not in sep.replace("||", "").replace("&&", ""):
            carried = False
        c = sw.seg_cmd(s, a, b)
        g = sw.cmd_index(s, a, b, _INTERP, nested)
        fed = (b + 1 < len(s.w) and s.op[b + 1].startswith(_FED)
               and (b + 2 in segs and _has_dl(s, b + 2, segs[b + 2], nested)))
        if g is not None:
            name = os.path.basename(s.w[g])
            if carried and _reads_stdin(s, g, b):
                return say("pipe_into", name=name)
            given, ops = _program(s, g, b)
            if fed and (given or not ops):
                return say("pipe_substituted", name=name)
            if given and any(s.k[i] == "q" and _text_downloads(doc, s.q[i]) for i in range(g + 1, b + 1)):
                return say("pipe_substituted_c", name=name)
        if c is not None and s.w[c] == "eval":
            if fed or any(s.k[i] == "q" and _text_downloads(doc, s.q[i]) for i in range(c + 1, b + 1)):
                return say("pipe_eval")
        if c is not None and s.w[c] in ("source", ".") and fed and len(s.w[c + 1:b + 1]) == 0:
            return say("pipe_source", name=s.w[c])
        if _has_dl(s, a, b, nested):
            carried = True
    return None


def pipe_to_shell(doc):
    """A download that is run as it arrives: piped into an interpreter that reads stdin, handed
    over as a file (`sh <(curl u)`) or as text (`eval "$(curl u)"`)."""
    for text, nested in doc.texts():
        why = _pipe_why(doc, doc.scan(text), nested)
        if why:
            return {"why": why, "way_out": say("pipe_to_shell_way_out")}
    return None




# The tests that judge target paths (recursive-delete, permissions): the walk of the command
# gathers the targets, paths.check_targets asks the world where each really is.
_FIND = re.compile(r"(?:^|/)find\Z")
_RM = re.compile(r"(?:^|/)rm\Z")
_RM_PARENTS = re.compile(r"^(?:" + "|".join(sw.GIT_WRAPPERS) + r"|svn|hg|jj|gsutil)\Z")
# Adding a name is a PR, not a judgment call in a session.
#   node_modules   npm/yarn/pnpm install output, most JS repos
#   dist           tsc/vite/webpack build output
#   coverage       test coverage reports (nyc/jest/vitest)
#   .pio           PlatformIO build cache
GENERATED_NAMES = ("node_modules", "dist", "coverage", ".pio")


class _RmJudge:
    """Find every recursive target in the command and either refuse it on
    sight or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home = cwd, home
        self.trig, self.moved, self.targets = "rm", False, []

    def lab(self, raw):
        if self.trig == "find":
            return "find" + ("" if raw == "" else " " + raw) + " -delete"
        return "rm -r" + ("" if raw == "" else " " + raw)

    def blocked(self, raw, why):
        raise Refuse(say("recursive_delete", label=self.lab(raw), why=why))

    def target(self, s, idx):
        raw = s.w[idx]
        try:
            t = paths.resolve_target(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.blocked(raw, str(e))
        self.targets.append((t, self.trig, raw))

    def segment(self, s, a, b, nested):
        g = sw.cmd_index(s, a, b, _FIND, nested)
        if g is not None and "-delete" in s.w[g + 1:b + 1]:
            self.trig, starts = "find", paths.find_starts(s, g, b)
            if not starts:
                self.blocked("", say("rd_find_no_start"))
            for i in starts:
                self.target(s, i)
            self.trig = "rm"
        g = sw.cmd_index(s, a, b, _RM, nested, _RM_PARENTS)
        if g is None:
            return
        recursive, dashdash, tgt = False, False, []
        for i in range(g + 1, b + 1):
            x = s.w[i]
            if not dashdash and x == "--":
                dashdash = True
                continue
            # GNU getopt_long takes any unambiguous prefix: --rec, --r are --recursive.
            if not dashdash and s.k[i] == "w" and x.startswith("--"):
                if len(x) >= 3 and "--recursive".startswith(x):
                    recursive = True
                continue
            if not dashdash and s.k[i] == "w" and len(x) >= 2 and x.startswith("-"):
                if re.fullmatch(r"-[A-Za-z0-9]*[rR][A-Za-z0-9]*", x):
                    recursive = True
                continue
            tgt.append(i)
        if not recursive:
            return
        if not tgt:
            self.blocked("", say("rd_no_target"))
        for i in tgt:
            self.target(s, i)

    def run(self, doc):
        scans = [(doc.scan(t), nested) for t, nested in doc.texts()]
        # Any cd anywhere makes every relative target in the command unresolvable.
        self.moved = paths.moves_directory(scans)
        paths.judge_segments(self, scans)


def _rm_malformed(guard, err):
    return say("rm_malformed", guard=guard, err=err)


def _rm_verdict(targets, home, bases, physical, extra_roots=(), extra_names=()):
    names = GENERATED_NAMES + tuple(extra_names)
    roots = paths.own_roots(home, bases, physical, extra_roots)

    def is_generated(p):
        if p.startswith(home + "/"):
            p = p[len(home) + 1:]
        for depth, seg in enumerate((s for s in p.split("/") if s), 1):
            if seg in names:
                return depth != 1
        return False

    def allowed(p):
        return paths.under(p, roots) or is_generated(p)

    for abs_, kind, raw in targets:
        what = f"find {raw} -delete" if kind == "find" else f"rm -r {raw}"
        if not allowed(abs_):
            return deny(say("rd_not_allowed", what=what, raw=raw, abs_=abs_))
        phys = physical(abs_)
        if phys != abs_ and not allowed(phys):
            return deny(say("rd_symlink_out", what=what, abs_=abs_, phys=phys))
    return None


def recursive_delete(doc):
    """A recursive `rm` or `find ... -delete` whose every target, resolved against the cwd and
    then the filesystem, is not the agent's to remove: the scratchpad, an agent worktree, /tmp
    or a generated directory (GENERATED_NAMES) that is not a direct child of $HOME or of /. A
    target that does not resolve to one allowed path is denied on sight."""
    return (yield from paths.check_targets(doc, "guard-recursive-delete", _RmJudge, "LANGUETTE_RM_ALLOW",
                                           functools.partial(paths.parse_allow, bare_names=True), _rm_malformed,
                                           _rm_verdict))


_PERM = re.compile(r"(?:^|/)(chown|chgrp|chmod)\Z")
_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_WRAPPERS = re.compile(r"(?:sudo|doas|env|nice|nohup|timeout|command|exec|time|ionice|stdbuf|sh|bash|dash|zsh|ksh)\Z")
_PERM_IN_TEXT = re.compile(r"(?:^|[^A-Za-z0-9_./-])(chmod|chown|chgrp)(?![A-Za-z0-9_-])")
_CHMOD_FLAGS = re.compile(r"-[Rcfv]+\Z")
_WORLD = re.compile(r"(?:0*777|(?:a|ugo)[+=]rwx)\Z")
_PERM_WAY_OUT = say("perm_way_out")


def _perm_allow(value, home, home_p, physical):
    """LANGUETTE_PERM_ALLOW -> (extra_roots, error or None): absolute paths only."""
    roots, _, err = paths.parse_allow(value, home, home_p, physical)
    return roots, err


def _exec_perm(s, g, b):
    """The chmod, chown or chgrp that a find at g runs with -exec, even behind a
    wrapper (`-exec sudo chmod`, `-exec sh -c 'chmod ..'`), else None. Once the
    command after -exec is a wrapper, the rest of the clause is searched."""
    for i in range(g + 1, b):
        if s.k[i] != "w" or s.w[i] not in _EXEC:
            continue
        m = _PERM.search(s.w[i + 1]) if s.k[i + 1] == "w" else None
        if m:
            return m.group(1)
        if s.k[i + 1] != "w" or not _WRAPPERS.fullmatch(os.path.basename(s.w[i + 1])):
            continue
        for j in range(i + 1, b + 1):
            m = _PERM.search(s.w[j]) if s.k[j] == "w" else _PERM_IN_TEXT.search(s.q[j])
            if m:
                return m.group(1)
    return None


class _PermJudge:
    """Find every judged target in the command and either refuse it on sight
    or return it resolved."""

    def __init__(self, cwd, home):
        self.cwd, self.home = cwd, home
        self.moved, self.targets, self.what = False, [], ""

    def blocked(self, raw, why):
        raise Refuse(say("perm_blocked", target=f"{self.what}{' ' + raw if raw else ''}", why=why,
                         way_out=_PERM_WAY_OUT))

    def target(self, s, idx):
        raw = s.w[idx]
        try:
            t = paths.resolve_target(raw, s.k[idx] == "q", self.cwd, self.home, self.moved)
        except paths.Unresolved as e:
            self.blocked(raw, str(e))
        if ".git" in t.split("/"):
            self.blocked(raw, "it is inside a .git directory, the repository's own store")
        self.targets.append((t, self.what, raw))

    def perm(self, s, g, b, sweep):
        """chown, chgrp or chmod at g. `sweep`: a find -exec runs it over a tree."""
        name = _PERM.search(s.w[g]).group(1)
        recursive = ref = dashdash = False
        ops = []
        i = g + 1
        while i <= b:
            x, at, i = s.w[i], i, i + 1
            if s.k[at] != "w":
                ops.append(at)
            elif not dashdash and x == "--":
                dashdash = True
            elif not dashdash and x.startswith("--"):
                # GNU getopt_long takes any unambiguous prefix: --rec is --recursive.
                if len(x) >= 3 and "--recursive".startswith(x):
                    recursive = True
                elif x == "--reference":
                    ref, i = True, i + 1
                elif x.startswith("--reference="):
                    ref = True
            elif not dashdash and len(x) > 1 and x[0] == "-":
                if re.fullmatch(r"-[A-Za-z0-9]*R[A-Za-z0-9]*", x):
                    recursive = True
                # chmod's mode may begin with a dash (-x, -w): it is the first operand, not an option.
                if name == "chmod" and not ref and not ops and not _CHMOD_FLAGS.fullmatch(x):
                    ops.append(at)
            else:
                ops.append(at)
        mode = None
        if not ref and ops:
            mode = s.w[ops.pop(0)]
        world = name == "chmod" and mode is not None and bool(_WORLD.fullmatch(mode))
        if not (recursive or world or sweep):
            return
        self.what = f"{name} -R" if recursive else f"{name} {mode}" if world else f"find -exec {name}"
        if not ops:
            if sweep:
                return
            self.blocked("", "no target is visible to this hook -- xargs, brace expansion and quoted lists all "
                             "look like this. Run it on the resolved paths directly")
        for i in ops:
            self.target(s, i)

    def segment(self, s, a, b, nested):
        g, sweep = sw.cmd_index(s, a, b, _FIND, nested), False
        if g is not None:
            name = _exec_perm(s, g, b)
            if name is not None:
                sweep, self.what = True, "find -exec " + name
                starts = paths.find_starts(s, g, b)
                if not starts:
                    self.blocked("", "with no start path find sweeps the working directory")
                for i in starts:
                    self.target(s, i)
        g = sw.cmd_index(s, a, b, _PERM, nested)
        if g is not None:
            self.perm(s, g, b, sweep)

    def run(self, doc):
        scans = [(doc.scan(t), nested) for t, nested in doc.texts()]
        self.moved = paths.moves_directory(scans)
        paths.judge_segments(self, scans)


def _perm_malformed(guard, err):
    return say("perm_malformed", guard=guard, err=err)


def _perm_verdict(targets, home, bases, physical, extra_roots=()):
    roots = paths.own_roots(home, bases, physical, extra_roots)
    for abs_, what, raw in targets:
        if not paths.under(abs_, roots):
            return deny(say("perm_not_allowed", what=what, raw=raw, abs_=abs_, way_out=_PERM_WAY_OUT))
        phys = physical(abs_)
        if phys != abs_ and not paths.under(phys, roots):
            return deny(say("symlink_out", what=what, raw=raw, abs_=abs_, phys=phys, way_out=_PERM_WAY_OUT))
    return None


def permissions(doc):
    """A recursive chown, chgrp or chmod (-R, --recursive, a short cluster holding R), `chmod 777`,
    and `find ... -exec chown|chgrp|chmod`, whose every target, resolved against the cwd and then
    the filesystem, is not the agent's own: under the scratchpad, an agent worktree or /tmp, or an
    absolute path named in LANGUETTE_PERM_ALLOW. Never `/`, $HOME itself, or anything inside a .git."""
    return (yield from paths.check_targets(doc, "guard-permissions", _PermJudge, "LANGUETTE_PERM_ALLOW",
                                           _perm_allow, _perm_malformed, _perm_verdict))


TESTS = {"power-word": power_word, "fork-bomb": fork_bomb, "pipe-to-shell": pipe_to_shell,
         "recursive-delete": recursive_delete, "permissions": permissions}


def judges(name):
    """Whether the test gives a verdict of its own, having asked the world: a generator."""
    return inspect.isgeneratorfunction(TESTS.get(name))
