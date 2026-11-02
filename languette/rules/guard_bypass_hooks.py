"""guard-bypass-hooks: features/guard-bypass-hooks.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a git call that skips the repo's
hooks (`--no-verify`, `-n` on commit and am, `-c core.hooksPath=...`) runs only on the
user's approval, one per run. The walk of the command is the `skips-hooks` test; the
approval is cross-call state, spent beside the transcript, read by the `hooks-approval`
handler (languette/hook_skips.py), which gives the verdict."""

RULE_SET = {
    "guard": "guard-bypass-hooks",
    "rules": [{"id": "skip-hooks", "match": [{"test": "skips-hooks"}], "action": "deny",
               "handler": "hooks-approval"}],
}
