"""Secret detection: which words of a parsed command are a secret (#95).

One detector, shared by guard-secrets (which reports its findings to the
verdict) and any writer that records commands (which masks them). Pure: it
reads a Scan's words and returns Findings; no I/O, no clock.

Three layers, in the order prior art (gitleaks, detect-secrets) uses them:

- shape: a word holds a vendor-prefixed or fixed-format token
  (secret_rules.RULES, ported from gitleaks, plus the caller's own rules);
- context: the word is `KEY=value`, `Key: value` (a data line's indent, an
  `export` and quotes around key or value set aside) or follows an option that
  names a credential (`--password`, `--token`, `-u user:pass`), or is a URL
  with a password;
- entropy: only confirms a shape or context hit, never fires alone, so
  `GITHUB_TOKEN=ghp_xxxxxxxx...` (a placeholder) is no finding.

A finding names the word by index, so a writer redacts by position in the
word stream, never by regex over the raw text. Standard library only.
"""

import math
import re
from collections import namedtuple

from languette import secret_rules

# how: "shape" (a known token format) or "context" (named as a credential).
# rule: the rule id ("github-pat", "context:--password", "context:url").
# span: (start, end) of the secret within the word's text, for redaction.
Finding = namedtuple("Finding", "index rule how span")

Rule = secret_rules.Rule

MIN_LEN = 8          # a context value shorter than this is not judged a secret
MIN_ENTROPY = 3.0    # bits per character, Shannon; gitleaks' usual floor

# A key that names a credential, as the whole key or its last underscore-,
# dash- or camelCase-separated part: TOKEN, GITHUB_TOKEN, db-password,
# githubToken. The camelCase boundary is case-sensitive, so `bypass` and
# `compass` are not a `pass`.
_KEY = re.compile(r"(?:^|[_.-]|(?<=[a-z])(?=[A-Z]))"
                  r"(?i:secret|token|passw(?:or)?d|pass|pwd|api[_-]?key|apikey|access[_-]?key|"
                  r"private[_-]?key|auth|authorization|credentials?|client[_-]?secret|secret[_-]?key|"
                  r"access[_-]?token|refresh[_-]?token|session[_-]?key|signing[_-]?key|cookie)$")
# `KEY=value` or `Key: value`, after a data line's indent and an optional
# export/set/setenv; the key may sit in one pair of matching quotes.
_PAIR = re.compile(r"""^\s*(?:(?:export|set|setenv)\s+)?(["']?)([^=:\s"']+)\1\s*[=:]\s*""")
# Options whose next word, or whose =value, is a credential. Short options
# (-p) are too many other things (mkdir -p, ssh -p) to be read this way.
_OPTS = frozenset("--password --passwd --pass --token --secret --api-key --apikey --access-key --client-secret "
                  "--auth-token --access-token --private-key --secret-key".split())
# Options whose next word is `user:password` (curl -u); the part after the
# colon is the credential. Without a colon (sudo -u root, id -u) it is a user.
_USER_OPTS = frozenset("-u --user --username --userinfo".split())
# A header value's scheme word, dropped before the value is judged.
# Unanchored: _value_span matches it at a position, where `^` would not.
_SCHEME = re.compile(r"(?i)(?:bearer|basic|token|apikey)\s+")
# user:password@ in a URL; the password is the secret.
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@")
# A value that is clearly not a literal secret: a variable, a placeholder, a path.
_NOT_LITERAL = re.compile(r"^(?:\$|<|\{|\.{2,}$|/|~/)")


def entropy(s):
    """Shannon entropy of s in bits per character; 0.0 for the empty string."""
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _secret_of(rule, m):
    return m.span("secret") if "secret" in rule.regex.groupindex and m.group("secret") is not None else m.span(0)


