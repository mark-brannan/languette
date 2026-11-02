"""ask-first: features/ask-first.feature is the spec. A rule set (languette/engine.py
reads it) whose handler is code: a command the repo lists as costly, in
.languette/ask-first.json, runs only on the user's approval, one per run. The list is
read in gather, so the rule selects every command and the `listed-approval` handler
(languette/listed_runs.py) finds the list, walks the command against it and gives the
verdict; a list it cannot read denies every command."""

RULE_SET = {
    "guard": "ask-first",
    "rules": [{"id": "listed", "match": [{"test": "command"}], "action": "deny",
               "handler": "listed-approval"}],
}
