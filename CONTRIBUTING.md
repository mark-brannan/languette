# Contributing

Thanks for looking. Bug reports, fixes and docs are welcome as issues and
pull requests. For a vulnerability, see [SECURITY.md](SECURITY.md) instead.

## A new guard starts as an issue

A guard enters languette through an issue, never straight from a miss.
The issue gives:

- the incident,
- its root cause,
- the hazard: why it could ruin a day, as the README's lede puts it (a
  waste of an hour is not one),
- the concept: a setting of an existing guard, or a new one,
- the name, under the naming decision in [docs/decisions.md](docs/decisions.md).

Root cause comes first, guard second. A miss is often a workflow gap, and a
guard at most a backstop for it.

Please do not open a pull request that prototypes a guard, not even a
draft. Prototype it in your own hook layer or a sibling repository; it
comes here once the maintainer puts the `ready` label on its issue. If the
parser and engine make that hard, the issue to file is the interface you
need exposed.

## Building a guard

A guard is written against the shared layer: Document for the call, scan
for the words, verdict for the answer. A primitive that two or more guards
would share goes into scan or verdict in the same pull request, and the
siblings that repeat it move onto it. `tests/test_structure.py` fails on a
constant a guard keeps that the shared layer or another guard holds, a call
field read past Document, or a sentence said outside messages.

## Before you push

```
pip install -r requirements-dev.txt
pytest
```

The decisions behind all of this are in [docs/decisions.md](docs/decisions.md),
under "New guards".
