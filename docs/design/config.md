# Configuration

How a guard's options are set, on any host. Present tense is the aim;
"(planned)" marks where the code lags. The other design docs: [install](install.md),
[the doctor](doctor.md), [guard rules](guard-rules.md), [exceptions](exceptions.md).

## Purpose

Which guards run, and how, is set in one place that is not the installer. Today
an option is reached through the host (`claude plugin install … --config`,
`/plugin configure`), a file under `.languette/`, a terms file or an
environment variable, and the one command that reads them all is the doctor.
Installing and configuring are separate acts: install
puts languette on the host, and config changes it afterwards, any day.

## languette config (planned)

```
languette config                              every option, its value, where it is set
languette config guard_recursive_delete=false set one
languette config --unset guard_recursive_delete
```

- **One name per option,** the underscore name the README already uses.
- **Validated before written.** The value goes through the guard's own loader;
  one it would refuse writes nothing and says why, as the doctor would.
- **The host stays the owner.** For Claude Code it sets the plugin's option
  through `claude plugin`, as `install` does, and writes nothing itself; a
  host with no options of its own gets a file under `.languette/`, shown as a
  diff first.
- **A setting that can only close a gate stays closed.** `config` cannot make
  a misconfiguration open one; the "exactly `false`" and "exactly `true`"
  rules in the README hold whoever wrote the value.

## The doctor's part

The doctor diagnoses and offers the fix; `config` sets an option. Where the
doctor writes on a yes ([doctor](doctor.md): an applied fix,
`--restore-terms`), it writes through the same loaders, so neither can store
a value the other would refuse.

## install takes no options

`languette install [host]` wires the host and nothing else. The `--config` in
the README belongs to `claude plugin install`, the host's flag, and the README
points to `languette config` as the way to change an option later.

## Open questions

- Whether `config` and the doctor stay two commands or merge into one, and
  if they merge, which name survives. Open.
