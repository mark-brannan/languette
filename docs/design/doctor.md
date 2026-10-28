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

1. **Checks protection and its dependencies:** one ✓, ! or ✗ row per check; any ✗ exits non-zero.
2. **Diagnoses every config** through the guard's own loader. (planned)
3. **Offers the fix** as a diff, applied only on a yes. (planned)
4. **Assists with configuration,** not only repair. (planned)

The checks are the install, the dependencies, a probe through the hooks as
installed, and the version; CI can run them. The dependencies are few and
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
guard-private-terms is the first: a row per terms file through the guard's
loader, a refused line named, and `--redact <file>`
printing what a post would become and which terms block it. (planned)

## Limits

The probes send payloads to the hooks and run neither command. Only trusted
hooks get a probe; a project's checked-out settings are counted, never run.
What the doctor cannot read is a ! row, never a traceback.
