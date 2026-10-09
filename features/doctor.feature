Feature: doctor
  `languette doctor` says whether languette protects Claude Code here: one row
  per check, each ✓, ! or ✗, and a non-zero exit on any ✗, so CI can run it.
  Each scenario runs it in "{HOME}/project" against a fake HOME, with stubs
  for `claude` and `gh`, and this repo as the plugin's install path. The
  canary sends `rm -rf ~` to the hook as a payload; nothing runs it.

  Background:
    Given a fake HOME
    And gh is signed in

  Scenario: a plugin install whose hook denies the canary
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true}`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; 20 guards on, 0 off"
    And the "shell parser" row is there
    And the "gh" row is ✓ "signed in"
    And the "fail-closed" row is ✓ matching "`rm -rf ~` was denied through the hook command as installed, \d+ ms of 600 s"
    And the "version" row is ! "no releases yet; plugin at commit cd31356"
    And the doctor exits 0
    And the fake HOME is as it was

  Scenario Outline: a guard is off only when its option says so exactly
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `<options>`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; <counts>"

    Examples:
      | options                                         | counts                                 |
      | {}                                              | 19 guards on, 1 off: guard_worktrees   |
      | {"guard_worktrees": true, "guard_disk": false}  | 19 guards on, 1 off: guard_disk        |
      | {"guard_worktrees": true, "guard_disk": "false"} | 19 guards on, 1 off: guard_disk       |
      | {"guard_worktrees": true, "guard_disk": "no"}   | 20 guards on, 0 off                    |
      | {"guard_worktrees": "yes"}                      | 19 guards on, 1 off: guard_worktrees   |

  Scenario: gh signed out is a warning, not a failure
    Given languette "cd31356ad5db" is installed at user scope
    And gh is signed out
    When the doctor runs
    Then the "gh" row is ! "not signed in; the stacked-base and ruleset guards will ask instead of deciding"
    And the doctor exits 0

  Scenario: nothing installed fails
    When the doctor runs
    Then the "Claude Code" row is ✗ "languette is not installed for this directory"
    And the "fail-closed" row is ✗ "no guard-recursive-delete hook installed to send the canary to"
    And the doctor exits 1

  Scenario: a plugin install and by-hand run.py hooks for the same host fail
    Given languette "cd31356ad5db" is installed at user scope
    And the user's settings.json has a by-hand guard-recursive-delete hook
    When the doctor runs
    Then the "Claude Code" row is ✗ "plugin cd31356, user scope, and by-hand run.py hooks in ~/.claude/settings.json: every guard runs twice; remove the by-hand entries"
    And the doctor exits 1

  Scenario: a by-hand install alone is checked through its own hook
    Given the user's settings.json has a by-hand guard-recursive-delete hook
    When the doctor runs
    Then the "Claude Code" row is ✓ "by hand, 1 guard in ~/.claude/settings.json"
    And the "fail-closed" row is ✓ matching "`rm -rf ~` was denied through the hook command as installed"
    And the doctor exits 0

  # A project's settings arrive with whatever was checked out, and the doctor
  # runs in CI: it counts their hooks but never runs one.
  Scenario: a by-hand hook in a project's settings is counted, never run
    Given the project's settings have a by-hand guard-recursive-delete hook that leaves a mark
    When the doctor runs
    Then the "Claude Code" row is ✓ "by hand, 1 guard in ~/project/.claude/settings.json"
    And the "fail-closed" row is ! "the by-hand guard-recursive-delete hook is in a project's settings, and the doctor runs no command a project supplies; the canary did not run"
    And the hook left no mark

  Scenario: a disabled plugin fails
    Given languette "cd31356ad5db" is installed at user scope, disabled
    When the doctor runs
    Then the "Claude Code" row is ✗ "plugin cd31356, user scope, is disabled: claude plugin enable languette@languette"
    And the "fail-closed" row is ! "the plugin is disabled, so its hooks do not run; the canary did not run"
    And the doctor exits 1

  Scenario: a hook that lets the canary through fails
    Given languette "cd31356ad5db" is installed at user scope from a copy whose guard-recursive-delete hook allows everything
    When the doctor runs
    Then the "fail-closed" row is ✗ matching "`rm -rf ~` was not denied through the hook command as installed: the hook let it through silently"
    And the doctor exits 1
    And the fake HOME is as it was

  Scenario: guard-recursive-delete turned off skips the canary
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_recursive_delete": false}`
    When the doctor runs
    Then the "fail-closed" row is ! "guard-recursive-delete is off, so `rm -rf ~` would go through; the canary did not run"

  Scenario: the install in effect for the working directory is the project's
    Given languette "cd31356ad5db" is installed at user scope
    And languette "617e6febf158" is installed at project scope for "{HOME}/project"
    And languette "0cf7e0462cc9" is installed at project scope for "{HOME}/elsewhere"
    When the doctor runs in "{HOME}/project/sub"
    Then the "Claude Code" row is ✓ matching "plugin 617e6fe, project scope; "

  Scenario: without the claude CLI the doctor reads installed_plugins.json
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true}`
    And claude plugin list fails
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; 20 guards on, 0 off"
    And the doctor exits 0

  Scenario Outline: what the doctor cannot read is a warning row, never a traceback
    Given languette "cd31356ad5db" is installed at user scope
    And claude plugin list fails
    And "<file>" holds `<text>`
    When the doctor runs
    Then the "Claude Code" row is ! matching "<why>"
    And the doctor prints no traceback

    Examples:
      | file                                     | text                    | why                                                                |
      | ~/.claude/settings.json                  | {not json               | ~/.claude/settings.json is not JSON, so which guards are on is unknown |
      | ~/.claude/settings.json                  | {"pluginConfigs": []}   | pluginConfigs in ~/.claude/settings.json has a shape the doctor does not know |
      | ~/.claude/plugins/installed_plugins.json | {"plugins": {"languette@languette": 3}} | installed_plugins.json has a shape the doctor does not know |