def _shapes(text, rules):
    """[(rule_id, span)] of every known shape in text whose secret clears the
    rule's entropy floor, in order of start. A span overlapping one already
    taken (an earlier rule's, or an earlier match's) is dropped, and so is an
    empty one."""
    hits = []
    for rule in rules:
        for m in rule.regex.finditer(text):
            a, b = _secret_of(rule, m)
            if a == b or any(a < y and x < b for _, (x, y) in hits):
                continue
            if entropy(text[a:b]) >= rule.entropy:
                hits.append((rule.id, (a, b)))
    return sorted(hits, key=lambda h: h[1][0])


def _value_span(text, start, end=None):
    """(start, end) of the value at text[start:end], scheme word and one pair
    of matching quotes dropped, or None when it does not read as a literal
    secret."""
    end = len(text) if end is None else end
    m = _SCHEME.match(text, start, end)
    if m:
        start = m.end()
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end - start >= 2 and text[start] in "'\"":
        close = text.find(text[start], start + 1, end)
        if close != -1:
            start, end = start + 1, close
    v = text[start:end]
    if not v or _NOT_LITERAL.match(v) or len(v) < MIN_LEN or entropy(v) < MIN_ENTROPY:
        return None
    return start, end


def _context(text, prev):
    """(rule_id, span) when text is named as a credential by its own key, by
    the option before it, or as a URL password; else None."""
    m = _URL.search(text)
    if m and entropy(m.group(1)) >= MIN_ENTROPY and not _NOT_LITERAL.match(m.group(1)):
        return "context:url", m.span(1)
    if prev in _OPTS:
        span = _value_span(text, 0)
        if span:
            return f"context:{prev}", span
    if prev in _USER_OPTS:
        m = re.match(r"^[^:\s]+:(.+)$", text)
        span = m and _value_span(text, m.start(1))
        if span:
            return f"context:{prev}", span
    m = _PAIR.match(text)
    if m:
        key = m.group(2)
        if key in _OPTS or _KEY.search(key):
            span = _value_span(text, m.end())
            if span:
                return f"context:{key}", span
    return None


class Text:
    """A heredoc body or other data read as lines, not as shell: each line is
    one quoted word, so a PEM header keeps its spaces and `KEY=value` on a
    line of .env reads as the word it is. Quacks like a Scan to findings()."""

    def __init__(self, text):
        self.q = text.splitlines()
        self.w = ["$Q"] * len(self.q)
        self.k = ["q"] * len(self.q)


def findings(scan, extra=()):
    """Every Finding in scan's words: each known shape in a word, or, when it
    holds none, at most one context finding. `extra` is the caller's own rules
    (a project's list), tried after the shipped ones."""
    rules = tuple(secret_rules.RULES) + tuple(extra)
    out = []
    for i in range(len(scan.w)):
        if scan.k[i] == ";":
            continue
        text = scan.q[i] if scan.k[i] == "q" else scan.w[i]
        hits = _shapes(text, rules)
        if hits:
            out.extend(Finding(i, rule, "shape", span) for rule, span in hits)
            continue
        prev = scan.w[i - 1] if i > 0 and scan.k[i - 1] == "w" else None
        hit = _context(text, prev)
        if hit:
            out.append(Finding(i, hit[0], "context", hit[1]))
    return out


def word_text(scan, i):
    """The text of word i as a Finding's span indexes it."""
    return scan.q[i] if scan.k[i] == "q" else scan.w[i]


def redact(scan, found, mask="****"):
    """scan's words with each finding's secret replaced by mask, so a writer
    records `GITHUB_TOKEN=****` and keeps the rest of the command."""
    words = [word_text(scan, i) for i in range(len(scan.w))]
    # Right to left within a word, so an earlier span's indexes stay valid.
    for f in sorted(found, key=lambda f: (f.index, f.span[0]), reverse=True):
        a, b = f.span
        words[f.index] = words[f.index][:a] + mask + words[f.index][b:]
    return words


def shown(scan, f, keep=4):
    """The secret f names, shortened for a reason: at most `keep` characters
    and never more than a quarter of it, then the mask, so a reason echoes
    little of a short value and never the whole of any."""
    a, b = f.span
    return word_text(scan, f.index)[a:a + min(keep, (b - a) // 4)] + "…"
