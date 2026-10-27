# The doctor

What `languette doctor` is for and what it does. Present tense is the aim;
"(planned)" marks where the code lags. The other design docs: [the guard
pipeline](guard-pipeline.md), [guard rules](guard-rules.md),
[exceptions](exceptions.md), [portability](portability.md).

## Purpose

The doctor exists to make languette simple to configure. A guard that fails
closed on a bad config is right to stop the agent, and wrong to leave the
user to work out why. The doctor is where that why gets answered and the
config gets mended: one command that says what is wrong, offers the fix, and
helps write a config that works.

## What it does

1. **Says whether languette protects this machine.** One row per check, each
   ✓, ! or ✗, and a non-zero exit on any ✗, so CI can run it: the install,
   the shell parser, a probe through the hooks as installed, `gh`.
2. **Diagnoses every config.** Each config languette reads — the plugin's
   options and every file under `.languette/` — is loaded through the same
   loader the guard uses, and a config that guard would refuse is a ✗ row
   naming the file, the entry and why: a key no guard reads, a value of the
   wrong type, a file that does not parse. A config that switches every
   command to deny is the first thing the doctor reports. (planned)
3. **Offers to fix a bad config.** For each ✗ it can mend, the doctor shows
   the change as a diff and applies it on a yes: interactively at a
   terminal, through a flag where there is none. Where the right fix is the
   user's call — an entry that could be a typo for either of two keys — it
   asks, with the choices. It writes nothing without that yes. (planned)
4. **Assists with configuration.** It helps write a config, not only repair
   one: what each guard's options are, what a given choice would ask or
   deny, and a starting file for a guard that has none. (planned)

## Limits

The probes send payloads to the hooks and run neither command. Only trusted
hooks get a probe; a project's checked-out settings are counted, never run.
What the doctor cannot read is a ! row, never a traceback.
