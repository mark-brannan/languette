@shell
Feature: prose-budget-commit
  Before a `git commit`, runs the prose-budget engine
  (mark-brannan/claude, bin/prose-budget) with --staged and denies on a
  finding. The engine is never bundled here, so every scenario stubs it
  through PROSE_BUDGET; without that (or any engine on PATH) the guard is
  silent -- it can only narrow what already passes, never widen it.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"
    And the stub "prose-budget" is the engine

  Scenario Outline: a commit is judged, and detected however it is spelled
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                  | note                     |
      | git commit -m "docs: more"                | plain commit             |
      | git add README.md && git commit -m x      | after a separator        |
      | yadm commit -m x                           | yadm is git              |
      | git -C {PROJ} commit -m x                   | -C dir                   |
      | cd {PROJ} && git commit -m x                | cd dir && commit         |
      | git merge --continue                        | finishing a merge        |

  Scenario Outline: prose outside a real commit is not a commit
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                   | note                       |
      | git status                                | not a commit               |
      | echo "run git commit -m x"                 | prose that names a command is not the command |
      | gh pr create --title x                      | a different tool           |

  Scenario: a commit mentioned in a heredoc body is not run
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs:
      """
      cat <<EOF
      git commit -m x
      EOF
      """
    Then the guard is silent

  Scenario: the engine reports clean staging
    When the agent runs `git commit -m x`
    Then the guard is silent

  Scenario Outline: an engine crash with an unusual exit code is a no-op, by design
    Given PROSE_BUDGET_CRASH is "<code>"
    When the agent runs `git commit -m x`
    Then the guard is silent

    Examples:
      | code |
      | 126  |
      | 127  |
      | 139  |

  Scenario: the deny reason carries the engine's findings and the retry instruction
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `git commit -m x`
    Then the guard denies, naming "sections.max_words"
    And the guard denies, naming "not a judgment call"

  Scenario Outline: a working directory this guard cannot resolve is denied, not skipped
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard denies, naming "could not be resolved"

    Examples:
      | command                               | note                        |
      | cd nonexistent-dir-xyz && git commit -m x | an unresolvable cd target |
      | git -C nonexistent-dir-xyz commit -m x    | an unresolvable -C target |

  Scenario: exit 2, a bad budgets config, denies and says so
    Given PROSE_BUDGET_CRASH is "2"
    When the agent runs `git commit -m x`
    Then the guard denies, naming "bad budgets config"

  Scenario Outline: each cd and -C is folded onto the one before it
    Given the file "a/b/keep" holds:
      """
      x
      """
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard denies, naming "sections.max_words"

    Examples:
      | command                          | note                     |
      | cd a && cd b && git commit -m x  | two cds                  |
      | git -C a -C b commit -m x        | two -C                   |
      | cd a && git -C b commit -m x     | a cd, then a -C          |
      | cd a; cd b; git commit -m x      | separated by semicolons  |

  Scenario: a relative PROSE_BUDGET still resolves after the hook changes directory
    Given the stub "prose-budget" is the engine, at a relative path
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `cd sub && git commit -m x`
    Then the guard denies, naming "sections.max_words"

  Scenario: a bare-name PROSE_BUDGET is looked up on PATH, not under the project
    Given the stub "prose-budget" is the engine, by bare name on PATH
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `git commit -m x`
    Then the guard denies, naming "sections.max_words"

  @shell_only
  Scenario: with no engine on PROSE_BUDGET or PATH the guard is silent
    Given PROSE_BUDGET is unset
    And PATH holds only "sh jq awk cat cut dirname"
    When the agent runs `git commit -m x`
    Then the guard is silent

  @shell_only
  Scenario: with no jq on PATH the guard is silent
    Given PATH holds only "sh awk cat cut dirname"
    When the agent runs `git commit -m x`
    Then the guard is silent
