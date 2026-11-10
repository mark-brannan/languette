"""Stops: whether a command stops a service or a process, read through a
program description (PROGRAMS) and a unit test, for systemctl, the SysV
front ends and the process killers.
"""

import difflib
import fnmatch
import os
import re

from .forges import GH_API_FIELDS, GH_API_VALUED, GH_METHOD_FLAGS, GH_REPO_FLAGS
from .texts import cmd_index


_CTL_OTHER = {"--user", "-H", "--host", "-M", "--machine"}
CTL_HOST = {"isolate", "rescue", "emergency", "halt", "poweroff", "reboot", "kexec", "soft-reboot"}
_CTL_STOP = {"stop", "restart", "try-restart", "reload-or-restart", "try-reload-or-restart", "kill"}
# Options that take a separate value; the value is not the verb. A missing one only fails closed.
_CTL_ARG = {"-t", "--type", "-p", "--property", "-s", "--signal", "-n", "--lines", "-o", "--output",
            "--root", "--state", "--job-mode", "--kill-whom", "--kill-who", "--preset-mode", "--timestamp"}
# Options that take no value. Any option in neither set, before the verb, means the verb cannot be
# known, so a read verb after it does not clear the segment.
_CTL_FLAG = {"-a", "--all", "-l", "--full", "-q", "--quiet", "-r", "--recursive", "-f", "--force", "-i",
             "-T", "--show-transaction", "--now", "--no-pager", "--no-legend", "--no-block", "--no-wall",
             "--no-ask-password", "--failed", "--system", "--reverse", "--after", "--before", "--plain",
             "--value", "--dry-run", "--wait", "--global", "--runtime"}
# Verbs whose own arguments may be any word, so a later `reboot` is a unit or pattern, not a verb.
_CTL_READ = {"status", "show", "cat", "help", "list-units", "list-unit-files", "list-sockets", "list-timers",
             "list-jobs", "list-dependencies", "list-automounts", "list-paths", "list-machines",
             "is-active", "is-enabled", "is-failed", "is-system-running", "show-environment", "get-default",
             "start", "reload", "enable", "reenable", "daemon-reload"}


# A stop verb, and the long options it needs to stop the unit: `disable` and `mask` stop it only with --now.
CTL_STOPS = {**{v: [] for v in sorted(_CTL_STOP)}, "disable": ["--now"], "mask": ["--now"]}
# The SysV stops: `service` hands any verb to systemctl, so its stops are systemctl's, and the init scripts' own.
SERVICE_STOPS = {v: [] for v in sorted(_CTL_STOP | {"force-reload", "force-stop", "--full-restart"})}
# The SysV front ends; an init script under /etc/init.d is the fourth, the `script` of its description.
SYSV_CMDS = ("service", "invoke-rc.d", "rc-service")

