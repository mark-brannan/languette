"""guard-signed-comments: features/guard-signed-comments.feature is the spec. A rule set
(languette/engine.py reads it) whose handler is code: a comment an agent posts to GitHub
comes from a bot's account, and its body carries the opening and the signature the
settings give. Its calls include the GitHub MCP tools', which carry no command, so its
one match entry is a test. The `comment-posts` test finds the posts a call makes and
where each body is written; the bodies' files and gh's account are facts, read by the
`signatures` handler (languette/comment_posts.py), which gives the verdict and asks when
gh cannot say whose account it is."""

RULE_SET = {
    "guard": "guard-signed-comments",
    # Off unless the user turns it on: the signature is one workflow's convention.
    "opt_in": "CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS",
    "calls": "any",
    "rules": [{"id": "unsigned", "match": [{"test": "comment-posts"}], "action": "deny",
               "handler": "signatures"}],
}
