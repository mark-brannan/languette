# Security policy

Languette guards against an agent's mistakes. It is
[not a sandbox](README.md#not-a-sandbox).

A vulnerability is a bug that leaves you worse off than running without
languette.

## What counts as a vulnerability

- A secret written to the decision record.
- Text from a command, a file or a web page reaching the agent as languette's instruction.
- Languette running any part of a command it is only meant to read.

## What does not count

- A command that no guard or rule covers today. That is a gap in what
  languette does.
- A guard that allows a command the README says it denies.
- A guard that fails open: an error, a missing tool or a malformed input lets
  a command through.
- A `why` or other languette config text reaching the agent on a deny or ask: the design, see [#383](https://github.com/mark-brannan/languette/issues/383).
- An agent loosening its own guards through `languette config` or settings: known, see [#384](https://github.com/mark-brannan/languette/issues/384).

[Open an issue](https://github.com/mark-brannan/languette/issues) for any of
these. If you think one puts people at more risk than running without
languette, report it privately instead.

## Reporting a vulnerability

Report it privately, not in a public issue or pull request: on the
repository's Security tab, choose
[Report a vulnerability](https://github.com/mark-brannan/languette/security/advisories/new).

## What to expect

- Acknowledged within 7 days.
- A fix, or a plan for one, within 30 days.
- Made public when the fix is released, or after 90 days, whichever comes first.

Only the latest release is supported.
