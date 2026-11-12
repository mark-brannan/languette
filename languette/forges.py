"""The forges' words: a gh or glab call's verb, repo flag, method and `gh api`
fields, and the forge and repo a git remote's URL names (docs/design/forges.md).
"""

import re
from collections import namedtuple

from .quoting import UNREADABLE
from .lexer import word


PAGE = 100                                     # the largest page GitHub's and GitLab's APIs serve; one is read


# gh command words, as the guards that read a gh command share them: the verb,
# the repo a -R/--repo flag names, and `gh api`'s method, fields and endpoint.
# The *_flag and gh_api_arg readers read one word at a time, so a guard's own
# walk keeps its own flags; gh_api reads a whole `gh api` call.

# The flag that names the repo; its value is the next word unless glued on.
GH_REPO_FLAGS = ("-R", "--repo")

# The flag that sets `gh api`'s HTTP method.
GH_METHOD_FLAGS = ("-X", "--method")

# `gh api`'s field flags: -f/--raw-field send a string, -F/--field a typed
# value, where @path sends the file's contents.
GH_API_FIELDS = ("-f", "-F", "--field", "--raw-field")

# The GraphQL endpoint as gh_api_path leaves it: graphql, or an Enterprise
# server's api/graphql when the call names the URL (api/v3/graphql read as one).
GRAPHQL = re.compile(r"(?:api/(?:v3/)?)?graphql")

# A query GraphQL can only run as a read: the shorthand `{` must be the lone
# operation, and a named `query` takes a second operation only by operationName.
GRAPHQL_READ = re.compile(r"\s*(?:\{|query(?![A-Za-z0-9_]))")

# A GraphQL document that runs a mutation; read loosely, so a read that only
# mentions the word counts as a write.
_MUTATION = re.compile(r"(?<![A-Za-z0-9_])mutation(?![A-Za-z0-9_])")

# `gh api` flags whose value no guard reads.
GH_API_VALUED = frozenset("-H --header -q --jq -t --template -p --preview --hostname --cache".split())
# Every `gh api` flag that takes the next word as its value.
GH_API_VALUE = frozenset(GH_REPO_FLAGS + GH_METHOD_FLAGS + GH_API_FIELDS + ("--input",)) | GH_API_VALUED

# `glab api` reads its words as `gh api` does, but for these: --form sends a
# field too, and these flags' values no guard reads. It takes no -R.
GLAB_API_FIELDS = GH_API_FIELDS + ("--form",)
GLAB_API_VALUED = frozenset("-H --header --hostname --output --placeholder".split())

# The forges, a row each (docs/design/forges.md): the client an agent runs,
# the host the service answers on and the other names a remote's URL gives it,
# the first label of a self-hosted install's host (gitlab.example.com), and
# the shape of a repo's path there.
FORGES = {
    "github": {"cli": "gh", "host": "github.com", "aliases": ("ssh.github.com", "www.github.com"), "label": None,
               "repo": re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")},
    "gitlab": {"cli": "glab", "host": "gitlab.com", "aliases": ("altssh.gitlab.com", "www.gitlab.com"),
               "label": "gitlab", "repo": re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+")},
}
# A remote's URL: scheme://[user@]host[:port]/path, or scp-like [user@]host:path.
_REMOTE_URL = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]*@)?(?P<url>[^/:@]+)(?::\d*)?/"
                         r"|(?:[^@/:]*@)?(?P<scp>[^/:@]+):)(?P<path>.+)\Z")

Remote = namedtuple("Remote", "forge host repo")


def remote(url):
    """The Remote a git remote's URL names: forge, a FORGES key; host, lower-cased, an
    alias read as the forge's host; repo, its path less .git and slashes, in the forge's
    repo shape. None when the URL names no host, no row's host fits it, or the path is
    not a repo there."""
    m = _REMOTE_URL.match((url or "").strip())
    if not m:
        return None
    host = (m["url"] or m["scp"]).lower()
    repo = re.sub(r"\.git\Z", "", m["path"].strip("/"))
    for forge, row in FORGES.items():
        if host in row["aliases"]:
            host = row["host"]
        if host == row["host"] or row["label"] and host.split(".")[0] == row["label"] and "." in host:
            ok = row["repo"].fullmatch(repo) and not {".", ".."} & set(repo.split("/"))
            return Remote(forge, host, repo) if ok else None
    return None


def _flag(s, i, hi, names, default):
    """(name, value, index of the flag's last word) for flag_value."""
    t = word(s, i)
    if t in names:
        return (t, word(s, i + 1), i + 1) if i < hi else (t, default, i)
    for n in names:
        if n.startswith("--") and t.startswith(n + "="):
            return n, t[len(n) + 1:], i
        if len(n) == 2 and not t.startswith("--") and t.startswith(n) and len(t) > 2:
            return n, t[3:] if t[2] == "=" else t[2:], i
    return None


