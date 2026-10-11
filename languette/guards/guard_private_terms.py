"""guard-private-terms: text bound for a public GitHub repo is checked against
the user's private terms file. The spec is features/guard-private-terms.feature.

Once a private term is in a public issue or PR it is in GitHub's history and
every mirror of it; the undo is a support ticket, not an edit. So the check
sits at the moment the text leaves the machine.

Fires on Bash `gh issue|pr create|comment|edit|review|close|reopen|merge`,
`gh api` writing to repos/*/*/issues|pulls or a graphql mutation that comments
on or opens an issue or PR, and the GitHub MCP tools that create or edit an
issue, PR, comment or review. A body posted from a script file, `curl` or
`python -c` is not seen. The text judged is only what is posted: literal
--body/--title/--comment/--subject/--label values, gh api field values, every
heredoc body, and the contents of a --body-file/--comment-file/-F/--input file,
never its path; for MCP, every string in tool_input. Each term is matched
case-insensitively as plain text, and the reason names the terms that hit.

A home-directory path in the text is sanitized, not denied: rewritten to `~`
and allowed, unless it sits in a file's contents, which a rewrite cannot reach.

The target repo is --repo/-R, GH_REPO=, a positional URL or owner/repo#n, the
gh api path, or MCP owner/repo; failing those, the origin of the cwd, unless
the command runs a `cd`. A graphql mutation's repo is unknown. Unknown is
scanned; only when every target is in private_repos does the text go unscanned.

Inert with private_terms_file unset or empty. Once it is set, fails closed: a
terms file unreadable or empty, a body built at run time that no heredoc feeds,
stdin with no heredoc, a file it cannot read, or a flag whose shape says it
carries text but is not one it knows -> deny, with the fix in the reason.
"""

import re

from languette import scan as sw
from languette.verdict import Need, allow, deny

NAME = "guard-private-terms"
_MCP = ("create_issue|update_issue|issue_write|add_issue_comment|create_pull_request|update_pull_request|"
        "add_pull_request_review_comment|create_pull_request_review|pull_request_review_write|"
        "add_comment_to_pending_review|create_and_submit_pull_request_review|submit_pending_pull_request_review|"
        "add_reply_to_pull_request_comment|update_issue_comment")
# The tools hooks.json wires this guard to; the MCP ones by their name's tail.
TOOLS = re.compile(rf"(?:Bash|mcp__.*__(?:{_MCP}))\Z")
_MCP_TOOL = re.compile(rf"mcp__.*__(?:{_MCP})\Z")
GH = re.compile(r"(?:^|/)gh\Z")
TO_PRIVATE = "target a repo listed in the private_repos option"
_UNSEEN = re.compile(r"--[A-Za-z-]*(?:body|comment|message)[A-Za-z-]*")
_ACTS = frozenset("create comment edit review close reopen merge".split())
_SKIP_VALUE = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
_GRAPHQL = re.compile(r"addComment|createIssue|updateIssue|createPullRequest|updatePullRequest|"
                      r"addPullRequestReview|submitPullRequestReview|addDiscussionComment")
_BACKSTOP = re.compile(r"(?:^|[^A-Za-z0-9_./-])gh\s+(?:issue|pr)\s+(?:create|comment|edit|review|close|reopen|merge)(?:\s|$)",
                       re.M)
_NAME_CHAR = "A-Za-z0-9_.-"


def _deny(why):
    return deny(f"{NAME}: {why}")


def _flat(t):
    return t.replace("\n", " ")


def _unq(t):
    return t.replace('"', "").replace("'", "")


def writes(b, heredoc_only):
    """The file paths `b` writes with a redirection or `tee`, heredoc bodies
    skipped; with heredoc_only, only those on a line that opens a heredoc --
    the paths whose content is the heredoc body. Quotes are stripped; a path
    built from $VAR comes back unresolved."""
    out, delim = [], ""
    for line in b.split("\n"):
        if delim:
            if re.fullmatch(r"[ \t]*" + re.escape(delim) + r"[ \t]*", line):
                delim = ""
            continue
        m = re.search(r"""<<-?[ \t]*["']?[A-Za-z_][A-Za-z0-9_]*["']?""", line)
        if m:
            delim = _unq(re.sub(r"^<<-?[ \t]*", "", m.group()))
            pre = line[:m.start()]
        else:
            pre = line
        if heredoc_only and not m:
            continue
        pre = re.sub(r"[;|&]", " ; ", pre)
        pre = re.sub(r">>?", " @redir@ ", pre)
        t = [x for x in re.split(r"[ \t]+", pre) if x != ""]
        teeing = False
        for x, tok in enumerate(t):
            if tok == ";":
                teeing = False
                continue
            if tok == "@redir@":
                if x + 1 < len(t) and t[x + 1] not in (";", "@redir@"):
                    out.append(_unq(t[x + 1]))
                continue
            if _unq(tok) == "tee":
                teeing = True
                continue
            if teeing and not tok.startswith("-"):
                out.append(_unq(tok))
    return out


