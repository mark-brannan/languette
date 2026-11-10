# Security policy

## What does *not* count as a vulnerability?

A command that no guard or rule covers today. That is merely a feature/functionality gap, not a
vulnerability; [open an issue](https://github.com/mark-brannan/languette/issues) for it.

## What counts as a vulnerability?
- A secret written to the decision record.
- A prompt injection risk, setting aside the specified design that send preconfigured 'why' statements to the agent on a deny/ask. 

## What counts as ambiguous for vulnerability reporting?
These might be either a bug/issue or vulnerability depending on the circumstances.  There's not a clear rule yet:
- A guard that allows a command the README says it denies.
- A guard that fails open: an error, a missing tool or a malformed input lets a command through.

## Reporting a vulnerability

Report it privately, not in a public issue or pull request: on the
repository's Security tab, choose
[Report a vulnerability](https://github.com/mark-brannan/languette/security/advisories/new).

## What to expect

- Acknowledged within 7 days.
- A fix, or a plan for one, within 30 days.
- Made public when the fix is released, or after 90 days, whichever comes first.

Only the latest release is supported.
