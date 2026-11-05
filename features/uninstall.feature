Feature: uninstall
  `languette uninstall` reverses `languette install` for Claude Code. It lists
  what install wrote, the plugin at user scope and the marketplace added from
  {REPO}, asks, and on a yes asks the `claude` command to remove them, the
  plugin first. Anything install did not write is left and named: an install
  at another scope, a marketplace of the same name from elsewhere. The terms
  files and the plugin's options are left; Claude Code drops the options when
  it removes the plugin, so they are written back. Rows in the doctor's format,
  a non-zero exit on any ✗. Each scenario runs it in "{HOME}/project" against
  a fake HOME, with the stub `claude` install.feature uses.

  Background:
    Given a fake HOME and a stub claude

  Scenario: without claude on PATH it fails and removes nothing
    Given claude is not on PATH
    When uninstall runs, answering "y"
    Then the uninstall "Claude Code" row is ✗ "the claude command is not on PATH, so nothing can be removed through it"
    And uninstall exits 1
    And the fake HOME is as it was before uninstall

  Scenario: with nothing installed it asks nothing and removes nothing
    When uninstall runs, answering "y"
    Then the uninstall "uninstall" row is ✓ "nothing install wrote is here; nothing removed"
    And uninstall did not ask
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      """
    And uninstall exits 0

  Scenario: on a yes it removes the plugin, then the marketplace
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists the languette marketplace
    When uninstall runs, answering "y"
    Then uninstall listed, before asking:
      """
      Claude Code   languette@languette, plugin cd31356, user scope
      marketplace   languette, added from {REPO}
      """
    And the uninstall "Claude Code" row is ✓ "languette@languette removed"
    And the uninstall "marketplace" row is ✓ "languette removed"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      plugin uninstall languette@languette --scope user
      plugin marketplace remove languette --scope user
      """
    And uninstall exits 0

  Scenario: without a yes it removes nothing
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists the languette marketplace
    When uninstall runs, answering ""
    Then the uninstall "uninstall" row is ! "nothing removed"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      """
    And uninstall exits 0
    And the fake HOME is as it was before uninstall

  Scenario: the plugin's options are still in the user's settings afterwards
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists the languette marketplace
    And the user's settings hold the languette options `{"guard_worktrees": true}`
    When uninstall runs, answering "y"
    Then the uninstall "options" row is ✓ "kept in ~/.claude/settings.json"
    And the user's settings hold the languette options `{"guard_worktrees": true}`
    And uninstall exits 0

  Scenario: the terms files are left as they are
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists the languette marketplace
    And the redacted terms file holds "zephyr-01\tthe boat"
    When uninstall runs, answering "y"
    Then the redacted terms file is unchanged
    And uninstall exits 0

  Scenario: an install at project scope is left, and named
    Given claude lists languette "cd31356ad5db" installed at project scope for "{HOME}/project"
    And claude lists the languette marketplace
    When uninstall runs, answering "y"
    Then the uninstall "Claude Code" row is ! "languette@languette, plugin cd31356, project scope for ~/project, left: install did not write it"
    And the uninstall "marketplace" row is ! "languette, added from {REPO}, left: 1 install(s) still come from it"
    And uninstall did not ask
    And uninstall exits 0

  Scenario: a marketplace of the same name from another repo is left, with its plugin
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists a languette marketplace from "someone/fork"
    When uninstall runs, answering "y"
    Then the uninstall "marketplace" row is ! "languette is added from someone/fork, not {REPO}; left: install did not write it"
    And the uninstall "Claude Code" row is ! "languette@languette, plugin cd31356, user scope, left: install did not write it"
    And the uninstall "uninstall" row is ✓ "nothing install wrote is here; nothing removed"
    And uninstall did not ask
    And uninstall exits 0

  Scenario: a failed plugin removal stops before the marketplace
    Given claude lists languette "cd31356ad5db" installed at user scope
    And claude lists the languette marketplace
    And claude plugin uninstall fails with "Plugin is busy"
    When uninstall runs, answering "y"
    Then the uninstall "Claude Code" row is ✗ "Plugin is busy"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      plugin uninstall languette@languette --scope user
      """
    And uninstall exits 1

  Scenario: a host other than claude is an error that says others are planned
    When uninstall runs for "codex"
    Then uninstall exits 2
    And uninstall says on stderr "other hosts are planned (#5)"
    And claude was asked nothing
