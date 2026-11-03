"""guard-private-terms: features/guard-private-terms.feature is the spec. A rule set alone
(languette/engine.py reads it): text bound for a public GitHub repo is judged twice. Once a
private term is in a public issue or PR it is in GitHub's history and every mirror of it, so
the check sits at the moment the text leaves the machine. A term from the redacted terms file
is replaced in the posted text alone and the call allowed; a hit on the blocked terms file
denies the whole post. Both files are data (languette/terms.py reads them; the defaults are
languette/rules/redacted-terms.tsv). The posted text is read from gh's flags, gh api and an
MCP tool's strings (languette/posts.py); the walk and the verdict are the `private-terms`
test, which gives the verdict itself, a deny or an allow carrying the redaction. `calls`
says it judges a call with no command too, an MCP tool's. `on` names the handler of the
session's start: `terms-init` writes the default redacted terms file where none is there."""

RULE_SET = {
    "guard": "guard-private-terms",
    "calls": "any",
    "rules": [{"id": "private-terms", "match": [{"test": "private-terms"}], "action": "deny"}],
    "on": {"SessionStart": "terms-init"},
}