def flag_value(s, i, hi, names, default=None):
    """(value, index of the flag's last word) when word i is one of the flags
    `names` in any spelling pflag reads: the flag then its value (`default`
    when that would pass hi), --long=value, or a short flag with its value
    glued on (-bvalue, -b=value). Else None."""
    got = _flag(s, i, hi, names, default)
    return got[1:] if got else None


Flag = namedtuple("Flag", "at name value live tilde")
Flag.__doc__ = """One word, or one flag with its value, of a call's words (flag_words). at: the
flag's first word; name: the flag as `names` spells it, None for a word that is none
of them; value: the flag's value (None when no word is left for it), or the word
itself; live: the value's word is live; tilde: a leading ~ in the value is the home
directory, as the shell expands it: only at the start of an unquoted word, so never in
a glued --body-file=~/b.md or -F~/b.md, where gh opens a directory named ~."""


def flag_words(s, lo, hi, names):
    """A Flag per word lo..hi: each flag in `names`, read by flag_value with its value
    taken with it, and every other word as itself."""
    i = lo
    while i <= hi:
        got = _flag(s, i, hi, names, None)
        if got is None:
            yield Flag(i, None, word(s, i), s.live[i], not s.quoted[i])
        else:
            name, v, j = got
            yield Flag(i, name, v, s.live[j], j > i and not s.quoted[j])
            i = j
        i += 1


def gh_env_repo(s, lo, g, cli="gh"):
    """The repo a GH_REPO= (GITLAB_REPO= for glab) assignment before word g
    names, the last one as the shell reads them; or None."""
    env = "GITLAB_REPO=" if cli == "glab" else "GH_REPO="
    return next((s.w[i][len(env):] for i in range(g - 1, lo - 1, -1)
                 if s.k[i] == "w" and s.w[i].startswith(env)), None)


def gh_repo(s, lo, g, hi, cli="gh"):
    """The repo a gh or glab call at word g names: its last -R/--repo flag in
    g+1..hi, else its GH_REPO= (gh_env_repo); or None."""
    repo, i = gh_env_repo(s, lo, g, cli), g + 1
    while i <= hi:
        if r := gh_repo_flag(s, i, hi, repo):
            repo, i = r
        i += 1
    return repo


def gh_verb(s, i, hi):
    """The index of the first word at or after i that is no flag, -R/--repo
    taking the word after it; or None."""
    while i <= hi:
        t = word(s, i)
        if t in GH_REPO_FLAGS:
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return i
    return None


def gh_repo_flag(s, i, hi, default=None):
    """(repo, index of its last word) when word i is -R/--repo in any spelling
    (-R x, -Rx, --repo x, --repo=x); repo is `default` when its value would
    pass hi. Else None."""
    return flag_value(s, i, hi, GH_REPO_FLAGS, default)


def gh_method_flag(s, i, hi, default=""):
    """(method upper-cased, index of its last word) when word i of `gh api` sets
    the HTTP method (-X M, -XM, -X=M, --method M, --method=M); method is
    `default` when its value would pass hi. Else None."""
    got = flag_value(s, i, hi, GH_METHOD_FLAGS)
    if not got:
        return None
    return (default if got[0] is None else got[0]).upper(), got[1]


class GhArg(namedtuple("GhArg", "flag text live tilde")):
    """A `gh api` argument that sends data: a field or --input. flag is the
    flag's name as gh spells it (-f, -F, --field, --raw-field, --input); text
    the word it carries, key=value or --input's source, None when no word is
    left for it; live is that word's; tilde: a leading ~ in the source the
    shell expands, only --input's own unquoted word (never after `@` or `=`)."""

    @property
    def key(self):
        return "" if self.flag == "--input" else (self.text or "").partition("=")[0]

    @property
    def value(self):
        """A field's value: what follows the first =, "" without one."""
        return (self.text or "").partition("=")[2]

    @property
    def typed(self):
        """-F/--field: gh reads an @path value from the file."""
        return self.flag in ("-F", "--field")


def gh_api_arg(s, i, hi, fields=GH_API_FIELDS):
    """(GhArg, index of its last word) when word i of `gh api` is a field or
    --input flag, in any spelling pflag reads: -f k=v, -fk=v, -f=k=v,
    --field k=v, --field=k=v, --input p, --input=p. Else None. `fields` is
    the client's field flags (GLAB_API_FIELDS for `glab api`)."""
    t = word(s, i)
    if t in fields or t == "--input":
        if i >= hi:
            return GhArg(t, None, False, False), i
        return GhArg(t, word(s, i + 1), s.live[i + 1], t == "--input" and not s.quoted[i + 1]), i + 1
    if t[:2] in ("-f", "-F") and len(t) > 2:
        return GhArg(t[:2], t[3:] if t[2] == "=" else t[2:], s.live[i], False), i
    for flag in [f + "=" for f in fields if f.startswith("--")] + ["--input="]:
        if t.startswith(flag):
            return GhArg(flag[:-1], t[len(flag):], s.live[i], False), i
    return None


