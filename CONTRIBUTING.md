# Contributing

Issues and pull requests are welcome. A vulnerability goes through
[SECURITY.md](SECURITY.md) instead.

## A pull request

Run the suite before you push; the README's
[Working on it](README.md#working-on-it) has the other commands.

```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
python3 -m pytest
```

Title it with a conventional type: `fix(doctor): …`, not `doctor: …`.

## A new guard starts as an issue

A guard never comes straight from a miss. The issue gives:

- the incident
- its root cause
- the hazard: why it could ruin your day; a wasted hour is not one
- the concept: a setting of an existing guard, or a new one
- the name: a row of [the approved names](docs/approved-guard-names.md), or one proposed for it

A miss is often a workflow gap, and a guard at most a backstop for it.

Prototype it outside this repository. A pull request here, even a draft,
waits for the maintainer's `ready` label on the issue.

## Building a guard

Start with its spec, `features/<name>.feature`: a command in, a verdict out.
Write the guard against the shared layer: Document for the call, scan for the
words, verdict for the answer. A primitive two guards would share lands there
first.

`tests/test_structure.py` and `tests/test_purity.py` fail on a guard that:

- has no feature file
- keeps a constant the shared layer or another guard holds
- reads a call field from the payload, not from Document
- says a sentence outside `languette/messages.py`
- touches the disk, the network, the clock or a program; it asks the runner, with a Need

Their lists of known exceptions only shrink. The decisions are in
[docs/decisions.md](docs/decisions.md), under "New guards".
