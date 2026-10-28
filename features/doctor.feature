Feature: doctor
  `languette doctor` says whether languette protects Claude Code here: one row
  per check, each ✓, ! or ✗, and a non-zero exit on any ✗, so CI can run it.
  Each scenario runs it in "{HOME}/project" against a fake HOME, with stubs
  for `claude` and the forge clients, and this repo as the plugin's install path. The
  doctor sends two probes to the installed hooks as payloads, a command that
  does not parse and a recursive delete of a fake path; nothing runs either.
  A ✗ never stops a later check: every check that can run does, and the exit
  code is decided once, after the last row. A check that cannot run because
  something it needs failed is a ! row saying so, never skipped silently,
  except fail-closed: no hook to probe means no protection, so it is ✗.
  Rows run in this order: version, shell parser, parse check, fail-closed,
  Claude Code (its guards beneath it), gh, the other forge clients, redacted
  terms, blocked terms. A row's detail lines are indented beneath it.

  Background:
    Given a fake HOME
    And gh is signed in

  @planned
  Scenario: a plugin install whose hooks deny both probes
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true}`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope"
    And beneath it "guards enabled: 24" is ✓ and "guards disabled: 0" is ✓
    And the "shell parser" row is there
    And the "version" row comes before the "shell parser" row
    And the "shell parser" row comes before the "parse check" row
    And the "parse check" row comes before the "fail-closed" row
    And the "fail-closed" row comes before the "Claude Code" row
    And the "Claude Code" row comes before the "gh" row
    And the "gh" row is ✓ "signed in"
    And the "parse check" row is ✓ matching "^`echo \"unclosed` was denied: .+, \d+ ms$"
    And the "fail-closed" row is ✓ matching "`rm -rf /fake/languette-doctor` was denied through the hook command as installed, \d+ ms of 600 s"
    And the "version" row is ! "plugin at commit cd31356, from main; not a release"
    And the doctor exits 0
    And the fake HOME is as it was

  @planned
  Scenario Outline: a guard is off only when its option says so exactly
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `<options>`
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope"
    And beneath it "guards enabled: <on>" is ✓
    And beneath it "guards disabled: <off>" is <mark>
    And beneath that, one ! line per off guard, "(off) <guard>: " and its one-line description

    Examples:
      | options                                                                                                       | on | off | mark | guard          |
      | {"guard_review_threads": true, "guard_signed_comments": true}                                                 | 23 | 1   | !    | guard_worktrees |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": false}   | 23 | 1   | !    | guard_disks    |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": "false"} | 23 | 1   | !    | guard_disks    |
      | {"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true, "guard_disks": "no"}    | 24 | 0   | ✓    |                |
      | {"guard_worktrees": "yes", "guard_review_threads": true, "guard_signed_comments": true}                       | 23 | 1   | !    | guard_worktrees |

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

  @planned
  Scenario: without the claude CLI the doctor reads installed_plugins.json
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_worktrees": true, "guard_review_threads": true, "guard_signed_comments": true}`
    And claude plugin list fails
    When the doctor runs
    Then the "Claude Code" row is ✓ "plugin cd31356, user scope"
    And beneath it "guards enabled: 24" is ✓
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
  # A row per terms file, counting only the entries in that file; the doctor can write
  # the default entries into it (--init-redacted-terms) but never counts a set the file lacks.
  # features/fixtures/private-terms is the design's example; the doctor reads it to time
  # each re: line it accepts. The times are shown, never the verdict: a re: line is
  # accepted or refused by its shape alone, and a slow one is a ! warning, exit 0. Every bad line is reported, and the valid
  # ones are still loaded and timed.

  @planned
  Scenario: a terms file gets a row, its path and entry count, and the timings of its re: lines
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds the fixture "private-terms/redacted-terms.tsv"
    And "~/.config/languette/blocked-terms.tsv" holds the fixture "private-terms/blocked-terms.tsv"
    When the doctor runs
    Then the "redacted terms" row is ✓ "enabled"
    And beneath it "~/.config/languette/redacted-terms.tsv (5 entries)" is ✓
    And beneath it a line is ✓ matching "^1 regular expression \(min=\d+\.\d\dms, max=\d+\.\d\dms, avg=\d+\.\d\dms\)$"
    And the "blocked terms" row is ✓ "enabled"
    And beneath it "~/.config/languette/blocked-terms.tsv (3 entries)" is ✓
    And the doctor exits 0

  @planned
  Scenario: a re: slower than the threshold is listed on its own line, with its line number and its first characters
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds `a\nb\nc\nre:(?:Wanderlust|Wanderer)\s+aboard\b`
    And the doctor's clock times the re: on line 4 at 7.20 ms and every other at 0.02 ms
    When the doctor runs
    Then beneath the "redacted terms" row a line is ! matching "^slow regular expressions \(> \d+\.\dms\)$"
    And beneath that, "line 4:  re:(?:Wanderlust|Wanderer)\s+a…  7.20 ms"
    And the doctor exits 0

  # The marks follow what the guard does with each file: on with no file is a !,
  # off with no file is a ✓, a file it cannot read is a ✗. An empty file is one
  # step stricter than the guard, which judges by it without complaint: a !.
  Scenario: no blocked terms file, with the guard on, is a warning that says what that means
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs
    Then the "blocked terms" row is ! "none at ~/.config/languette/blocked-terms.tsv, and blocked_terms_file is unset: no term is blocked"

  @planned
  Scenario: no redacted terms file, with the guard on, is a warning that names the fix
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs
    Then the "redacted terms" row is ! "none at ~/.config/languette/redacted-terms.tsv: nothing is redacted"
    And beneath it "run `languette doctor --init-redacted-terms` to write the defaults" is !
    And the doctor exits 0

  @planned
  Scenario: no terms files, with the guard off, is fine
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"guard_private_terms": false}`
    When the doctor runs
    Then the "redacted terms" row is ✓ "off, and none at ~/.config/languette/redacted-terms.tsv"
    And the "blocked terms" row is ✓ "off, and none at ~/.config/languette/blocked-terms.tsv"
    And the doctor exits 0

  @planned
  Scenario Outline: an empty terms file is a warning, though the guard accepts it
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/<file>" holds ``
    When the doctor runs
    Then the "<row>" row is ! "enabled"
    And beneath it "~/.config/languette/<file> (0 entries)" is !
    And the doctor exits 0

    Examples:
      | file               | row            |
      | redacted-terms.tsv | redacted terms |
      | blocked-terms.tsv  | blocked terms  |

  @planned
  Scenario Outline: a terms file the guard cannot read fails the row, as it would fail every public post
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/<file>" <state>
    When the doctor runs
    Then the "<row>" row is ✗ "~/.config/languette/<file> <why>: every public post is denied until it is fixed"
    And the doctor exits 1

    Examples:
      | file               | row            | state                       | why             |
      | redacted-terms.tsv | redacted terms | is a directory              | is a directory  |
      | blocked-terms.tsv  | blocked terms  | exists but is not readable  | is not readable |

  @planned
  Scenario Outline: a line the guard would refuse fails the row, naming the line
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/<file>" holds `<text>`
    When the doctor runs
    Then beneath the "<row>" row "line <n>: <why>" is ✗
    And the doctor exits 1

    Examples:
      | file               | row            | text                              | n | why                                    |
      | redacted-terms.tsv | redacted terms | re:(a+)+$                         | 1 | a quantifier inside a quantified group |
      | redacted-terms.tsv | redacted terms | zephyr-01\n\nre:x*                | 3 | matches the empty string               |
      | blocked-terms.tsv  | blocked terms  | re:[unclosed                      | 1 | does not compile                       |
      | redacted-terms.tsv | redacted terms | re:.*.*.*.*;                      | 1 | two unbounded repeats in a row over the same characters |
      | blocked-terms.tsv  | blocked terms  | a{TAB}b{TAB}c{TAB}d               | 1 | four columns                           |
      | redacted-terms.tsv | redacted terms | re:(?:a\|aa)+x                    | 1 | overlapping alternatives inside a repeat |

  @planned
  Scenario: every bad line is listed, and the valid re: lines are still timed
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds a malformed line 13, an empty-matching re: line 17, a nested-quantifier line 22 and 8 valid re: lines
    When the doctor runs
    Then beneath the "redacted terms" row "line 13", "line 17" and "line 22" are each ✗ with their reasons
    And beneath it a line is ✗ matching "^10 regular expressions, 2 invalid \(min=\d+\.\d\dms, max=\d+\.\d\dms, avg=\d+\.\d\dms\)$"
    And the doctor exits 1

  @planned
  Scenario: a failed check does not stop the ones after it
    When the doctor runs
    Then the "Claude Code" row is ✗ "languette is not installed for this directory"
    And the "redacted terms" row is there
    And the "blocked terms" row is there
    And the last line is "2 problems; exit 1"
    And the doctor exits 1

  Scenario: a set path that is missing fails the row, as it would fail every public post
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"redacted_terms_file": "~/no-such.tsv"}`
    When the doctor runs
    Then the "redacted terms" row is ✗ "redacted_terms_file is ~/no-such.tsv, which does not exist: every public post is denied until it does"
    And the doctor exits 1

  # Mending configuration: a default entry is a copied line tagged default:<name>@<version>
  # in its comment column; the user's own lines are never touched.
  @planned
  Scenario: --init-redacted-terms writes the file with every default entry
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs with `--init-redacted-terms`
    Then "~/.config/languette/redacted-terms.tsv" holds the default entries
    And it prints "✓ wrote ~/.config/languette/redacted-terms.tsv (3 defaults)"
    And the doctor exits 0

  @planned
  Scenario: --init-blocked-terms writes the file with a header and no terms
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs with `--init-blocked-terms`
    Then "~/.config/languette/blocked-terms.tsv" holds a header and no terms
    And the doctor exits 0

  @planned
  Scenario Outline: an init never overwrites a file, and names the repair
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/<file>" holds `zephyr-01\tthe boat`
    When the doctor runs with `<flag>`
    Then "~/.config/languette/<file>" is unchanged
    And it prints ✗ "~/.config/languette/<file> exists<fix>"
    And the doctor exits 1

    Examples:
      | flag                  | file               | fix                                                      |
      | --init-redacted-terms | redacted-terms.tsv | ; to repair it: languette doctor --restore-redacted-terms |
      | --init-blocked-terms  | blocked-terms.tsv  |                                                          |

  @planned
  Scenario: --restore-redacted-terms adds a missing default in order and leaves the rest alone
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds every default entry but "host", with "private-ip" commented out, and the line "zephyr-01\tthe boat"
    When the doctor runs with `--restore-redacted-terms` and answers yes
    Then it prints the diff before writing
    And "host" is back where it sits in the defaults' order
    And "private-ip" is still commented out
    And the line "zephyr-01\tthe boat" is unchanged
    And running it again changes nothing

  @planned
  Scenario: --restore-redacted-terms updates an unedited default and reports an edited one
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds "home" as an earlier version wrote it, and "host" edited by hand
    When the doctor runs with `--restore-redacted-terms` and answers yes
    Then "home" holds the current version
    And "host" is unchanged, and it prints that "host" was edited by hand

  @planned
  Scenario: --restore-redacted-terms writes nothing without a yes
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds every default entry but "host"
    When the doctor runs with `--restore-redacted-terms` and answers no
    Then "~/.config/languette/redacted-terms.tsv" is unchanged

  @planned
  Scenario: --restore-redacted-terms with no file names the init
    Given languette "cd31356ad5db" is installed at user scope
    When the doctor runs with `--restore-redacted-terms`
    Then it prints ✗ "none at ~/.config/languette/redacted-terms.tsv; to create it: languette doctor --init-redacted-terms"
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

  @planned
  Scenario: doctor --help shows the parent command's help too
    When the doctor runs with `--help`
    Then it prints the doctor's own options
    And it then prints everything `languette --help` prints
    And the doctor exits 0

  @planned
  Scenario Outline: --redact reads stdin when it is given no file, or "-"
    Given languette "cd31356ad5db" is installed at user scope
    And "~/.config/languette/redacted-terms.tsv" holds the fixture "private-terms/redacted-terms.tsv"
    When the doctor runs with `<args>` and the fixture "private-terms/bad-comment.md" on stdin
    Then it prints the fixture "private-terms/bad-comment.redacted.md"
    And the doctor exits 0

    Examples:
      | args       |
      | --redact   |
      | --redact - |

  Scenario: --redact loads the files the installed plugin's options name, as the rows and the guard do
    Given languette "cd31356ad5db" is installed at user scope
    And the languette options are `{"blocked_terms_file": "~/mine.tsv"}`
    And "~/mine.tsv" holds `Wanderlust`
    When the doctor runs with `--redact` and the fixture "private-terms/bad-comment.md" plus the line "Tested aboard Wanderlust."
    Then it prints "blocked: Wanderlust"
    And the doctor exits 1
