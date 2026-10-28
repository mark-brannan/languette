# The doctor

What `languette doctor` is for and what it does. Present tense is the aim;
"(planned)" marks where the code lags. The other design docs: [the guard
pipeline](guard-pipeline.md), [guard rules](guard-rules.md),
[exceptions](exceptions.md), [portability](portability.md).

## Purpose

The doctor says whether languette protects the agent at all: the install,
its dependencies, the hooks as wired, the version. Beyond that it exists to
make languette simple to configure. A guard that fails
closed on a bad config is right to stop the agent, and wrong to leave the
user to work out why. The doctor is where that why gets answered and the
config gets mended: one command that says what is wrong, offers the fix, and
helps write a config that works.

## What it does

1. **Checks protection and its dependencies:** one ✓, ! or ✗ row per check, detail lines indented beneath it; any ✗ exits non-zero. A ✗ never stops a later check: the doctor runs every check it can and decides the exit code once, after the last row, with a closing line counting the problems. A check that cannot run because something it needs failed is a ! row saying so.
2. **Diagnoses every config** through the guard's own loader. (planned)
3. **Offers the fix** as a diff, applied only on a yes. (planned)
4. **Assists with configuration,** not only repair. (planned)

The checks run in this order: the version, the shell parser, the parse-check
probe, the fail-closed probe, the install with its guards beneath it (counts
enabled and disabled, each disabled guard named with a one-line description),
the forge clients, then the terms files; CI can run them. The dependencies are few and
each gets its row: `shfmt`, the preferred parser, has top billing, and a
machine without it is told which rung reads commands instead; `gh` is
optional, and without it the guards that ask GitHub ask the user instead.
Every other forge client installed gets a row too, a warning when signed in,
since the agent can act through it where the guards see only part. The configs are the plugin's options
and every file under `.languette/`. A config its guard would refuse is a ✗
row naming the file, the entry and why: a key no guard reads, a value of the
wrong type, a file that does not parse. A config that switches every command
to deny is reported first.

The fix is offered interactively at a terminal, or through a flag where
there is none. Where the right fix is the user's call, such as an entry that
could be a typo for either of two keys, the doctor asks with the choices. It
writes nothing without a yes.

Assisting means saying what each guard's options are and what a given choice
would ask or deny, and writing a starting file for a guard that has none.
guard-private-terms is the first. Each terms file gets a row, then indented
lines: its path, the number of entries it holds, and the min, max and average
time of its `re:` lines. Only the entries in the file count; the doctor does
not add a shipped set. Every line the loader would refuse is a ✗ line naming
its line number and why, and the valid lines are still loaded and timed. A
`re:` slower than the threshold is listed on its own line with its line
number and the first characters of the find. The time is shown, never the
verdict. A missing redacted terms file is a ! row naming the fix.

`--restore-terms` writes the default entries into the redacted terms file when
there is none, and otherwise appends the defaults the file lacks; it never
edits or removes a line you wrote, and prints what it added. (planned)
`--redact` prints what a post would become and which terms block it, reading
the post from a file or, with none given or `-`, from stdin.

## Limits

The probes send payloads to the hooks and run neither command. Only trusted
hooks get a probe; a project's checked-out settings are counted, never run.
What the doctor cannot read is a ! row, never a traceback.
