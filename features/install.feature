Feature: install
  `languette install` wires languette into Claude Code through its own plugin
  marketplace and writes nothing itself: it asks the `claude` command, and
  only Claude Code writes. Rows in the doctor's format, a non-zero exit on
  any ✗. Each scenario runs it in "{HOME}/project" against a fake HOME, with
  a stub `claude` first on PATH that records every command it is asked.
  {SOURCE} is the marketplace's source, this repo's release branch.

  Background:
    Given a fake HOME and a stub claude

  Scenario: without claude on PATH it fails and asks nothing
    Given claude is not on PATH
    When install runs
    Then the install "Claude Code" row is ✗ "the claude command is not on PATH; install Claude Code, or see Installing by hand in the README"
    And install exits 1
    And the fake HOME is as it was before install

  Scenario: an installed plugin is left as it is
    Given claude lists languette "cd31356ad5db" installed at user scope
    When install runs
    Then the install "Claude Code" row is ✓ "plugin cd31356 already installed, user scope; nothing written"
    And claude was asked only:
      """
      plugin list --json
      """
    And install exits 0

  Scenario: a disabled plugin fails, naming the command that enables it
    Given claude lists languette "cd31356ad5db" installed at user scope, disabled
    When install runs
    Then the install "Claude Code" row is ✗ "plugin cd31356, user scope, is disabled: claude plugin enable languette@languette"
    And claude was asked only:
      """
      plugin list --json
      """
    And install exits 1

  Scenario: a fresh install adds the marketplace, then installs the plugin
    When install runs
    Then the install "marketplace" row is ✓ "{SOURCE} added"
    And the install "Claude Code" row is ✓ "plugin installed, user scope; run languette doctor"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      plugin marketplace add {SOURCE}
      plugin install languette@languette
      """
    And install exits 0
    And the fake HOME is as it was before install

  Scenario: a marketplace already added is not added again
    Given claude lists the languette marketplace
    When install runs
    Then the install "marketplace" row is ✓ "{SOURCE} already added"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      plugin install languette@languette
      """
    And install exits 0

  Scenario: a marketplace add that answers "already exists" counts as added
    Given claude plugin marketplace add fails with "Marketplace 'languette' already exists"
    When install runs
    Then the install "marketplace" row is ✓ "{SOURCE} already added"
    And the install "Claude Code" row is ✓ "plugin installed, user scope; run languette doctor"
    And install exits 0

  Scenario: a failed marketplace add stops before the plugin install
    Given claude plugin marketplace add fails with "Failed to clone repository"
    When install runs
    Then the install "marketplace" row is ✗ "Failed to clone repository"
    And claude was asked only:
      """
      plugin list --json
      plugin marketplace list --json
      plugin marketplace add {SOURCE}
      """
    And install exits 1

  Scenario: a host other than claude is an error that says others are planned
    When install runs for "codex"
    Then install exits 2
    And install says on stderr "other hosts are planned (#5)"
    And claude was asked nothing