class _Meta:
    """The command's records, in command order, as (kind, value):
    R repo (- = the cwd's, ? = unknown) | T posted text | HDTXT heredoc text |
    F / FX file (FX: in nested text) | CDTO dir | CDPUSH / CDPOP | A NAME=VALUE |
    HFED path a heredoc writes | STDIN | OPAQUE value | HEREDOC | CD | UNSEEN flag."""

    def __init__(self, doc, command):
        self.out = []
        buf = self.orig = command + "\n"
        counts = {}
        for p in writes(buf, False):
            counts[p] = counts.get(p, 0) + 1
        for p in writes(buf, True):
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

    def wv(self, i):
        return self.s.q[i] if self.s.k[i] == "q" else self.s.w[i]

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

    def val(self, v, live):
        """A posted value: text, or OPAQUE when built at run time and no heredoc on
        the value itself feeds it."""
        if not live:
            self.add("T", _flat(v))                  # single-quoted: posted verbatim
        elif "$(" in v or "`" in v:
            if "<<" not in v and " HEREDOC " not in v:
                self.add("OPAQUE", _flat(v))
        elif re.match(r"\$[A-Za-z_{]", v):
            if not self.fed(v):
                self.add("OPAQUE", _flat(v))
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
        self.val(v, live)

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
                        t = self.wv(i + 1)
                    break
                if not re.match(r"[-+].", s.w[i]):
                    t = self.wv(i)
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
        g = sw.cmd_index(s, lo, hi, GH, nested)
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
            t = self.wv(i)                       # a glued flag+quoted-value token may not be kind "w"
            live = s.live[i]
            if t in ("--repo", "-R"):
                if i < hi:
                    i += 1
                    repo = self.wv(i)
            elif t.startswith("--repo="):
                repo = t[7:]
            elif t.startswith("-R") and len(t) > 2:
                repo = t[2:]
            elif t in ("--body-file", "--comment-file", "-F"):
                if i < hi:
                    i += 1
                    self.file(self.wv(i))
            elif t.startswith("--body-file="):
                self.file(t[12:])
            elif t.startswith("--comment-file="):
                self.file(t[15:])
            elif t.startswith("-F") and len(t) > 2:
                self.file(t[2:])
            elif t in ("--body", "--title", "--comment", "--subject", "-b", "-t", "-c"):
                if i < hi:
                    i += 1
                    self.val(self.wv(i), s.live[i])
            elif re.match(r"--(?:body|title|comment|subject)=", t):
                self.val(t.split("=", 1)[1], live)
            elif re.match(r"-[btc].", t):
                self.val(t[2:], live)
            elif t in ("--label", "--add-label", "-l"):
                if i < hi:
                    i += 1
                    self.lab(self.wv(i))
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
        s = self.s
        path, method, fields = "", "", False
        i = g + 2
        while i <= hi:
            t = self.wv(i)
            if t in ("-X", "--method"):
                if i < hi:
                    i += 1
                    method = s.w[i].upper()
            elif t.startswith("--method="):
                method = t[9:].upper()
            elif t.startswith("-X") and len(t) > 2:
                method = t[2:].upper()
            elif t in ("-f", "-F", "--field", "--raw-field"):
                fields = True
                if i < hi:
                    i += 1
                    self.field(self.wv(i), s.live[i])
            elif re.match(r"-[fF].", t):
                fields = True
                self.field(t[2:], s.live[i])
            elif re.match(r"--(?:field|raw-field)=", t):
                fields = True
                self.field(t.split("=", 1)[1], s.live[i])
            elif t == "--input":
                fields = True
                if i < hi:
                    i += 1
                    self.file(self.wv(i))
            elif t.startswith("--input="):
                fields = True
                self.file(t[8:])
            elif t in _SKIP_VALUE:
                i += 1
            elif _UNSEEN.match(t):
                self.add("UNSEEN", _flat(t))
            elif t.startswith("-"):
                pass
            elif path == "":
                path = t
            i += 1
        p = re.sub(r"^/+", "", re.sub(r"^https?://[^/]+/", "", path, count=1), count=1)
        if re.match(r"repos/[^/]+/[^/]+/(?:issues|pulls)(?:/|\Z)", p):
            if method in ("GET", "HEAD") or (method == "" and not fields):
                return
            parts = p.split("/")
            self.add("R", parts[1] + "/" + parts[2])
        elif p == "graphql":
            if any(_GRAPHQL.search(self.wv(i)) for i in range(g, hi + 1)):
                self.add("R", "?")          # the target is a node id in the query, never the cwd's origin


def norm_repo(r):
    """owner/name in lower case from any of the spellings gh and git accept."""
    r = r.lower()
    for pat in (r"^[a-z]*://[^/]*/", r"^[^@/]*@[^:]*:", r"^github\.com/", r"\.git$", r"/*$"):
        r = re.sub(pat, "", r, count=1)
    return r


