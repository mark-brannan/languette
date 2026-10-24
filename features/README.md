# Feature files

Every row runs with every guard on, opt-in guards included, configured once
in `tests/conftest.py`. A file named for a guard checks that guard's verdict,
and every other guard must stay silent on the row.

## `@also_<guard>`

Some commands rightly trip a second guard. `@also_guard-disks` on a scenario
or an Examples block says so: guard-disks must fire on those rows too, and
the row fails if it stays quiet. It switches nothing on.

```gherkin
@also_guard-disks
Scenario: a click comes back when the user declines the command
  When the agent runs `npm run e2e && dd if=/dev/zero of=/dev/sda`
  Then the guard is silent        # ask-first's verdict; guard-disks denies the dd
```

A file tagged `@family` or `@planned`, and `everyday-commands.feature`, checks
what the hook as a whole answers.
