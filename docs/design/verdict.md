# The verdict

What step 5 of [the guard pipeline](guard-pipeline.md) says and to whom, and where
the human's yes is spent. Present tense is the aim, not today's code; the
decisions are in [decisions.md](../decisions.md).

## What the verdict says

A verdict has two axes (#87), so no guard's message is lost to the decision
that won.

- **Decision:** allow, ask or deny. The strictest across guards wins, deny
  over ask over allow, as Claude Code merges its own hooks.
- **Who is told:** nobody, the agent, the user, or both. Every guard's message
  reaches its audience, whichever decision wins.

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
tier adds denies, the rest open there. A crashed guard's deny and an
unparsable command's deny are never downgraded: both fail closed.

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
- **A guard spends nothing.** The runner spends the yes once, in act, only
  when the verdict lets the call through (#83).
- **One click is one run,** whichever guards asked: every guard's asks for a
  call are spent together. A spend lost to a parallel call, or one that
  cannot be recorded, makes the call a deny: act's one refusal, the only
  decision after the verdict.
- **Nobody to answer:** an ask falls back to a deny, in the verdict, from the
  mode. The fallback sits outside every guard so it can change without
  touching one; whether it is configurable is open (#84).
