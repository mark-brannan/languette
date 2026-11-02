"""guard-secrets: features/guard-secrets.feature is the spec. A rule set alone
(languette/engine.py reads it): a credential written into a Bash command is in the
transcript already, and in whatever the command commits, prints or posts next. A known
token shape (languette/secret_rules.py) is denied; a value only its context names as a
credential is asked, since the shape alone cannot tell a secret from a hostname. The
project may add shapes in <project>/.languette/secrets.json, the nearest at or above the cwd:

    {"patterns": [{"id": "acme-key", "description": "Acme API key",
                   "regex": "acme_[a-z0-9]{24}", "entropy": 3.0}]}

No file is the shipped list alone. A file that does not load denies every Bash command: a
pattern may not reuse a shipped id, its regex is at most 512 characters, and one unbounded
repeat inside another is refused (a slow pattern would fail open at the hook's timeout).
The walk of the command and the verdict are the `secrets` test, which gives the verdict
itself, deny or ask."""

RULE_SET = {
    "guard": "guard-secrets",
    "rules": [{"id": "secrets", "match": [{"test": "secrets"}], "action": "deny"}],
}
