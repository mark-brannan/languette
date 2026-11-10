# Security policy

## What counts as a vulnerability

- A guard that allows a command the README says it denies.
- A guard that fails open: an error, a missing tool or a malformed input lets a command through.
- A secret written to the decision record.

A command no rule covers does not count. That is a known gap, not a
vulnerability; [open an issue](https://github.com/mark-brannan/languette/issues) for it.

## Reporting a vulnerability

Report it privately, not in a public issue or pull request: on the
repository's Security tab, choose
[Report a vulnerability](https://github.com/mark-brannan/languette/security/advisories/new).

## What to expect

- Acknowledged within 7 days.
- A fix, or a plan for one, within 30 days.
- Made public when the fix is released, or after 90 days, whichever comes first.

Only the latest release is supported.
