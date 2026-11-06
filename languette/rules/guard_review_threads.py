"""guard-review-threads: features/guard-review-threads.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a review bot's thread is resolved
only after a reply that names a commit or a link. The `thread-resolves` test finds, from
the call's words alone, the gh calls that may resolve a thread; the query files they name
and each thread's comments on GitHub are facts, read by the `thread-replies` handler
(languette/thread_resolves.py), which gives the verdict and asks when GitHub cannot
answer."""

RULE_SET = {
    "guard": "guard-review-threads",
    # Off unless the user turns it on.
    "opt_in": "CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS",
    "rules": [{"id": "resolve", "match": [{"test": "thread-resolves"}], "action": "deny",
               "handler": "thread-replies"}],
}
