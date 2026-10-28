"""guard-private-terms: text bound for a public GitHub repo is judged twice. The
spec is features/guard-private-terms.feature.

Once a private term is in a public issue or PR it is in GitHub's history and
every mirror of it; the undo is a support ticket, not an edit. So the check
sits at the moment the text leaves the machine.

Redact: each pair's find is replaced in the posted text alone and the call
is allowed, as a secret is redacted. Shipped, rules/redacted-terms.tsv: the
home directory in every spelling to `~`, this machine's name and LAN or
tailnet names to `<host>`, private addresses to `<private-ip>`. Yours:
redacted_terms_file, applied after, none puts `<redacted>`; a line `!<put>`
drops the shipped pairs with that put. A term the command also holds outside
the posted text, or inside a file's contents, which a redaction cannot reach,
is a deny with the fix in the reason.

Hard block: a hit on a term from blocked_terms_file denies the whole post; the
reason names the terms that hit and each term's message. It reads the text as
written, before any redaction. No file, no hard block.

Both files are one tab-separated format: find, put, comment, an optional
header row, `#` comments, case-insensitive plain text or a regular expression
under `re:`, `$NAME` the variable's value, `$HOSTNAME` asked of the OS when
unset; a line naming a variable that is unset or empty is skipped. A `re:`
the guard would not run (does not compile, matches empty, a backreference, or
a shape that backtracks without bound) is not in shape. Parsing is
languette/terms.py and languette/reshape.py, shared with `languette doctor`.
Either option expands a leading `~` or `$HOME`; unset or empty, the guard reads
$XDG_CONFIG_HOME/languette/blocked-terms.tsv or redacted-terms.tsv (~/.config
by default) if it exists. A path set is a promise: set but missing, or found
but unreadable, a directory or not in shape, denies every public-bound post
this guard judges, naming the option and the fix. A file with no terms is
valid. A cloud session or CI job is provisioned its list, never excused.

Fires on Bash `gh issue|pr create|comment|edit|review|close|reopen|merge`,
`gh api` writing to repos/*/*/issues|pulls or a graphql mutation that comments
on or opens an issue or PR, and the GitHub MCP tools that create or edit an
issue, PR, comment or review. A body posted from a script file, `curl` or
`python -c` is not seen. The text judged is only what is posted: literal
--body/--title/--comment/--subject/--label values, gh api field values, every
heredoc body, and the contents of a --body-file/--comment-file/-F/--input file,
never its path; for MCP, every string in tool_input. Each term is matched
case-insensitively as plain text.

The target repo is --repo/-R, GH_REPO=, a positional URL or owner/repo#n, the
gh api path, or MCP owner/repo; failing those, the origin of the cwd, unless
the command runs a `cd`. A graphql mutation's repo is unknown. Unknown is
judged; only when every target is in private_repos does the text go unjudged.

Only the hard block fails closed on text it cannot see. With a blocked terms
file loaded: a body built at run time that no heredoc feeds, stdin with no
heredoc, a file it cannot read, or a flag whose shape says it carries text but
is not one it knows -> deny, with the fix in the reason.
"""

import re

from languette import paths
from languette import scan as sw
from languette import terms
from languette.messages import say
from languette.verdict import Need, allow, deny

NAME = "guard-private-terms"
_MCP = ("create_issue|update_issue|issue_write|add_issue_comment|create_pull_request|update_pull_request|"
        "add_pull_request_review_comment|create_pull_request_review|pull_request_review_write|"
        "add_comment_to_pending_review|create_and_submit_pull_request_review|submit_pending_pull_request_review|"
        "add_reply_to_pull_request_comment|update_issue_comment")
# The tools hooks.json wires this guard to; the MCP ones by their name's tail.
TOOLS = re.compile(rf"(?:Bash|mcp__.*__(?:{_MCP}))\Z")
_MCP_TOOL = re.compile(rf"mcp__.*__(?:{_MCP})\Z")
TO_PRIVATE = "target a repo listed in the private_repos option"
_UNSEEN = re.compile(r"--[A-Za-z-]*(?:body|comment|message)[A-Za-z-]*")
_ACTS = frozenset("create comment edit review close reopen merge".split())
_GRAPHQL = re.compile(r"addComment|createIssue|updateIssue|createPullRequest|updatePullRequest|"
                      r"addPullRequestReview|submitPullRequestReview|addDiscussionComment")
