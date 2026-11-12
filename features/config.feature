Feature: config
  `languette config` lists languette's options, sets them and puts them back
  to their defaults, through `claude plugin configure`: the host stays the
  owner, and languette writes no file itself. Every value is judged first, as
  its guard would read it, all of them together: one the guard would refuse
  writes nothing, and the row says why. A switch is exactly `true` or `false`,
  so `config` cannot make a misconfiguration open a gate. Claude Code keeps no
  unset, so `--unset` writes the option's default. Each scenario runs in
  "{HOME}/project" against the doctor's fake HOME, its `claude` stub answering
  as the host does.

  Background:
    Given a fake HOME
    And languette "cd31356ad5db" is installed at user scope

  Scenario: with no arguments it lists every option, its value and where it is set
    Given the languette options are `{"guard_disks": false}`
    When languette config runs
    Then it lists every option in the manifest, in its order
    And it lists "guard_disks" as "false", set in ~/.claude/settings.json
    And it lists "guard_sudo" as "false", default
    And it lists "protected_services" as "(empty)", default
    And the doctor exits 0

  Scenario: an option set by name is written through the host
    Given the languette options are `{}`
    When languette config runs with `guard_recursive_delete=false protected_services=nginx`
    Then it prints ✓ "guard_recursive_delete: true → false"
    And it prints ✓ "protected_services: (empty) → nginx"
    And it prints ✓ "Claude Code: Configuration saved. Restart Claude Code to apply it."
    And the stored options are `{"guard_recursive_delete": false, "protected_services": "nginx"}`
    And the doctor exits 0

  Scenario: --unset puts an option back to its default
    Given the languette options are `{"guard_disks": false, "protected_services": "nginx"}`
    When languette config runs with `--unset guard_disks --unset protected_services`
    Then it prints ✓ "guard_disks: false → true (its default)"
    And it prints ✓ "protected_services: nginx → (empty) (its default)"
    And the stored options are `{"guard_disks": true, "protected_services": ""}`
    And the doctor exits 0

  Scenario Outline: a value the guard would refuse writes nothing, not even the others
    Given the languette options are `{}`
    When languette config runs with `guard_disks=false <setting>`
    Then it prints ✗ "<row>; nothing written"
    And the stored options are `{}`
    And the doctor exits 1

    Examples:
      | setting                         | row                                                                                    |
      | guard_sudo=yes                  | guard_sudo: is a switch, exactly true or false; 'yes' would leave the gate as if unset |
      | signed_comments_signature=(     | signed_comments_signature: is not a regular expression (missing ), unterminated subpattern at position 0) |
      | signed_comments_mcp=yes         | signed_comments_mcp: is not one of deny, ask, allow                                    |
      | redacted_terms_file=~/none.tsv  | redacted_terms_file: ~/none.tsv does not exist                                         |
      | no_such_option=1                | no_such_option: languette has no such option; languette config lists them             |
      | guard_disks                     | guard_disks: is not name=value                                                         |

  Scenario: a terms file the guard loads is taken
    Given "~/terms.tsv" holds `acme{TAB}<client>{TAB}a client's name`
    And the languette options are `{}`
    When languette config runs with `redacted_terms_file=~/terms.tsv`
    Then the stored options are `{"redacted_terms_file": "~/terms.tsv"}`
    And the doctor exits 0

  Scenario: a terms file with a line the guard would refuse writes nothing
    Given "~/terms.tsv" holds `re:(a+)+{TAB}x{TAB}backtracks`
    And the languette options are `{}`
    When languette config runs with `redacted_terms_file=~/terms.tsv`
    Then the stored options are `{}`
    And the doctor exits 1