class GhApi(namedtuple("GhApi", "path operands method args flags skipped")):
    """A `gh api` call's words. path: the endpoint (gh_api_path of the first
    operand that is not empty, "" when none); operands: the words that are
    neither a flag nor a flag's value; method: upper-cased, "" when unset;
    args: a GhArg per field and --input, in command order; flags: every other
    flag word; skipped: the indices of the words that are the method's value or
    a GH_API_VALUED flag's."""

    @property
    def sends(self):
        """A field or --input is given, with a value or not: gh sends a body,
        and with no method set, sends it as a POST."""
        return bool(self.args)

    @property
    def sent(self):
        """The HTTP method gh sends: the one set, else POST with a body, GET without."""
        return self.method or ("POST" if self.sends else "GET")

    @property
    def graphql(self):
        """The endpoint is the GraphQL one, on github.com or an Enterprise server."""
        return bool(GRAPHQL.fullmatch(self.path))

    def _query_arg(self):
        """The query field when the command's words hold it: no --input, no @file."""
        if any(a.flag == "--input" for a in self.args):
            return None
        q = next((a for a in self.args if a.key == "query"), None)
        return None if q is None or (q.typed and q.value.startswith("@")) else q

    @property
    def query(self):
        """The GraphQL query as the command's words write it out, or None when
        they do not: no query field, an --input, an @file, or a value built at
        run time."""
        q = self._query_arg()
        return None if q is None or (q.live and re.search(r"[$`]", q.value)) else q.value

    @property
    def writes(self):
        """Whether the call changes something on the forge. GraphQL: True when
        the query runs a mutation, None when the query is not written out (see
        `query`), else False; a query that can only run as a read (GRAPHQL_READ,
        with no operationName) is False however much of it is built at run
        time. Any other endpoint: any method sent but GET and HEAD."""
        if self.graphql:
            if not any(a.flag == "--input" or a.key == "query" or (a.live and re.search(r"[$`]", a.key))
                       for a in self.args):
                return False   # no query is sent (no field name built at run time either): nothing can run
            q = self._query_arg()
            if q is not None and GRAPHQL_READ.match(q.value) and not any(a.key == "operationName" for a in self.args):
                return False
            text = self.query
            return None if text is None else bool(_MUTATION.search(text))
        return self.sent not in ("GET", "HEAD")


def gh_api(s, lo, hi, cli="gh"):
    """The GhApi of `gh api`'s words lo..hi, the words after `api`; `glab api`'s
    when `cli` is "glab"."""
    fields, valued = (GLAB_API_FIELDS, GLAB_API_VALUED) if cli == "glab" else (GH_API_FIELDS, GH_API_VALUED)
    method, operands, args, flags, skipped = "", [], [], [], set()
    i = lo
    while i <= hi:
        t = word(s, i)
        if m := gh_method_flag(s, i, hi, method):
            method, j = m
            skipped.update(range(i + 1, j + 1))
            i = j
        elif a := gh_api_arg(s, i, hi, fields):
            arg, i = a
            args.append(arg)
        elif t in valued:
            skipped.add(i + 1)
            i += 1
        elif t.startswith("-"):
            flags.append(t)
        else:
            operands.append(t)
        i += 1
    path = gh_api_path(next((o for o in operands if o), ""))
    return GhApi(path, tuple(operands), method, tuple(args), tuple(flags), frozenset(skipped))


def gl_project(p):
    """The project a glab api path names, read: "-" for :id (the cwd's), "?" for a numeric
    id or a word the shell would still expand (no path to look up), else group/project."""
    return "-" if p == ":id" else "?" if p.isdigit() or UNREADABLE.search(p) else p


def gh_api_path(path):
    """The endpoint a `gh api` path argument names: any https://host/ prefix,
    leading slashes, a ?query or #fragment, and trailing slashes dropped
    (repos/o/r/issues)."""
    path = re.split(r"[?#]", re.sub(r"^https?://[^/]+/", "", path, count=1), maxsplit=1)[0]
    return path.strip("/")


def norm_repo(r):
    """owner/name in lower case from any of the spellings gh and git accept."""
    r = r.lower()
    for pat in (r"^[a-z]*://[^/]*/", r"^[^@/]*@[^:]*:", r"^github\.com/", r"\.git$", r"/*$"):
        r = re.sub(pat, "", r, count=1)
    return r
