Feature: doctor
  `languette doctor` says whether languette protects Claude Code here: one row
  per check, each ✓, ! or ✗, and a non-zero exit on any ✗, so CI can run it.
  Each scenario runs it in "{HOME}/project" against a fake HOME, with stubs
  for `claude` and the forge clients, and this repo as the plugin's install path. The
  doctor sends two probes to the installed hooks as payloads, a command that
  does not parse and a recursive delete of a fake path; nothing runs either.

  Background:
    Given a fake HOME
    And gh is signed in

  Scenario: a plugin install whose hooks deny both probes
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true}`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; 24 guards on, 0 off"
    And the "shell parser" row is there
    And the "Claude Code" row comes before the "version" row
    And the "version" row comes before the "shell parser" row
    And the "gh" row is ✓ "signed in"
    And the "parse check" row is ✓ matching "^`echo \"unclosed` was denied: .+, \d+ ms$"
    And the "parse check" row comes before the "fail-closed" row
    And the "fail-closed" row comes before the "gh" row
    And the "fail-closed" row is ✓ matching "`rm -rf /fake/languette-doctor` was denied through the hook command as installed, \d+ ms of 600 s"
    And the "version" row is ! "plugin at commit cd31356, from main; not a release"
    And the doctor exits 0
    And the fake HOME is as it was

  Scenario Outline: a guard is off only when its option says so exactly
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `<options>`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; <counts>"

    Examples:
      | options                                           | counts                               |
      | {"guard_review_threads": true, "guard_signed_comments": true} | 23 guards on, 1 off: guard_worktrees |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": false}   | 23 guards on, 1 off: guard_disks     |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": "false"} | 23 guards on, 1 off: guard_disks     |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": "no"}    | 24 guards on, 0 off                  |
      | {"guard_worktrees": "yes", "guard_review_threads": true, "guard_signed_comments": true} | 23 guards on, 1 off: guard_worktrees |

  Scenario: gh signed out is a warning, not a failure
    Given languette "cd31356ad5db" is installed at user scope
    And gh is signed out
    When the doctor runs
    Then the "gh" row is ! "installed, not signed in" and its note
    And the doctor exits 0

  Scenario Outline: another forge client signed in is a warning, signed out is not
    Given languette "cd31356ad5db" is installed at user scope
    And <client> is signed in
    And <other> is signed out
    When the doctor runs
    Then the "<client>" row is ! "signed in" and its note
    And the "<other>" row is ✓ "installed, not signed in"
    And the "gh" row comes before the "<client>" row
    And the doctor exits 0

    Examples:
      | client | other |
      | glab   | tea   |
      | fj     | glab  |
      | tea    | fj    |

  Scenario: nothing installed fails
    When the doctor runs
    Then the "Claude Code" row is ✗ "languette is not installed for this directory"
    And the "parse check" row is ! "no require-well-formed hook installed to send the probe to"
    And the "fail-closed" row is ✗ "no guard-recursive-delete hook installed to send the probe to"
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
    And the "parse check" row is ! "no require-well-formed hook in the install to send the probe to"
    And the "fail-closed" row is ✓ matching "was denied through the hook command as installed"
    And the doctor exits 0

  # A project's settings arrive with whatever was checked out, and the doctor
  # runs in CI: it counts their hooks but never runs one.
  Scenario: a by-hand hook in a project's settings is counted, never run
    Given the project's settings have a by-hand guard-recursive-delete hook that leaves a mark
    When the doctor runs
    Then the "Claude Code" row is ✓ "by hand, 1 guard in ~/project/.claude/settings.json"
    And the "fail-closed" row is ! "the by-hand guard-recursive-delete hook is in a project's settings, and the doctor runs no command a project supplies; the probe did not run"
    And the hook left no mark

  Scenario: a disabled plugin fails
    Given languette "cd31356ad5db" is installed at user scope, disabled
    When the doctor runs
    Then the "Claude Code" row is ✗ "plugin cd31356, user scope, is disabled: claude plugin enable languette@languette"
    And the "fail-closed" row is ! "the plugin is disabled, so its hooks do not run; the probe did not run"
    And the doctor exits 1

  Scenario: a hook that lets the fail-closed probe through fails
    Given languette "cd31356ad5db" is installed at user scope from a copy whose guard-recursive-delete hook allows everything
    When the doctor runs
    Then the "fail-closed" row is ✗ matching "was not denied through the hook command as installed: the hook let it through silently"
    And the doctor exits 1
    And the fake HOME is as it was

  Scenario: a hook that lets the unparseable command through fails
    Given languette "cd31356ad5db" is installed at user scope from a copy whose require-well-formed hook allows everything
    When the doctor runs
    Then the "parse check" row is ✗ matching "was not denied through the hook command as installed: the hook let it through silently"
    And the "fail-closed" row is ✓ matching "was denied"
    And the doctor exits 1

  Scenario: a plugin install without a require-well-formed hook fails
    Given languette "cd31356ad5db" is installed at user scope from a copy without a require-well-formed hook
    When the doctor runs
    Then the "parse check" row is ✗ "no require-well-formed hook in the install to send the probe to"
    And the "fail-closed" row is ✓ matching "was denied"
    And the doctor exits 1

  Scenario: a deny from the hook's fallback, with run.py missing, fails
    Given languette "cd31356ad5db" is installed at user scope from a copy without run.py
    When the doctor runs
    Then the "fail-closed" row is ✗ matching "was not denied through the hook command as installed: only the fallback denied it, so the guard never judged it: languette/run.py is missing from the plugin directory or crashed"
    And the "parse check" row is ✗ matching "only the fallback denied it"
    And the doctor exits 1

  Scenario: a deny from a guard that crashed fails
    Given languette "cd31356ad5db" is installed at user scope from a copy whose guard-recursive-delete raises when called
    When the doctor runs
    Then the "fail-closed" row is ✗ matching "was not denied through the hook command as installed: only the fallback denied it, so the guard never judged it: guard-recursive-delete: guard crashed \(RuntimeError: canary\)"
    And the doctor exits 1

  Scenario: guard-recursive-delete turned off skips its probe
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_recursive_delete": false}`
    When the doctor runs
    Then the "fail-closed" row is ! "guard-recursive-delete is off, so `rm -rf /fake/languette-doctor` would go through; the probe did not run"
    And the "parse check" row is ✓ matching "was denied"

  Scenario: require-well-formed turned off skips its probe
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"require_well_formed": false}`
    When the doctor runs
    Then the "parse check" row is ! matching "^require-well-formed is off, .* would go through; the probe did not run$"
    And the "fail-closed" row is ✓ matching "was denied"

  Scenario: the install in effect for the working directory is the project's
    Given languette "cd31356ad5db" is installed at user scope
    And languette "617e6febf158" is installed at project scope for "{HOME}/project"
    And languette "0cf7e0462cc9" is installed at project scope for "{HOME}/elsewhere"
    When the doctor runs in "{HOME}/project/sub"
    Then the "Claude Code" row is ✓ matching "plugin 617e6fe, project scope; "

  Scenario: without the claude CLI the doctor reads installed_plugins.json
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true}`
    And claude plugin list fails
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope; 24 guards on, 0 off"
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

  # --- guard-private-terms' files, through the guard's own loader ----------------
  # One row per file, shipped included, so a line the guard would refuse is found
  # here and not at the next public post. features/fixtures/private-terms is the
  # design's example; the doctor reads it to time each re: line it accepts. The time is
  # shown, never the verdict: a re: line is accepted or refused by its shape alone.

  Scenario: each terms file gets a row, counting what loaded
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds the fixture "private-terms/redacted-terms.tsv"
    And "~/.config/languette/blocked-terms.tsv" holds the fixture "private-terms/blocked-terms.tsv"
    When the doctor runs
    Then the "redacted terms" row is ✓ "shipped 9 pairs, 9 re:; ~/.config/languette/redacted-terms.tsv 5 pairs, 1 re:"
    And the "blocked terms" row is ✓ "~/.config/languette/blocked-terms.tsv 3 terms, 1 re:"
    And the doctor exits 0

  Scenario: no blocked terms file is a warning that says what that means
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs
    Then the "blocked terms" row is ! "none at ~/.config/languette/blocked-terms.tsv, and blocked_terms_file is unset: no term is blocked"
    And the "redacted terms" row is ✓ "shipped 9 pairs, 9 re:; none of your own"

  Scenario Outline: a line the guard would refuse fails the row, naming the file and the line
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/<file>" holds `<text>`
    When the doctor runs
    Then the "<row>" row is ✗ "~/.config/languette/<file> line <n>: <why>"
    And the doctor exits 1

    Examples:
      | file               | row            | text                              | n | why                                    |
      | redacted-terms.tsv | redacted terms | re:(a+)+$                         | 1 | a quantifier inside a quantified group |
      | redacted-terms.tsv | redacted terms | zephyr-01\n\nre:x*                | 3 | matches the empty string               |
      | blocked-terms.tsv  | blocked terms  | re:[unclosed                      | 1 | does not compile                       |
      | redacted-terms.tsv | redacted terms | re:.*.*.*.*;                      | 1 | two unbounded repeats in a row over the same characters |
      | blocked-terms.tsv  | blocked terms  | a{TAB}b{TAB}c{TAB}d               | 1 | four columns                           |

  Scenario: a re: with overlapping alternatives in a repeat is refused by its shape, not its speed
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds `re:(?:a|aa)+x`
    When the doctor runs
    Then the "redacted terms" row is ✗ "~/.config/languette/redacted-terms.tsv line 1: overlapping alternatives inside a repeat"
    And the doctor exits 1

  Scenario: a set path that is missing fails the row, as it would fail every public post
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"redacted_terms_file": "~/no-such.tsv"}`
    When the doctor runs
    Then the "redacted terms" row is ✗ "redacted_terms_file is ~/no-such.tsv, which does not exist: every public post is denied until it does"
    And the doctor exits 1

  # Assisting with configuration: show what a post would become.
  Scenario: the doctor shows what a post would become through the files as loaded
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds the fixture "private-terms/redacted-terms.tsv"
    And "~/.config/languette/blocked-terms.tsv" holds the fixture "private-terms/blocked-terms.tsv"
    When the doctor runs with `--redact` and the fixture "private-terms/bad-comment.md"
    Then it prints the fixture "private-terms/bad-comment.redacted.md"
    And it prints "blocked: none"
    When the doctor runs with `--redact` and the fixture "private-terms/bad-comment.md" plus the line "Tested aboard Wanderlust."
    Then it prints "blocked: Wanderlust (the boat's name stays off public repos; say \"the boat\")"
    And the doctor exits 1
