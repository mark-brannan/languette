# State read after write, file by file (measured)

For each file a guard writes and later reads back for a verdict
([#368](https://github.com/mark-brannan/languette/issues/368)): can the
verdict come from the call, the transcript or git instead, what that costs
per call, and where it fails. Read against main at `a510dfb` (the code read
is unchanged since `3fbb3cd`, where it was measured); every row of #368's
tables is still there. Measured 2026-11-10 on one Linux machine
(16 cores, load 1.3 to 2.6), Claude Code 2.1.319, over its 6,274 session
transcripts.

## The rows

| File | Verdict from instead | Cost per call | Where it fails | Row |
|---|---|---|---|---|
| issues door, `+.held` | the payload's `prompt_id`, and the transcript's results that carry it | one transcript scan | two writes in flight at once, from a subagent and the main thread | shrink: keep the claim only |
| cross-session record | the transcript's tool calls, run through the guard's own read test | one scan, plus one parse per past call | subagent reads sit in other files | remove |
| worktrees record, `+.arrive` | the transcript's `cwd` per entry, and the call before each change | one scan, one `lstat` per candidate | `cwd` alone vouches for nothing | remove |
| spent ledger | the credit rule, replayed from the transcript | none: the guard scans the transcript already | a subagent's calls sit in other files | remove the read; write-only if kept |
| rulesets cache | the call, and GitHub's answer every time | 648 ms median, on a push already denied | offline, a repeat asks instead of denying | remove |

Out of scope here: the redacted terms file is the user's configuration,
written only when missing, and no verdict reads back what a call wrote; the
decision record is never read.

## What a replay costs

`languette.world.scan` over the transcripts on disk, best of three:

| Transcript | Size | Scan |
|---|---|---|
| median | 0.59 MB | 2.7 ms |
| p90 | 1.59 MB | 8.1 ms |
| p99 | 6.78 MB | 22.0 ms |
| largest | 26.9 MB | 43.1 ms |

A session with subagents (881 of them) keeps each subagent's calls in its
own file: 2 files at the median, 7 at p90, 59 at most; 1.2 MB in all at the
median, 7.1 MB at p90, 91 MB at most. Reading them all at the p99 rate, 1.6
to 4.6 ms per MB, is about 11 to 33 ms at p90 and 0.15 to 0.4 s at the
largest: extrapolated, not timed. For scale, one languette hook run on a
bare `ls` takes 80 ms at least and 86 ms at the median (n=20);
`git rev-parse --show-toplevel` 2.7 ms; `git worktree list --porcelain`
29 ms over 346 worktrees.

## What the transcript carries

- **Subagents.** A tool hook in a subagent gets the main session's
  `transcript_path` and `session_id`, plus `agent_id` (the bundle builds
  `transcript_path` from the session id alone). The subagent's own calls are
  written to `<session>/subagents/agent-<id>.jsonl`, the path SubagentStop
  hands over as `agent_transcript_path`. Every replay below reads those files
  too, or it is blind to a subagent's calls.
- **The human turn.** The payload's `prompt_id` is, in the bundle's words,
  the "UUID correlating a user prompt with all subsequent events until the
  next prompt". Tool results in the transcript carry it as `promptId`: 9,702
  of 9,736 results in the 300 newest transcripts carry the latest prompt's;
  34 carry none. A subagent's results carry its parent's. A new `promptId`
  starts at a human prompt and also at a task notification (99 of 1,071) or
  a peer message (82); the entry's `origin.kind` (`human`,
  `task-notification`, `peer`) tells them apart. Whether UserPromptSubmit,
  which opens today's door, fires for those two was not measured.
- **Where a call stood.** Every entry carries the `cwd` the harness had for
  it.
- **No transcript.** The bundle sends an empty `transcript_path` when the
  session is not persisted and for a call served to a remote caller. A replay
  then has nothing to read and must fail closed.

## The three facts a replay rests on

| Question | Answer | Evidence |
|---|---|---|
| Is the call's own `tool_use` on disk before its PreToolUse hook fires? | Not by design. Earlier calls are, in practice. | The hooks docs: "The transcript file is written asynchronously and may lag the in-memory conversation". The bundle drains its write queue on a 100 ms timer. A serial call follows the earlier call's own hooks, at least 80 ms each. |
| Can two Bash calls from one message run at once? | Only when every running one is read-only. A write runs alone. | The bundle: a tool runs when none is executing or all are concurrency-safe, and Bash is concurrency-safe exactly when the command is read-only. Hooks for one event run in parallel. |
| Does the credit rule, replayed, give what the ledger gave? | Yes, 15 of 15 lines in 6 ledgers, with no extra run allowed. | 14 lines carry the issue door's yes, replayed with the door modelled; 1 carries an ask-first label, whose consumers were taken from the ledger itself, so it is not an independent check. |

The credit rule: yeses for the label, minus later calls for the label before
this one, in transcript order, whose result does not show they never ran. A
call with no result yet counts as spent, so lag over-denies and never
over-allows, as long as the earlier call's `tool_use` line is there.

## Row by row

**Issues door.** The turn is the payload's `prompt_id`: a write may run when
no issue write under that id ran, in the main transcript or a subagent's.
This removes the open and the spend. It does not remove the claim: across
all transcripts, 477 issue writes ran, 11 of them from subagents, and 2 of
408 turns with a write had writes from both the main thread and a subagent.
Two such writes in flight at once have no results yet, so each sees the door
open; the claim's atomic rename is the one thing that lets only one through.
Alternative checked: counting in-flight `tool_use` lines, which a concurrent
call may not have flushed within 100 ms.

**Cross-session record.** Whether the session read untrusted content is a
fold over its tool calls, main and subagent files, through
`untrusted_read`; its own subagents are the Agent calls' names and the ids
their results return. A cleared session starts a new transcript, so `clear`
falls out. A resumed session with no record is unknown today; the
transcript answers it. Cost not measured: each past Bash call is parsed
again, on a SendMessage to another session only.

**Worktrees record.** A session's own linked worktrees are the `cwd` values
in its transcript reached by a route the guard vouches for: the first
entry's, the one after `EnterWorktree(name=...)`, a `git worktree add`
whose `.git` file's ctime is later than that call's timestamp (the
`.arrive` file's job today). A `cwd` alone is not enough: a move the guard
could not see changes it too, so the replay keeps the vouched-route rule.
guard-git-work-loss reads the same answer. Git alone cannot say who owns a
worktree. A subagent's own file holds its own `cwd`s, as the per-agent
record does today.

**Spent ledger.** The guard scans the transcript on every approval already;
the ledger read adds an open and a shared lock. A subagent's calls spend
the main transcript's yeses today, since its payload names the main
transcript; a replay sees those calls only in the subagent files. A purge
removes old transcripts (the docs: about 30 days), not the one a live
session is writing.

**Rulesets cache.** Only "requires a pull request" is cached, so it saves
one or two API calls (648 ms median, n=5, 473 to 813 ms) on a push the guard
denied within the hour. The decision record held 177 pushes in 2.8 days, 7
naming main or master.