# Program descriptions (docs/design/guard-rules.md, "A program description"): how a command rule
# reads a program's words. `valued`: options that take a value, so the value is no operand;
# `flags`: options that take none; any other option before the first operand leaves the verb unknown.
# `away`: options that send the call to another manager or host, so it stops nothing here.
# `reads`: verbs whose arguments may be any word. `unit`: where the unit sits: "after" the verb,
# "beside" it (on either side), or "operand" (no verb: each operand names units). `script`: a
# command word that is a unit's own script, its name the unit. `pattern`: what an operand is to
# the unit test, a "regex" or a "name", and `regex` the options that make a name a regex. `fold`:
# the options that fold case. `signal`: `-9` and `-KILL` are a signal, not options. `opaque`: an
# operand the scan cannot read (a substitution, a variable) fails closed. `inverse`: the options
# that select every process the pattern does not, so they hit. `selects`: options whose value is a
# file that selects processes (a pidfile), read as a process name.
PROGRAMS = {
    "systemctl": {"valued": _CTL_ARG, "flags": _CTL_FLAG, "away": _CTL_OTHER, "reads": _CTL_READ, "unit": "after"},
    "sysv": {"unit": "beside", "script": r"etc/(?:rc\.d/)?init\.d/[^/]+", "via": ("sh", "bash", "dash")},
    "pkill": {"valued": frozenset("-g -G -P -s -t -u -U -F -r -q --pgroup --group --parent --session --terminal "
                                  "--euid --uid --pidfile --runstates --queue --signal --ns --nslist --cgroup "
                                  "--env --older --newer".split()),
              "flags": frozenset("-c -e -f -i -n -o -v -w -x -A -H -L --count --echo --full --ignore-case --newest "
                                 "--oldest --inverse --lightweight --exact --ignore-ancestors --require-handler "
                                 "--logpidfile".split()),
              "unit": "operand", "pattern": "regex", "fold": {"-i", "--ignore-case"}, "signal": True, "opaque": True,
              "inverse": {"-v", "--inverse"}, "selects": {"-F", "--pidfile"}},
    "killall": {"valued": frozenset("-o -y -u -s -Z -n --older-than --younger-than --user --signal --context --ns".split()),
                "flags": frozenset("-e -g -i -l -q -r -v -V -w -I --exact --process-group --interactive --list "
                                   "--quiet --regexp --verbose --version --wait --ignore-case".split()),
                "unit": "operand", "pattern": "name", "regex": {"-r", "--regexp"}, "fold": {"-I", "--ignore-case"},
                "signal": True, "opaque": True},
    # Descriptions that name only `valued`, read by operands(): an option outside it is a flag.
    "terragrunt": {"valued": frozenset(
        "--terragrunt-config --config --terragrunt-working-dir --working-dir --terragrunt-download-dir "
        "--download-dir --terragrunt-iam-role --iam-assume-role --terragrunt-parallelism --parallelism "
        "--terragrunt-include-dir --queue-include-dir --terragrunt-exclude-dir --queue-exclude-dir "
        "--terragrunt-log-level --log-level --terragrunt-source --source".split())},
    "pulumi": {"valued": frozenset("--color --cwd -C --profiling --tracing --memprofilerate --verbose -v".split())},
    "cdk": {"valued": frozenset("-a --app -c --context -p --plugin --profile -r --role-arn -o --output --proxy "
                                "--ca-bundle-path --toolkit-stack-name --build --lookups --notices".split())},
    "aws": {"valued": frozenset("--profile --region --endpoint-url --output --query --ca-bundle --cli-read-timeout "
                                "--cli-connect-timeout --color --cli-binary-format".split())},
    "kubectl": {"valued": frozenset(
        "-n --namespace --context --kubeconfig --cluster --user -s --server --token --as --as-group "
        "--as-uid --certificate-authority --client-certificate --client-key --cache-dir "
        "--request-timeout --tls-server-name --username --password --profile --profile-output "
        "--log-flush-frequency -v --v --vmodule".split())},
    "helm": {"valued": frozenset("-n --namespace --kube-context --kubeconfig --kube-apiserver --kube-token "
                                 "--kube-as-user --kube-as-group --kube-ca-file --kube-tls-server-name "
                                 "--registry-config --repository-cache --repository-config --burst-limit "
                                 "--qps".split())},
    # A push takes any unambiguous prefix of a long option; --exec is --receive-pack.
    "git push": {"valued": frozenset("-o --push-option --repo --receive-pack --exec".split())},
    "gh api": {"valued": frozenset(GH_REPO_FLAGS + GH_METHOD_FLAGS + GH_API_FIELDS + ("--input",)) | GH_API_VALUED},
}
_SIGNAL = re.compile(r"-(?:[0-9]+|(?:SIG)?[A-Z][A-Z0-9+-]+)\Z")


def unit_names(u):
    """The names `u` answers to: as written, without its unit-type suffix, and without its `@instance`."""
    bare = re.sub(r"\.(?:service|socket|target|scope|slice)\Z", "", u)
    return {u, bare, bare.split("@")[0]}


class _Dark(str):
    """An operand the scan cannot read, a substitution or a variable, as written."""


class _Path(str):
    """A file an option names that selects processes (pkill's pidfile): a name, held in its path."""