_BACKSTOP = re.compile(r"(?:^|[^A-Za-z0-9_./-])gh\s+(?:issue|pr)\s+(?:create|comment|edit|review|close|reopen|merge)(?:\s|$)",
                       re.M)


def _flat(t):
    return t.replace("\n", " ")


class _Meta:
    """The command's records, in command order, as (kind, value):
    R repo (- = the cwd's, ? = unknown) | T posted text | HDTXT heredoc text |
    F / FX file (FX: in nested text) | CDTO dir | CDPUSH / CDPOP | A NAME=VALUE |
    HFED path a heredoc writes | STDIN | OPAQUE (what, value) | HEREDOC | CD | UNSEEN flag."""

    def __init__(self, doc, command):
        self.out = []
        buf = self.orig = command + "\n"
        counts = {}
        for p in sw.writes(buf, False):
            counts[p] = counts.get(p, 0) + 1
        for p in sw.writes(buf, True):
            if counts.get(p) == 1:
                self.add("HFED", p)
        if doc.heredocs():
            self.add("HEREDOC")
        for body in doc.heredoc_bodies():
            for line in body.split("\n") if body else ():
                self.add("HDTXT", line)
        for text, nested in doc.texts():
            s = self.s = doc.scan(text)
            for i in range(len(s.w)):
                if s.k[i] == "w" and s.w[i] in ("cd", "pushd", "popd"):
                    self.add("CD")
            for a, b in s.segments():
                if a <= b:
                    self.segment(a, b, nested)
                # A ( ) subshell inherits the cwd and its cd dies at the ): push the
                # virtual cwd at each ( and pop it at each ), in the order written.
                if not nested and b + 1 < len(s.w):
                    for c in s.op[b + 1]:
                        if c == "(":
                            self.add("CDPUSH")
                        elif c == ")":
                            self.add("CDPOP")

    def add(self, kind, value=""):
        self.out.append((kind, value))

    def file(self, p):
        if p == "-":
            self.add("STDIN")
        else:
            self.add("FX" if self.nested else "F", _flat(p))

    def fed(self, v):
        """A $VAR whose assignment in this command carries a heredoc."""
        name = re.sub(r"^\$\{?", "", v, count=1)
        name = re.sub(r"[^A-Za-z0-9_].*", "", name, count=1, flags=re.S)
        return name != "" and re.search(r"(?:^|[;&|\s])" + name + r"""=["']?\$\([^)]*<<""", self.orig) is not None

    def val(self, v, live, what=None):
        """A posted value: text, or OPAQUE (what it is, the value) when built at run
        time and no heredoc on the value itself feeds it."""
        what = what or say("pt_what_body")
        if not live:
            self.add("T", _flat(v))                  # single-quoted: posted verbatim
        elif "$(" in v or "`" in v:
            if "<<" not in v and " HEREDOC " not in v:
                self.add("OPAQUE", (what, _flat(v)))
        elif re.match(r"\$[A-Za-z_{]", v):
            if not self.fed(v):
                self.add("OPAQUE", (what, _flat(v)))
        else:
            self.add("T", _flat(v))

    def lab(self, v):
        for part in v.split(","):
            part = part.strip()
            if part:
                self.add("T", _flat(part))

    def field(self, v, live):
        key = v.split("=", 1)[0]
        v = v.split("=", 1)[1] if "=" in v else v
        if v.startswith("@"):
            self.file(v[1:])
            return
        # An id or number field names a thing by its identifier; the API refuses
        # prose there, so a run-time value carries no text to check.
        if re.search(r"(?:^|_)(?:id|number)\Z", key) and re.fullmatch(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)", v):
            return
        if "label" in key:
            self.lab(v)
        self.val(v, live, say("pt_what_field", name=key))

    def subshelled(self, lo, hi):
        """A cd in a pipeline, in backticks or backgrounded runs in a subshell."""
        s = self.s
        before = s.op[lo - 1] if lo > 0 else ""
        after = s.op[hi + 1] if hi + 1 < len(s.w) else ""
        before, after = re.sub(r"&&|\|\|", "", before), re.sub(r"&&|\|\|", "", after)
        return re.search(r"[|`]", before) is not None or re.search(r"[|&`]", after) is not None

    def cdto(self, c, lo, hi):
        """Where a top-level cd/pushd goes; `-` = somewhere unseen."""
        s = self.s
        t = "~" if s.w[c] == "cd" else "-"
        if self.subshelled(lo, hi) or "CDPATH=" in self.orig:
            self.add("CDTO", "-")
            return
        if s.w[c] != "popd":
            for i in range(c + 1, hi + 1):
                if s.w[i] == "--":
                    if i < hi:
                        t = sw.word(self.s, i + 1)
                    break
                if not re.match(r"[-+].", s.w[i]):
                    t = sw.word(self.s, i)
                    break
        self.add("CDTO", _flat(t))

    def assign(self, a, live):
        name = a.split("=", 1)[0]
        # A single-quoted $, or a quoted ~, is literal: poison it, so the path stays unresolvable.
        if (not live and "$" in a) or re.search(r"(?:^|[;&|\s])" + name + r"""=["']~""", self.orig):
            a = name + "=$"
        self.add("A", _flat(a))

    def segment(self, lo, hi, nested):
        s, self.nested = self.s, nested
        if not nested:
            c = sw.seg_cmd(s, lo, hi)
            ok = c is None and all(s.k[i] == "w" and sw._ASSIGN.match(s.w[i]) for i in range(lo, hi + 1))
            if ok or (c is not None and s.w[c] in ("export", "local", "readonly", "declare", "typeset")):
                for i in range(lo, hi + 1):
                    if s.k[i] == "w" and sw._ASSIGN.match(s.w[i]):
                        self.assign(s.w[i], s.live[i])
            elif c is not None and s.w[c] in ("cd", "pushd", "popd"):
                self.cdto(c, lo, hi)
        g = sw.cmd_index(s, lo, hi, sw.GH, nested)
        if g is None or g + 1 > hi:
            return
        repo = posrepo = ""
        for i in range(lo, g):
            if s.k[i] == "w" and s.w[i].startswith("GH_REPO="):
                repo = s.w[i][8:]
        sub = s.w[g + 1]
        if sub == "api":
            self.api(g, hi)
            return
        if sub not in ("issue", "pr") or g + 2 > hi or s.w[g + 2] not in _ACTS:
            return
        i = g + 3
        while i <= hi:
            t = sw.word(self.s, i)                       # a glued flag+quoted-value token may not be kind "w"
            live = s.live[i]
            if r := sw.gh_repo_flag(s, i, hi, repo):
                repo, i = r
            elif t in ("--body-file", "--comment-file", "-F"):
                if i < hi:
                    i += 1
                    self.file(sw.word(self.s, i))
            elif t.startswith("--body-file="):
                self.file(t[12:])
            elif t.startswith("--comment-file="):
                self.file(t[15:])
            elif t.startswith("-F") and len(t) > 2:
                self.file(t[2:])
            elif t in ("--body", "--title", "--comment", "--subject", "-b", "-t", "-c"):
                if i < hi:
                    i += 1
                    self.val(sw.word(self.s, i), s.live[i], say("pt_what_flag", name=t))
            elif re.match(r"--(?:body|title|comment|subject)=", t):
                self.val(t.split("=", 1)[1], live, say("pt_what_flag", name=t.split("=", 1)[0]))
            elif re.match(r"-[btc].", t):
                self.val(t[2:], live, say("pt_what_flag", name=t[:2]))
            elif t in ("--label", "--add-label", "-l"):
                if i < hi:
                    i += 1
                    self.lab(sw.word(self.s, i))
            elif re.match(r"--(?:add-)?label=", t):
                self.lab(t.split("=", 1)[1])
            elif t.startswith("-l") and len(t) > 2:
                self.lab(t[2:])
            elif _UNSEEN.match(t):
                # A flag whose name says it carries posted text, in a shape not read above.
                self.add("UNSEEN", _flat(t))
            elif re.match(r"https?://[^/]+/[^/]+/[^/]+/(?:issues|pull)/", t):
                u = t.split("/")
                posrepo = u[3] + "/" + u[4]
            elif re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+", t):
                posrepo = t.split("#", 1)[0]
            i += 1
        if posrepo:
            self.add("R", _flat(posrepo))
        if repo or not posrepo:
            self.add("R", _flat(repo) if repo else "-")

    def api(self, g, hi):
        api = sw.gh_api(self.s, g + 2, hi)
        for a in api.args:
            if a.text is None:
                continue
            if a.flag == "--input":
                self.file(a.text)
            else:
                self.field(a.text, a.live)
        for t in api.flags:
            if _UNSEEN.match(t):
                self.add("UNSEEN", _flat(t))
        p = api.path
        if re.match(r"repos/[^/]+/[^/]+/(?:issues|pulls)(?:/|\Z)", p):
            if api.method in ("GET", "HEAD") or (api.method == "" and not api.sends):
                return
            parts = p.split("/")
            self.add("R", parts[1] + "/" + parts[2])
        elif p == "graphql":
            if any(_GRAPHQL.search(sw.word(self.s, i)) for i in range(g, hi + 1)):
                self.add("R", "?")          # the target is a node id in the query, never the cwd's origin


