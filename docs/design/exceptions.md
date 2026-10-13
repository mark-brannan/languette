# Exceptions

How languette raises and catches, on [the guard pipeline](guard-pipeline.md).
Present tense is the aim; "(planned)" marks where the code lags.

## Purpose

A finding must not turn on which exception a library happened to raise.
When it does, a change far from a guard rewords or flips its verdict: a
directory at ask-first's config path once read "unreadable" and now reads
"not JSON", though ask-first never changed. So no exception carries meaning
across a step's edge, and one place turns a failure into a deny.

## The rule

> A pure step never sees an exception from I/O.
>
> - A Need is answered with a value. A fact that cannot be had is still a
>   value, one that says why, and the guard decides what it means.
> - A pure step's own exceptions are raised and caught inside it; none
>   leaves the step.
> - Any other exception is a bug. The runner's catch-all turns it into a deny.

## The classes kept

| Class | Means | Raised by | Caught by | The catcher |
|---|---|---|---|---|
| `Refuse` | this guard denies, for the reason it carries | deep in a guard's walk | that guard's `check` | returns the deny |
| `scan.Unparseable` | a parser rung read the text and refused it | parse | require-well-formed; the ladder, for a nested text | denies; or reads that text with awk |
| `scan.RunFailed` | the parser's run failed, not the text | parse | require-well-formed | denies, saying retry |
| `scan.TooBig`, `scan.TooMany` | the text is past a size, weight or nesting limit | parse | require-well-formed | denies, naming the limit |
| a library's own (`ValueError` from `json`, `re.error`, `OSError`) | the call failed | the standard library | the line that made the call | turns it into a value |
| anything else | a bug | anywhere | the runner, once per guard | a deny naming the guard |

## A fact that cannot be had

World answers every Need with a value. When it cannot have the fact it
answers `Unavailable(kind, why)` (planned). `kind` is one of a closed list:
`missing`, `denied`, `not-regular`, `too-big`, `not-text`, `garbled`,
`timeout`, `failed`. `why` is the OS's words, for a person. `None`, `False`
and `""` stay facts: `path exists` answering `False` means no such file;
`Unavailable` means world could not tell. `bool()`, `==` and formatting on
it raise, so a guard that forgets to check crashes into the catch-all, a
deny, rather than reading "could not tell" as "no". Only `is` slips past, so
a guard tests for `Unavailable` before it tests `is None`.

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
for, and the runner does it, each toward a deny (planned):
guard-cross-session-send's door opens (later sends deny or ask), and
guard-github-issues' door is spent (the next write is denied).

After the verdict, act and the record sit behind one silent catch each.

## Forbidden

- Branching on the class of an exception from world inside a guard.
- `except Exception` inside a guard.
- Raising to return a value one frame up; a check returns the reason.
- A bare `except:`, or an `except BaseException` that does not re-raise.
- Raising a class for a condition it does not name (`OSError` for no
  transcript).

## Allowed

- A step's own signal as a non-local exit out of a walk, a recursion or a
  judge with many call sites frames below its edge (the guard-disks judge), caught
  at the step's edge and turned into a finding.
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
- **Errors as values across boundaries**, as Go's `(value, err)` and Rust's
  `Result` do.

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
- Guards read the command parsed once: no parser signal reaches the others.