def _read(s, g, b, prog):
    """The words past the command at g, read with program description `prog`: (operands, options,
    words, known), or None when an option sends the call to another manager or host. Quoted text
    is its text; an operand the scan cannot read is _Dark when `prog` is opaque, else as written."""
    valued, flags, away = prog.get("valued", ()), prog.get("flags", ()), prog.get("away", ())
    selects = prog.get("selects", ())
    ops, opts, words, known, skip, ended, skip_sel = [], [], [], True, False, False, False
    for i in range(g + 1, b + 1):
        w = s.w[i] if s.k[i] == "w" else s.q[i]
        if skip:
            skip = False
            if skip_sel:
                ops.append(_Dark(w) if s.live[i] else _Path(w))
        elif w == "--" and s.k[i] == "w" and not ended:
            words.append(w)
            ended = True                       # past `--`, every word is an operand
        elif s.k[i] == "w" and not ended and w.startswith("-") and w.split("=", 1)[0] in away:
            return None                        # a variable host (`--host=$H`) is still another host
        elif s.live[i] or s.k[i] != "w":
            if prog.get("opaque"):
                ops.append(_Dark(w) if s.live[i] else w)
            elif s.k[i] == "w":
                words.append(w)
                ops.append(w)
        elif ended or not w.startswith("-") or w == "-":
            words.append(w)
            ops.append(w)
        elif w.startswith("--"):
            words.append(w)
            name = w.split("=", 1)[0]
            if name in away:
                return None                    # tested here, so an option's value (`--root -M`) is not it
            opts.append(name)
            if name in selects and name != w:
                ops.append(_Path(w.split("=", 1)[1]))
            if name in valued and name == w:
                skip, skip_sel = True, name in selects
            elif name not in valued and name not in flags and name == w:
                known = known and bool(ops)
        else:                                  # a short option, or a cluster of them
            words.append(w)
            letters = ["-" + c for c in w[1:]]
            if prog.get("signal") and _SIGNAL.match(w) and not all(o in flags for o in letters):
                opts.append(w)
                continue
            for j, o in enumerate(letters):
                if o in away:
                    return None
                opts.append(o)
                if o in valued:
                    skip = j == len(letters) - 1   # a value joined to it (`-upostgres`) ends the cluster
                    skip_sel = skip and o in selects
                    if not skip and o in selects:
                        ops.append(_Path(w[j + 2:]))
                    break
                if o not in flags:
                    known = known and bool(ops)
    return ops, opts, words, known


def stop_of(s, a, b, match, hit, host_verbs=()):
    """(the command as written, the stop) when the segment runs a command rule's program on a unit
    `hit` accepts, with a verb of the rule's `verbs` (verb: the long options it needs) or, after
    systemctl's, one of `host_verbs`; else None. The rule's `program` names its description."""
    prog = PROGRAMS[match.get("program", "systemctl")]
    names = [match["cmd"]] if isinstance(match["cmd"], str) else match["cmd"]
    g = cmd_index(s, a, b, re.compile(r"(?:^|/)(?:" + "|".join(map(re.escape, names)) + r")\Z"), True)
    own = None
    if g is None and "script" in prog:
        script = re.compile(r"(?:^|/)" + prog["script"] + r"\Z")
        g = cmd_index(s, a, b, script, True)
        if g is None:                          # `sh /etc/init.d/postgresql stop`
            sh = cmd_index(s, a, b, re.compile(r"(?:^|/)(?:" + "|".join(prog.get("via", ())) + r")\Z"), True)
            arg = sh is not None and next((i for i in range(sh + 1, b + 1)
                                           if s.k[i] != "w" or not s.w[i].startswith("-")), None)
            g = arg if arg and s.k[arg] == "w" and script.search(s.w[arg]) else None
        own = g is not None and os.path.basename(s.w[g])
    if g is None:
        return None
    got = _read(s, g, b, prog)
    if got is None:
        return None
    ops, opts, words, known = got
    head, verbs = s.w[g] if own else os.path.basename(s.w[g]), match.get("verbs", {})
    if prog["unit"] == "after":
        if known and ops and ops[0] in prog.get("reads", ()):
            return None
        # The verb is the first word past the options, but an option's value looks like a word too
        # (`--root /x reboot`), so any down verb in the segment counts unless a read verb leads.
        for i, w in enumerate(ops):
            if w in host_verbs:
                return head, w
            if w in verbs and all(o in opts for o in verbs[w]):
                unit = next((u for u in ops[i + 1:] if hit(u)), None)
                if unit:
                    return head, f"{w} {unit}"
        return None
    if prog["unit"] == "beside":               # `service ssh --full-restart`, `service -v ssh stop`
        verb = next((w for w in words if w in verbs), None)
        if verb is None:
            return None
        if own:
            return (head, verb) if hit(own) else None
        unit = next((u for u in ops if u != verb and not u.startswith("-") and hit(u)), None)
        return (head, f"{unit} {verb}") if unit else None
    inverse = next((o for o in opts if o in prog.get("inverse", ())), None)
    if inverse and ops:                        # it selects every process the pattern does not
        return head, f"{inverse} {ops[-1]}"
    if prog.get("opaque") and _opens_backtick(s, b) and s.w[b] not in prog.get("valued", ()):
        ops.append(_Dark("`"))                 # a backtick substitution ends the segment: its words are elsewhere
    how = "regex" if any(o in opts for o in prog.get("regex", ())) else prog["pattern"]
    fold = any(o in opts for o in prog.get("fold", ()))
    unit = next((u for u in ops if isinstance(u, _Dark) or hit(u, "name" if isinstance(u, _Path) else how, fold)),
                None)
    return None if unit is None else (head, unit)