def _is_private(repo, env):
    if not repo:
        return False
    listed = env.get("CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS") or ""
    return any(r.strip() and norm_repo(r.strip()) == repo for r in listed.split(","))


def normpath(p):
    out = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out:
                out.pop()
            continue
        out.append(seg)
    return "/" + "/".join(out)


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
            return normpath(p)
        return normpath(self.vcwd + "/" + p) if self.vcwd else None


def check(doc):
    payload, env = doc.payload, doc.env
    terms_file = env.get("CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE") or ""
    if not terms_file:
        return None                              # inert until the user names a terms file
    tool = payload.get("tool_name")
    if not isinstance(tool, str) or not tool:
        return None
    cwd = payload["cwd"]
    ti = payload.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
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
        if not _is_private(norm_repo(repo), env):
            all_private = False
    if all_private:
        return None

    unseen = next((v for k, v in meta if k == "UNSEEN"), None)
    if unseen is not None:
        return _deny(f"the flag `{unseen}` looks like it carries text to post, but this hook doesn't recognise its "
                     "shape and cannot see what it holds. Recognised: --body/--title/--comment/--subject (or "
                     "-b/-t/-c), --body-file/--comment-file/-F/--input <path>, --label/--add-label, gh api "
                     f"-f/-F/--field/--raw-field. Use one of those, or {TO_PRIVATE}.")
    try:
        listed = yield Need("read", terms_file)
    except Exception:  # noqa: BLE001
        return _deny(f"the private-terms file ({terms_file}), set as the private_terms_file option, is unreadable, "
                     "so text bound for a public repo cannot be checked. Fix the path in the plugin's "
                     "private_terms_file option (/plugin configure languette@languette), or clear the option to "
                     f"turn the check off. To post without the check, {TO_PRIVATE}.")
    terms = [t for t in (line.strip() for line in listed.split("\n")) if t and not t.startswith("#")]
    if not terms:
        return _deny(f"the private-terms file ({terms_file}) is readable but has no terms in it -- only comments "
                     "and blank lines, or nothing at all. An empty list matches nothing, so every post would pass "
                     "unchecked, which is indistinguishable from a check that ran. Populate it (one term per line, "
                     f"# for comments) and retry. To post without the check, {TO_PRIVATE}.")
    opaque = next((v for k, v in meta if k == "OPAQUE"), None)
    if opaque is not None:
        return _deny(f"the body or title is built at run time ({opaque}) and no heredoc in this command feeds it, "
                     "so its text cannot be checked before it is posted. Write it literally, in a heredoc in the "
                     "same command, or in a file and pass --body-file <path>.")
    kinds = {k for k, _ in meta}
    if "HEREDOC" not in kinds and "STDIN" in kinds:
        return _deny("the body comes from stdin (-F - / --input -) and there is no heredoc in the command, so it "
                     "cannot be checked. Put the text in a heredoc in the same command, or in a file and pass "
                     "--body-file <path>.")

    # Replayed in command order, so a cd or an assignment before a path applies to it.
    home = env.get("HOME") or ""
    rp = _Replay(cwd, home)
    hfed = [v for k, v in meta if k == "HFED" and v]
    text_file, bad = "", None
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
    if bad is not None:
        return _deny(f"--body-file {bad} cannot be read, so the text about to be posted cannot be checked. Write it "
                     "to that same path from a heredoc in this same command (cat > PATH <<EOF ... EOF, or tee PATH "
                     "<<EOF) -- the gate reads the heredoc body directly, so the file need not exist yet. Otherwise "
                     "create the file in an earlier command and retry. The path is resolved with the $VARs this "
                     "same command assigns before it, after any cd in it, with . and .. collapsed; a variable set in "
                     "an earlier command is invisible here, so spell the path out.")

    text = text_cmd + text_file
    low = text.lower()
    if not any(t.lower() in low for t in terms):
        return None

    # The home directory is a sanitization job: the path belongs in posted text as
    # `~`. A hit inside a file's contents does not qualify: rewriting tool_input
    # never touches the file on disk.
    if home and home in text and home not in text_file:
        # Only where $HOME stands as a whole path component, so /home/u2 is left alone.
        home_re = re.compile(rf"(?<![{_NAME_CHAR}]){re.escape(home)}(?![{_NAME_CHAR}])")
        if not any(t.lower() in home_re.sub("~", text).lower() for t in terms):
            if tool == "Bash":
                return allow({"command": home_re.sub("~", ti["command"]).rstrip("\n")})
            return allow(_walk(ti, lambda v: home_re.sub("~", v)))

    hits = [t for t in terms if t.lower() in low]
    return _deny(f"the text about to be posted to a public repo contains private term(s) from the denylist: "
                 f"{', '.join(hits)}. Private detail does not go on public GitHub, ever -- it stays in GitHub's "
                 f"history. Either {TO_PRIVATE} and link it from here, or rewrite the body without the term. Do "
                 "not paraphrase it into something recognisable.")


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
