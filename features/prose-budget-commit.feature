@python
Feature: prose-budget-commit
  Before a `git commit`, runs the prose-budget engine with --staged and
  warns on a finding; the commit still runs, because CI is the gate. The
  engine is the command the prose_budget_command option names, else
  prose-budget on PATH; it is never bundled here, so every scenario stubs it.
  Without an engine the guard is silent -- it only ever adds a note to a call
  that already passes.

  Why. Documentation bloat should be caught as it is written, not at the
  push. The guard runs on a `git commit`: `--staged` checks the index, and a
  commit that reaches past it (-a, a pathspec, an `add` in the same command,
  -p, --pathspec-from-file) also runs `--file` on what it would commit. No
  engine, no budgets config in the target repo, or an engine crash is a
  no-op. Exit 1 is a finding and warns, naming the file, the number and that
  CI fails on it; exit 2 (a bad budgets config, or an engine too old for
  --staged/--file) warns and says so; any other exit is a no-op. A commit
  that reaches past the index gets both checks' warnings together, since
  nothing is blocked and so nothing is retried.

  Silent on what it cannot resolve: anything the guard cannot read (a `cd` or
  `-C` target, a pathspec word, a directory pathspec, a failed `diff` or
  `ls-files`, a second commit in a different directory, since one check
  cannot serve two repositories) allows with no message and runs no engine
  for that part. A directory, glob or magic
  (`:`-led) pathspec names more than itself, so it widens the check to every
  unstaged tracked change rather than being passed on as a literal --file
  argument the engine would fail to find; an `add` by pattern (`-A`, `.`,
  `*`) or an interactive commit can also pick up a brand new untracked file,
  which a tracked-only diff cannot see. A relative engine path means relative
  to the commit's own cwd, resolved before any `cd`; a bare name is a command
  looked up on PATH. `yadm` is recognised as git's wrapper word only, as in
  the other guards, and is never called unless the command named it; the
  wrapper word is read for which CLI it names and never executed, being as
  attacker-controlled as the rest of the command.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"
    And the stub "prose-budget" is the engine

  Scenario Outline: a commit is judged, and detected however it is spelled
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard warns about "CI fails on this; fix before the push."

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

  Scenario: the warning carries the engine's findings and says CI is the gate
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `git commit -m x`
    Then the guard warns about "README.md:3: sections.max_words"
    And the guard warns about "CI fails on this; fix before the push."

  Scenario Outline: a working directory this guard cannot resolve is silent, and the engine does not run
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was not called

    Examples:
      | command                               | note                        |
      | cd nonexistent-dir-xyz && git commit -m x | an unresolvable cd target |
      | git -C nonexistent-dir-xyz commit -m x    | an unresolvable -C target |

  Scenario: exit 2, a bad budgets config, warns and says so
    Given PROSE_BUDGET_CRASH is "2"
    When the agent runs `git commit -m x`
    Then the guard warns about "bad budgets config"

  Scenario: exit 2 from the --file check warns too
    Given the file "README.md" holds:
      """
      x
      """
    And PROSE_BUDGET_CRASH is "2"
    When the agent runs `git commit -m x README.md`
    Then the guard warns about "engine too old for --file"

  Scenario: a commit that reaches past the index warns for both checks
    Given the file "README.md" holds:
      """
      x
      """
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `git commit -m x README.md`
    Then the guard warns about "prose-budget --staged found"
    And the guard warns about "checked those files directly"

  Scenario Outline: each cd and -C is folded onto the one before it
    Given the file "a/b/keep" holds:
      """
      x
      """
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard warns about "sections.max_words"

    Examples:
      | command                          | note                     |
      | cd a && cd b && git commit -m x  | two cds                  |
      | git -C a -C b commit -m x        | two -C                   |
      | cd a && git -C b commit -m x     | a cd, then a -C          |
      | cd a; cd b; git commit -m x      | separated by semicolons  |

  Scenario: a relative engine command still resolves after the hook changes directory
    Given the stub "prose-budget" is the engine, at a relative path
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `cd sub && git commit -m x`
    Then the guard warns about "sections.max_words"

  Scenario: a bare-name engine command is looked up on PATH, not under the project
    Given the stub "prose-budget" is the engine, by bare name on PATH
    And PROSE_BUDGET_FAIL is "1"
    When the agent runs `git commit -m x`
    Then the guard warns about "sections.max_words"

  Scenario Outline: a commit that reaches outside the staged index also checks those paths directly
    Given the file "README.md" holds:
      """
      x
      """
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was called with "--staged"
    And the stub "prose-budget" was called with "--file README.md"

    Examples:
      | command                               | note                      |
      | git commit -m x README.md             | trailing pathspec         |
      | git commit -m x -- README.md          | pathspec after --         |
      | git add README.md && git commit -m x  | add, then commit, in one  |

  Scenario: a `-a`/`--all` commit checks every unstaged tracked change, not just what's staged
    Given the file "README.md" holds:
      """
      x
      """
    And the file "README.md" is committed
    And the file "README.md" holds:
      """
      y
      """
    When the agent runs `git commit -am x`
    Then the guard is silent
    And the stub "prose-budget" was called with "--staged"
    And the stub "prose-budget" was called with "--file "
    And the stub "prose-budget" was called with "README.md"

  Scenario: a `-a` commit with several changed files checks each one, not their names run together
    Given the file "NOTES.md" holds:
      """
      x
      """
    And the file "NOTES.md" is committed
    And the file "README.md" holds:
      """
      x
      """
    And the file "README.md" is committed
    And the file "NOTES.md" holds:
      """
      y
      """
    And the file "README.md" holds:
      """
      y
      """
    When the agent runs `git commit -am x`
    Then the guard is silent
    And the stub "prose-budget" was called with "/NOTES.md /"
    And the stub "prose-budget" was called with "/README.md"

  Scenario: an `add` by pattern checks several new files, a non-ASCII name among them
    Given the file "NOTES.md" holds:
      """
      x
      """
    And the file "café.md" holds:
      """
      x
      """
    When the agent runs `git add . && git commit -m x`
    Then the guard is silent
    And the stub "prose-budget" was called with "/NOTES.md /"
    And the stub "prose-budget" was called with "/café.md"

  Scenario: a message stuck to `-m` does not swallow the pathspec after it
    Given the file "README.md" holds:
      """
      x
      """
    When the agent runs `git commit -mfix README.md`
    Then the guard is silent
    And the stub "prose-budget" was called with "--file README.md"

  Scenario: an `add` by pattern also checks a brand-new, still-untracked file
    Given the file "NOTES.md" holds:
      """
      x
      """
    When the agent runs `git add . && git commit -m x`
    Then the guard is silent
    And the stub "prose-budget" was called with "NOTES.md"

  Scenario: a pathspec starting with "-" cannot be read as one of the engine's own options
    When the agent runs `git commit -m x -- --staged`
    Then the guard is silent
    And the stub "prose-budget" was called with "--file ./--staged"

  Scenario: a pathspec that is a directory on disk is silent, and the engine does not run
    When the agent runs `git commit -m x sub`
    Then the guard is silent
    And the stub "prose-budget" was not called

  Scenario: an `add` flag this guard doesn't recognize widens rather than narrows
    Given the file "README.md" holds:
      """
      x
      """
    And the file "README.md" is committed
    And the file "README.md" holds:
      """
      y
      """
    When the agent runs `git add --unknown-flag && git commit -m x`
    Then the guard is silent
    And the stub "prose-budget" was called with "README.md"

  Scenario: a repo root git cannot find still leaves the files the commit names to be checked
    Given the file "README.md" holds:
      """
      x
      """
    And the project directory is not a git repository
    When the agent runs `git commit -am x README.md`
    Then the guard is silent
    And the stub "prose-budget" was called with "--file README.md"

  Scenario: a failed listing still leaves the files the commit names to be checked
    Given the file "README.md" holds:
      """
      x
      """
    And the project's git index is corrupt
    When the agent runs `git commit -am x README.md`
    Then the guard is silent
    And the stub "prose-budget" was called with "--file README.md"

  Scenario: a plain commit with nothing outside the index is not also checked by path
    When the agent runs `git commit -m x`
    Then the guard is silent
    And the stub "prose-budget" was called 1 times

  Scenario: a pathspec this guard cannot resolve is silent, and the engine does not run
    When the agent runs `git commit -m x "a file.md"`
    Then the guard is silent
    And the stub "prose-budget" was not called

  Scenario Outline: a `--pathspec-from-file` commit reaches past the index, so every unstaged tracked change is checked
    Given the file "README.md" holds:
      """
      x
      """
    And the file "README.md" is committed
    And the file "README.md" holds:
      """
      y
      """
    And the file "list.txt" holds:
      """
      README.md
      """
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was called with "--staged"
    And the stub "prose-budget" was called with "--file "
    And the stub "prose-budget" was called with "/README.md"

    Examples:
      | command                                          | note                |
      | git commit -m x --pathspec-from-file=list.txt    | stuck to the option |
      | git commit -m x --pathspec-from-file list.txt    | as the next word    |

  Scenario Outline: an interactive commit can stage any hunk or a new file, so both listings are checked
    Given the file "README.md" holds:
      """
      x
      """
    And the file "README.md" is committed
    And the file "README.md" holds:
      """
      y
      """
    And the file "NOTES.md" holds:
      """
      x
      """
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was called with "--staged"
    And the stub "prose-budget" was called with "/README.md"
    And the stub "prose-budget" was called with "/NOTES.md"

    Examples:
      | command                         | note                      |
      | git commit -p -m x              | -p                        |
      | git commit --patch -m x         | --patch                   |
      | git commit --interactive -m x   | --interactive             |
      | git commit -pm x                | -p in a short cluster     |

  Scenario Outline: a second commit in the same directory is checked too, not just the first
    Given the file "README.md" holds:
      """
      x
      """
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was called with "--staged"
    And the stub "prose-budget" was called with "--file README.md"

    Examples:
      | command                                                  | note                          |
      | git commit -m a && git commit -m b README.md             | pathspec on the second commit |
      | git commit -m a && git add README.md && git commit -m b  | an add after the first commit |
      | git merge --continue && git commit -m b README.md        | after finishing a merge       |

  Scenario Outline: a second commit in a different directory is silent, since one check cannot serve two repositories
    Given PROSE_BUDGET_FAIL is "1"
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "prose-budget" was not called

    Examples:
      | command                                      | note                 |
      | git commit -m a && cd sub && git commit -m b | a cd between them    |
      | git commit -m a && git -C sub commit -m b    | -C on the second     |
      | git commit -m a && yadm commit -m b          | git, then yadm       |

  Scenario: with no engine configured or on PATH the guard is silent
    Given no engine is configured
    And PATH holds only "sh"
    When the agent runs `git commit -m x`
    Then the guard is silent