def _opens_backtick(s, b):
    """The separator past word b opens a backtick substitution (an even count of backticks before it)."""
    j = b + 1
    return (j < len(s.w) and s.k[j] == ";" and s.op[j].startswith("`")
            and sum(op.count("`") for op in s.op[:j]) % 2 == 0)


def _literals(p):
    """The literal names a unit pattern holds: its unit names, or for a glob its literal runs."""
    if not any(c in p for c in "*?["):
        return unit_names(p)
    return {r for r in re.split(r"[*?@]+", re.sub(r"\[[^\]]*\]?", "*", p)) if r}


def _may_match(pat, names, fold):
    """Could process pattern `pat`, a regex, select a process of one of `names`? It does when it,
    or a word or path part of it, finds one of the names, or holds one, or a literal run of it (three
    characters or more) is part of a name or shares all but two of one's. It is tried without its
    anchors too, since a process's name or command line is not the unit's name (`^postgres$`
    selects PostgreSQL's daemon); that try only adds hits. One that does not compile fails closed."""
    flags = re.I if fold else 0

    def finds(p):
        parts = {p} | {f for f in re.split(r"[\s/]+", p) if f}
        return any(re.search(f, n, flags) for f in parts for n in names)
    try:                                       # dropping anchors may break `\$`: that fails closed too
        if finds(pat) or finds(re.sub(r"\\[AZbB]|[\^$]", "", pat)):
            return True
    except re.error:
        return True
    low = pat.lower() if fold else pat
    names = {n.lower() if fold else n for n in names}
    if any(n in low for n in names):
        return True
    # A literal run of the pattern that a name holds, or that holds most of a name (`postgres.*main`,
    # `-Dpostgres`: a daemon's process is named for its unit's stem).
    runs = {r for r in re.split(r"(?:\\.|[\W_])+", low) if len(r) >= 3}
    return any(r in n or _common(r, n) >= max(3, len(n) - 2) for r in runs for n in names)


def _common(x, y):
    """The length of the longest run of characters x and y share."""
    m = difflib.SequenceMatcher(None, x, y, autojunk=False).find_longest_match(0, len(x), 0, len(y))
    return m.size


# A command rule on a stop: docs/design/guard-rules.md, "Command rules". Its match is
# {"cmd": program word or list, "program": a PROGRAMS key (systemctl when absent),
#  "verbs": {verb: [long options it needs]}, "unit": condition}, and it hits when a verb, holding
# its options, acts on a unit the condition accepts. Conditions are a closed list: {"units":
# [pattern]}, a unit that answers to an fnmatch pattern of the list (`*`, `?` and `[...]` all match).
def unit_test(cond):
    """The test on a unit that condition `cond` names, or None when no unit can pass it. The test
    takes how the operand is read: a "unit" answers to a listed pattern, and a glob in it may name a
    listed one, so it passes: the test fails closed. A process "name" passes as a unit does, or when
    it holds a listed name or a listed name holds it (`postgres` is PostgreSQL's daemon). A "regex"
    passes when it could select a listed unit's process. `fold` folds case."""
    pats = cond["units"]
    if not pats:
        return None
    names = {n for p in pats for n in _literals(p)}

    def hit(u, how="unit", fold=False):
        if how == "regex":
            return _may_match(u, names, fold)
        f = str.lower if fold else str
        if how == "name" and any(f(n) in f(u) or f(u) in f(n) for n in names):
            return True
        return any(c in u for c in "*?[") or any(
            fnmatch.fnmatchcase(f(n), f(p)) for n in unit_names(u) for p in pats)
    return hit


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
