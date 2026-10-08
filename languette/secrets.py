"""Secret detection: which words of a parsed command are a secret (#95).

One detector, shared by guard-secrets (which reports its findings to the
verdict) and any writer that records commands (which masks them). Pure: it
reads a Scan's words and returns Findings; no I/O, no clock.

Three layers, in the order prior art (gitleaks, detect-secrets) uses them:

- shape: a word holds a vendor-prefixed or fixed-format token
  (secret_rules.RULES, ported from gitleaks, plus the caller's own rules);
- context: the word is `KEY=value`, `Key: value` or follows an option that
  names a credential (`--password`, `--token`), or is a URL with a password;
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

# A key that names a credential, as the whole key or its last underscore- or
# dash-separated part: TOKEN, GITHUB_TOKEN, db-password, aws_secret_access_key.
_KEY = re.compile(r"(?i)(?:^|[_.-])(?:secret|token|passw(?:or)?d|pass|pwd|api[_-]?key|apikey|access[_-]?key|"
                  r"private[_-]?key|auth|authorization|credentials?|client[_-]?secret|secret[_-]?key|"
                  r"access[_-]?token|refresh[_-]?token|session[_-]?key|signing[_-]?key)$")
# Options whose next word, or whose =value, is a credential. Short options
# (-p, -u) are too many other things (mkdir -p, ssh -p) to be read this way.
_OPTS = frozenset("--password --passwd --pass --token --secret --api-key --apikey --access-key --client-secret "
                  "--auth-token --access-token --private-key --secret-key".split())
# A header value's scheme word, dropped before the value is judged.
_SCHEME = re.compile(r"(?i)^(?:bearer|basic|token|apikey)\s+")
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


def _shape(text, rules):
    """(rule_id, span) of the first known shape in text whose secret clears the
    rule's entropy floor, or None."""
    for rule in rules:
        m = rule.regex.search(text)
        if m is None:
            continue
        a, b = _secret_of(rule, m)
        if entropy(text[a:b]) >= rule.entropy:
            return rule.id, (a, b)
    return None


def _value_span(text, start):
    """(start, end) of the value at text[start:], scheme word dropped, or None
    when it does not read as a literal secret."""
    v = text[start:]
    m = _SCHEME.match(v)
    if m:
        start += m.end()
        v = text[start:]
    v = v.strip()
    if not v or _NOT_LITERAL.match(v) or len(v) < MIN_LEN or entropy(v) < MIN_ENTROPY:
        return None
    s = text.index(v, start)
    return s, s + len(v)


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
    m = re.match(r"^([^=:\s]+)\s*[=:]\s*", text)
    if m:
        key = m.group(1)
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
    """Every Finding in scan's words, shape before context, one per word.
    `extra` is the caller's own rules (a project's list), tried after the
    shipped ones."""
    rules = tuple(secret_rules.RULES) + tuple(extra)
    out = []
    for i in range(len(scan.w)):
        if scan.k[i] == ";":
            continue
        text = scan.q[i] if scan.k[i] == "q" else scan.w[i]
        hit = _shape(text, rules)
        if hit:
            out.append(Finding(i, hit[0], "shape", hit[1]))
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
    for f in found:
        a, b = f.span
        words[f.index] = words[f.index][:a] + mask + words[f.index][b:]
    return words


def shown(scan, f, keep=4):
    """The secret f names, shortened for a reason: its first `keep` characters
    and the mask, never the whole value."""
    a, b = f.span
    return word_text(scan, f.index)[a:a + keep] + "…"