def _is_private(repo, env):
    if not repo:
        return False
    listed = env.get("CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS") or ""
    return any(sw.norm_repo(r) == repo for r in sw.listed(listed))


class _Replay:
    """The virtual cwd and $VARs as the command stands at each record."""

    def __init__(self, cwd, home):
        self.vcwd, self.home, self.vars, self.stack = cwd, home, {}, []

    def expand(self, s):
        v = {"HOME": self.home, **self.vars}
        if re.match(r"~(?:/|\Z)", s):                # only where it is written, never where a $VAR puts it
            s = v["HOME"] + s[1:]
        out = ""
        while "$" in s:
            j = s.index("$")
            out, s = out + s[:j], s[j + 1:]
            m = re.match(r"\{[A-Za-z_][A-Za-z0-9_]*\}", s) or re.match(r"[A-Za-z_][A-Za-z0-9_]*", s)
            name = m.group().strip("{}") if m else None
            if m and name in v:
                out, s = out + v[name], s[m.end():]
            else:
                out += "$"
        return out + s

    def resolve(self, p):
        p = self.expand(p)
        if "$" in p or "`" in p:
            return None
        if p.startswith("/"):
            return paths.lexical(p)
        return paths.lexical(self.vcwd + "/" + p) if self.vcwd else None


