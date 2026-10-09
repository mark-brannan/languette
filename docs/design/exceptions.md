# Exceptions

How languette raises and catches. Present tense is the aim, not today's
code; "(planned)" marks where the code has not caught up. It rests on
[the guard pipeline](guard-pipeline.md).

## Purpose

A finding must not turn on which exception a library happened to raise.
When it does, a change far from a guard rewords or flips its verdict: a
directory at ask-first's config path once read "unreadable" and now reads
"not JSON", though ask-first never changed. So no exception carries meaning
across a step's edge, and one place turns a failure into a deny.

## The rule

> A pure step never sees an exception from I/O. A Need is answered with a value; a fact that cannot be had is a value saying why, and the guard decides what it means. Exceptions inside a pure step are its own, raised and caught there; anything else is a bug, and the runner's catch-all makes it a deny.

## The classes kept

| Class | Means | Raised by | Caught by | The catcher |
|---|---|---|---|---|
| `Refuse` | this guard denies, for the reason it carries | deep in a guard's walk | that guard's `check` | returns the deny |
| `scan.Unparseable` | a parser rung read the text and refused it | parse | guard-unparsable; the ladder, for a nested text | denies; or reads that text with awk |
| `scan.RunFailed` | the parser's run failed, not the text | parse | guard-unparsable | denies, saying retry |
| `scan.TooBig`, `scan.TooMany` | the text is past a size, weight or nesting limit | parse | guard-unparsable | denies, naming the limit |
| a library's own (`ValueError` from `json`, `re.error`, `OSError`) | the call failed | the standard library | the line that made the call | turns it into a value |
| anything else | a bug | anywhere | the runner, once per guard | a deny naming the guard |

## A fact that cannot be had

World answers every Need with a value. When it cannot have the fact it
answers `Unavailable(kind, why)` (planned). `kind` is one of a closed list:
`missing`, `denied`, `not-regular`, `too-big`, `not-text`, `garbled`,
`timeout`, `failed`. `why` is the OS's words, for a person. `None`, `False`
and `""` stay facts: `path exists` answering `False` means no such file;
`Unavailable` means world could not tell. It has no truth value: `if fact:`
on it raises, so a guard that forgets to check crashes into the catch-all, a
deny, rather than reading "could not tell" as "no".

The runner's `throw` branch goes; it only sends. A Need of a kind world does
not know, or an Act it does not do, is a bug in the guard: it ends the guard
at the catch-all, never thrown in where a broad except could read it as a
missing file.

## What a guard may assume

It may assume an answer is the documented type or an `Unavailable`, never
an exception; that `kind` comes from the list above, which grows only here;
and that text it read is UTF-8 and within the limit it asked for.

It may not assume that `why` keeps its words (quote it, never match it);
that a fact still holds when the command runs; or that a fact it could not
have is false: a guard maps `Unavailable` to its own fail-closed finding.

## The one catch-all

The runner wraps each guard's run in one `except Exception` and turns what
escapes into a deny naming the guard; loading the guards and reading the
payload are the same edge. It is the only fail-closed catch-all: a second,
inside a guard, can only say the same deny in other words or swallow a bug
that should have denied.

An event that only keeps state (PostToolUse, SessionStart and the rest) has
no verdict to deny. A guard that keeps state names the Act a crash stands
for, and the runner does it: guard-cross-session-send's door opens,
guard-github-issues' door is spent (planned).

After the verdict, act and the decision record each sit behind one silent
catch: a failed write never changes a verdict already given.

## Forbidden

- Branching on the class of an exception from world inside a guard.
- `except Exception` inside a guard.
- Raising to return a value one frame up: a check that finds one fault
  returns the reason.
- A bare `except:`, or an `except BaseException` that does not re-raise.
- Raising a class for a condition it does not name, such as an `OSError`
  for a payload with no transcript.

## Allowed

- A step's own signal as a non-local exit out of a walk: a recursion, or a
  judge whose many call sites sit frames below its edge (guard-disk,
  guard-permissions, guard-recursive-delete, guard-worktrees' path walk).
  The step's edge catches it and turns it into a finding.
- A library's exception, by its own class, on the line that called it.
- A fence around foreign code: a pip parser that fails is a missing rung.
- `StopIteration` in the runner: it is how a generator returns.

## The practice behind it

- **EAFP at I/O, LBYL in judgement.** World tries the syscall, since
  looking first races the disk; a guard tests values, which race nothing.
- **Narrow excepts.** Catch the class the call names, on the call.
- **Classes as a declared interface, or not at all.** A class that crosses
  a module edge is in the table above; one that is not does not cross.
- **Fail closed at one boundary**, where the verdict is made.
- **Errors as values across boundaries**, as in Go's `(value, err)` or
  Rust's `Result`: the standard library's class tree is not an interface
  languette chose.

## What changes to get there

- `world`: `read`, `claim`, `send-state`, `run`, `cwd` and `path realpath`
  answer `Unavailable` rather than raise; `git`, `gh-api` and `pr-list`
  answer it where they now answer `None` for a failure to ask.
- `run._drive`: no throw; an unknown Need or Act ends the guard at the
  catch-all; a crashed state-keeping guard's named Act is done.
- Guards: every except on a Need's answer becomes a test for `Unavailable`;
  a one-frame `Refuse` becomes a returned reason (ask-first's and
  guard-secrets' config checks, guard-bypass-labels' file reads,
  guard-bypass-ruleset's push reading, guard-git-work-loss's rules,
  guard-worktrees' two controls).
- `paths.resolve` returns the path or the reason; `Unresolved` goes.
- Guards read the command parsed once, so no parser signal reaches a guard
  that is not guard-unparsable.
