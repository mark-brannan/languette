# The guard pipeline

The design behind epic #76. Present tense is the aim, not today's code;
the decisions are in [decisions.md](../decisions.md).

## Purpose

A guard's judgement is easy to read, test and trust only if it cannot touch
the world. Languette keeps every judgement pure and pushes all contact with
the disk, the network, the clock and other programs into two narrow steps.

## The six steps

```
 1. parse    pure*   read the command into its parts
 2. plan     pure    list the facts each guard needs
 3. gather   I/O     fetch exactly those facts, guard by guard; the only reads
 4. guard    pure    parsed command + facts -> finding
 5. verdict  pure    findings + configuration + mode -> silent / warn / ask / deny
 6. act      I/O     after the verdict only: every write
```

- **Pure** means: looks only at its inputs, only returns a value. Same input,
  same answer.
- **\*Parse** is pure in effect: the parser ladder runs `shfmt` and `bash -n`
  as programs. It is the one named exception.
- **Gather** fetches only what plan listed: no speculative reads, no `gh api`
  on a command that never names a repo. It reads only: a Need writes
  nothing, runs no program a setting or env var names, and reads no state
  but the call's payload and transcript, the clock, its own environment,
  the filesystem, git, GitHub, and records this plugin wrote in act. What a guard cannot learn that way
  stays out of its finding.
- **Gather** runs guard by guard, each in its own shape (below); all guards
  share the one parse and run in one process.
- **Mode** is the hook input's `permission_mode`, never an environment
  variable. It changes one thing: in a mode where no one can answer, an ask
  is a deny. A missing or unknown mode leaves the ask standing: a user who is
  there keeps the yes, and a host with no one to answer refuses it itself.
- **Act** holds every write: spending an approval, saving the ruleset cache,
  and the simple metrics. It runs at two moments: after the verdict, and
  after the call, for a write that must wait until the command has run
  (the issue door, #83). A deny writes nothing a guard asked for, so a click
  is never spent on a command the verdict refuses.

## Two shapes of guard

| Shape | When | How |
|---|---|---|
| plan / judge | the guard's questions are all known once the command is parsed (disk, permissions, recursive-delete, bypass-labels) | `plan(parsed)` returns the questions; `judge(parsed, answers)` returns the finding; both plain pure functions |
| ask as it goes | one answer decides the next question (ask-first, bypass-ruleset: git names the remote, then GitHub is asked about it) | the guard pauses with a question, the runner answers, the guard resumes; it loops through steps 2 and 3 more than once, and still never touches the world itself |

## What the verdict says

A verdict has two axes (#87), so no guard's message is lost to the decision
that won.

- **Decision:** allow, ask or deny. The strictest across guards wins, deny
  over ask over allow, as Claude Code merges its own hooks.
- **Who is told:** nobody, the agent, the user, or both. Every guard's message
  is kept and reaches its audience, whichever decision wins.

| Told | allow | ask | deny |
|---|---|---|---|
| nobody | silent, the default | — | — |
| the agent | a note | — | the reason |
| the user | the user alone | the prompt, the default | — |
| both | **warn** | ask, and the agent told why | the default |

A dash is a cell the decision rules out: an ask's reason always reaches the
user, a deny's always the agent. **Warn** is allow, telling both: the command
runs, and the reason reaches agent and user.

Each audience has its channel in Claude Code's
[hook output](https://code.claude.com/docs/en/hooks.md), and one output carries them all:

| Channel | Reaches | With |
|---|---|---|
| `additionalContext` | the agent | any decision; kept from every hook |
| `systemMessage` | the user | any decision |
| `permissionDecisionReason` | the agent on deny, the user on ask | its decision |

An allow's reason reaches no one and skips the permission prompt, so warn
never sets `permissionDecision: "allow"`; a redaction's allow stays the only
one. A warn, as sent:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "additionalContext": "guard-example: the reason, for the agent"},
 "systemMessage": "guard-example: the reason, for the user"}
```

**Who may change a decision:** the user only, through configuration the
agent cannot write (the user tier in [guard rules](guard-rules.md)); the repo
tier only adds denies. A crashed guard's deny and an unparsable command's
deny are never downgraded: both fail closed.

The configuration's shape is open (#87): a `tell:` field per rule, defaulting
by decision as the table does and with `warn` naming allow-and-tell-both, is
leading; a warn switch on the decision and warn as a fourth decision are the
others. Custom text rides the same rule in each.

## Approvals

The human's yes is spent in one place, so a yes is never lost on a call that
did not run (#84).

- **Any guard can ask.** A guard reports what it found; per-guard
  configuration, with opinionated defaults, maps the finding to deny, ask or
  warn. The user can turn a deny into an ask, or an ask into a deny.
- **The source of a yes is an input:** a click on the agent's question, the
  human's own turn, others later. A guard reads that a yes stands and never
  knows which source gave it.
- **A guard spends nothing.** Its finding names the yes the call needs. The
  runner spends it once, in act, after the verdict, and only when
  the verdict lets the call through: atomic, recorded against the tool call,
  given back when the call never ran. A deny spends nothing, so a click is
  not lost on a command another guard refused (#83).
- **One click is one run,** whichever guards asked: every guard's asks for a
  call are spent together. A spend lost to a parallel call, or one that
  cannot be recorded, makes the call a deny.
- **Nobody to answer:** an ask falls back to a deny, in the verdict, from the
  mode. The fallback sits outside every guard so it can change without
  touching one; whether it is configurable is open (#84).

## The purity check

A test reads the source of every guard and of the verdict, without running
them, and fails on any call that opens a file, starts a program, opens a
connection, reads the clock or asks the disk about a path. Pure path helpers
(join, dirname, normpath) pass. A file it cannot parse fails. It is a list of
known ways out, not a proof: it catches the slip a well-meaning author makes,
not a deliberate escape (`eval`, a command named in a variable). The README
says the guards are pure; this test catches the slip that would make that
false. Cost: one file, a few milliseconds per run (estimate).

## Cross-cutting: metrics

Metrics are expected to be simple and recorded in act, alongside the other
writes (the maintainer, 2026-10-07: "most likely we will do simple metrics that are at
the write stage also"). A richer metric that needs timing inside steps 1 to 5
would be the first wrinkle in this shape.