def _load(kind, env, penv):
    """(the terms of the kind's file, None), or (None, the deny) for a file the guard will not
    judge by: one the option names that is missing, or any found that is not readable text
    or not in shape. Unset with no file at the default path is no terms."""
    found, path, named, err = yield from terms.load(kind, env, penv)
    if err is None:
        return found or [], None
    why = f"is not in shape: {err}" if isinstance(err, terms.BadTerms) else terms.why_not(err)
    option = terms.option_name(kind)
    if named:
        return None, deny(say("pt_terms_file", guard=NAME, option=option, path=path, why=why, to_private=TO_PRIVATE))
    return None, deny(say("pt_terms_default", guard=NAME, option=option, path=path, why=why, to_private=TO_PRIVATE))


def _changes(texts, applied):
    """What the pairs would change in the texts, as `found` -> `put`, each once."""
    out = []
    for t in applied:
        for text in texts:
            for m in t.rx.finditer(text):
                out.append(f"`{m.group(0)}` -> `{terms.DEFAULT_PUT if t.put is None else t.put}`")
    return ", ".join(dict.fromkeys(out))


def check(doc):
    payload, env = doc.payload, doc.env
    tool = doc.tool
    if not isinstance(tool, str) or not tool:
        return None
    cwd = payload["cwd"]
    ti = doc.tool_input if isinstance(doc.tool_input, dict) else {}
    if tool == "Bash":
        cmd = ti.get("command")
        if not isinstance(cmd, str) or not cmd:
            return None
        meta = _Meta(doc, cmd).out
        # The tokeniser can lose a segment behind an odd construct; the raw string is
        # the backstop, so a gh write it names is scanned with the repo unknown.
        if not any(k == "R" for k, _ in meta) and _BACKSTOP.search(cmd):
            meta.append(("R", "-"))
        if not any(k == "R" for k, _ in meta):
            return None
        text_cmd = "".join(v + "\n" for k, v in meta if k in ("T", "HDTXT"))
    elif _MCP_TOOL.match(tool):
        owner, repo = ti.get("owner"), ti.get("repo")
        meta = [("R", f"{owner}/{repo}" if owner not in (None, "") and repo not in (None, "") else "-")]
        text_cmd = "\n".join(_strings(ti)) + "\n"
    else:
        return None

    cd = any(k == "CD" for k, _ in meta)
    all_private = True
    for kind, repo in meta:
        if kind != "R":
            continue
        if repo == "?":
            repo = ""
        elif repo == "-":
            repo = "" if cd else ((yield Need("git", "git", cwd, "remote", "get-url", "origin")) or "")
        if not _is_private(sw.norm_repo(repo), env):
            all_private = False
    if all_private:
        return None

    # The shipped pairs, then the user's. HOSTNAME is the OS's when the env has none.
    penv = yield from terms.environment(env)
    shipped = yield from terms.shipped(penv)
    mine, refused = yield from _load("redacted", env, penv)
    if refused:
        return refused
    blocked, refused = yield from _load("blocked", env, penv)
    if refused:
        return refused
    applied = terms.pairs(shipped, mine)

    # Only the hard block fails closed on text it cannot see.
    gate = any(t.rx for t in blocked)
    unseen = next((v for k, v in meta if k == "UNSEEN"), None)
    if gate and unseen is not None:
        return deny(say("pt_unseen", guard=NAME, unseen=unseen, to_private=TO_PRIVATE))
    opaque = next((v for k, v in meta if k == "OPAQUE"), None)
    if gate and opaque is not None:
        what, value = opaque
        return deny(say("pt_opaque", guard=NAME, what=what, opaque=value))
    kinds = {k for k, _ in meta}
    if gate and "HEREDOC" not in kinds and "STDIN" in kinds:
        return deny(say("pt_stdin", guard=NAME))

    # Replayed in command order, so a cd or an assignment before a path applies to it.
    home = env.get("HOME") or ""
    rp = _Replay(cwd, home)
    hfed = [v for k, v in meta if k == "HFED" and v]
    text_file, files, bad = "", [], None
    for kind, a in meta:
        if kind == "CDTO":
            rp.vcwd = "" if a == "-" else (rp.resolve(a) or "")
            continue
        if kind == "CDPUSH":
            rp.stack.append(rp.vcwd)
            continue
        if kind == "CDPOP":
            rp.vcwd = rp.stack.pop() if rp.stack else ""   # a ) whose ( was never seen: somewhere unseen
            continue
        if kind == "A":
            name, _, value = a.partition("=")
            rp.vars[name] = rp.expand(value)
            continue
        if kind == "FX" and ("$" in a or not a.startswith("/")):
            bad = a
            continue
        if kind not in ("F", "FX"):
            continue
        f = rp.resolve(a)
        if f is None:
            bad = a
            continue
        try:
            body = yield Need("read", f)
        except Exception:  # noqa: BLE001
            # A file this command writes from a heredoc need not exist yet: its text
            # is already in the scanned command.
            if not any(rp.resolve(h) == f for h in hfed):
                bad = f
            continue
        text_file += body + "\n"
        files.append(f)
    if gate and bad is not None:
        return deny(say("pt_body_file", guard=NAME, bad=bad))

    # The hard block reads the text as written, before any redaction.
    found = terms.hits(text_cmd + text_file, blocked)
    if found:
        return deny(say("pt_hits", guard=NAME, hits=terms.named(found), to_private=TO_PRIVATE))

    posted = _strings(ti) if tool != "Bash" else [v for k, v in meta if k in ("T", "HDTXT")]
    if not any(terms.redact(v, applied) != v for v in posted + [text_file]):
        return None
    # A redaction rewrites the call, never a file's contents.
    if terms.redact(text_file, applied) != text_file:
        return deny(say("pt_file_redact", guard=NAME, files=", ".join(files), changes=_changes([text_file], applied),
                        to_private=TO_PRIVATE))
    if tool != "Bash":
        return allow(say("pt_redacted", guard=NAME, changes=_changes(posted, applied)),
                     _walk(ti, lambda v: terms.redact(v, applied)))
    new = _rewrite_posted(doc, ti["command"], meta, applied)
    if new is None:
        return deny(say("pt_by_hand", guard=NAME, changes=_changes(posted, applied)))
    return allow(say("pt_redacted", guard=NAME, changes=_changes(posted, applied)), {**ti, "command": new})


