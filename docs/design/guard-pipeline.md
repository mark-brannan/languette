# The guard pipeline

The design behind epic #76. Present tense is the aim, not today's code;
the ruling is in [decisions.md](../decisions.md).
## Purpose

A guard's judgement is easy to read, test and trust only if it cannot touch
the world. Languette keeps every judgement pure and pushes all contact with
the disk, the network, the clock and other programs into two narrow steps.

## The six steps

```
 1. parse    pure*   read the command into its parts
 2. plan     pure    list the facts each guard needs
 3. gather   I/O     fetch exactly those facts; the only reads
 4. guard    pure    parsed command + facts -> finding
 5. verdict  pure    findings + configuration -> silent / warn / ask / deny
 6. act      I/O     after the verdict only: every write
```

- **Pure** means: looks only at its inputs, only returns a value. Same input,
  same answer.
- **\*Parse** is pure in effect: the parser ladder runs `shfmt` and `bash -n`
  as programs. It is the one named exception.
- **Gather** fetches only what plan listed: no speculative reads, no `gh api`
  on a command that never names a repo.
- **Act** holds every write: spending an approval, saving the ruleset cache,
  and the simple metrics. A deny writes nothing a guard asked for, so a click
  is never spent on a command that does not run.

## Two shapes of guard

| Shape | When | How |
|---|---|---|
| plan / judge | the guard's questions are all known once the command is parsed (disk, permissions, recursive-delete, bypass-labels) | `plan(parsed)` returns the questions; `judge(parsed, answers)` returns the finding; both plain pure functions |
| ask as it goes | one answer decides the next question (ask-first, bypass-ruleset: git names the remote, then GitHub is asked about it) | the guard pauses with a question, the runner answers, the guard resumes; it loops through steps 2 and 3 more than once, and still never touches the world itself |

## The purity check

A test reads the source of every guard and of the verdict, without running
them, and fails on any call that opens a file, starts a program, opens a
connection, reads the clock or asks the disk about a path. Pure path helpers
(join, dirname, normpath) pass. The README says the guards are pure; this test
is why that sentence stays true. Cost: one file, a few milliseconds per run
(estimate).

## Cross-cutting: metrics

Metrics are expected to be simple and recorded in act, alongside the other
writes (Solace, 2026-10-07: "most likely we will do simple metrics that are at
the write stage also"). A richer metric that needs timing inside steps 1 to 5
would be the first wrinkle in this shape.
