# Security policy

## Reporting a vulnerability

Report it privately: on the repository's Security tab, choose
[Report a vulnerability](https://github.com/mark-brannan/languette/security/advisories/new).
Please do not open a public issue or pull request for it.

## What to expect

- Acknowledged within 7 days.
- A fix, or a plan for one, within 30 days.
- Made public when the fix is released, or after 90 days, whichever comes first.

Only the latest release is supported.

## In scope

- A command a guard covers that the guard allows, when the README says it
  denies it.
- A guard that fails open: an error, a missing tool or a malformed input
  that lets a command through.
- A secret written to the decision record.

## Out of scope

- A command no rule covers. That is a known gap, not a vulnerability;
  [open an issue](https://github.com/mark-brannan/languette/issues) for it.