def _shell(put):
    """put as a bare shell word reads it back: every character it would act on, escaped."""
    return re.sub(r"[^\w./:@%+=,-]", lambda m: "\\" + m.group(), put)


def _rewrite_posted(doc, cmd, meta, applied):
    """cmd with the pairs applied to its posted values (T, HDTXT), or None when that cannot be
    shown safe. Each distinct posted text is found in cmd (its spaces standing for any
    whitespace, as the scanner flattens a newline) and must occur exactly as often as it is
    posted: a copy elsewhere is not ours to touch. The result is scanned again; it must post
    the redacted text and leave every other record as it was. A bare word gets its puts
    escaped (`\\~`), which the shell reads back; the first rescan shows which values are bare
    (the scanner drops the backslash there)."""
    posted = [(k, v) for k, v in meta if k in ("T", "HDTXT")]
    texts = {v for _, v in posted if terms.redact(v, applied) != v}
    pats = {v: re.compile(r"\s+".join(re.escape(w) for w in v.split(" "))) for v in texts}
    for v, pat in pats.items():
        if len(pat.findall(cmd)) != sum(1 for _, x in posted if x == v):
            return None

    def build(mode):
        out = cmd
        for v, pat in pats.items():
            out = pat.sub(lambda m, esc=mode[v]: terms.redact(m.group(0), applied, esc), out)
        return out

    scanned = {}

    def again(c):
        if c not in scanned:
            scanned[c] = rescan(c)
        return scanned[c]

    def rescan(c):
        d = type(doc)({**doc.payload, "tool_input": {**doc.payload["tool_input"], "command": c}}, doc.env)
        m = _Meta(d, c).out
        return [(k, v) for k, v in m if k in ("T", "HDTXT")], [r for r in m if r[0] not in ("T", "HDTXT")]

    other = [r for r in meta if r[0] not in ("T", "HDTXT")]
    mode = {v: _shell for v in texts}
    got, rest = again(build(mode))
    if rest != other or [k for k, _ in got] != [k for k, _ in posted]:
        return None
    seen = {}
    for (_, v), (_, g) in zip(posted, got):
        if v in texts:
            bare = g == terms.redact(v, applied)
            if not bare and g != terms.redact(v, applied, _shell) or seen.setdefault(v, bare) != bare:
                return None
            if not bare:
                mode[v] = None
    new = build(mode)
    got, rest = again(new)
    if rest != other or got != [(k, terms.redact(v, applied) if v in texts else v) for k, v in posted]:
        return None
    return new.rstrip("\n")


def _strings(v):
    """Every string in v, depth first, as jq's `.. | strings` lists them."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        v = list(v.values())
    return [s for x in v for s in _strings(x)] if isinstance(v, list) else []


def _walk(v, f):
    if isinstance(v, str):
        return f(v)
    if isinstance(v, dict):
        return {k: _walk(x, f) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk(x, f) for x in v]
    return v
