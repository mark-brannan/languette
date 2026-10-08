@python @shell
Feature: guard-worktrees
  Opt-in: the plugin option guard_worktrees turns this guard on (see
  wiring.feature). For a $HOME that is itself a worktree (yadm, a bare-repo
  setup), a checkout or switch there changes the branch every shell and
  session on the machine sees. Every scenario runs against a fake $HOME that
  holds a real .git, so the verdict does not depend on the machine's own.

  Background:
    Given HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the directory "{TMP}/subdir"
    And a git repository at "{TMP}/.claude/worktrees/fake-task"
    And a project directory

  Scenario Outline: a branch switch in $HOME is denied
    Given the working directory is "{TMP}"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                          |
      | yadm checkout some-branch                        |
      | git checkout some-branch                         |
      | yadm checkout -b new-branch                      |
      | yadm checkout -B new-branch                      |
      | echo hi && yadm checkout some-branch             |
      | git switch some-branch                           |
      | git switch -c new-branch                         |
      | git switch some-branch --                        |
      | git checkout some-branch --                      |
      | yadm checkout some-branch --                     |
      | yadm checkout some-branch && ls --               |
      | yadm checkout some-branch # --                   |
      | /usr/bin/yadm checkout some-branch               |
      | ./yadm checkout some-branch                      |
      | /usr/bin/git checkout some-branch                |
      | yadm     checkout    some-branch                 |
      | yadm checkout .                                  |

  # yadm hardcodes --work-tree=$HOME into every invocation, so where it is
  # run from does not matter.
  Scenario Outline: yadm ignores the working directory, so it is denied anywhere
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | cwd    | command                          |
      | {PROJ} | yadm checkout some-branch        |
      | /tmp   | yadm checkout some-branch        |
      | {PROJ} | yadm switch some-branch          |
      | /tmp   | sh -c 'yadm checkout some-branch' |
      | /nonexistent | yadm checkout some-branch  |

  Scenario Outline: plain git reaches $HOME's worktree only if git resolves there
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | cwd         | command                                                         |
      | {TMP}/subdir | git checkout some-branch                                       |
      | {PROJ}      | git -C "$HOME" switch some-branch                                |
      | {PROJ}      | git -C "$HOME" checkout some-branch                              |
      | {PROJ}      | git -C $HOME checkout some-branch                                |
      | {PROJ}      | git -C ~ checkout some-branch                                    |
      | {PROJ}      | git -C {TMP} checkout some-branch                                |
      | /tmp        | git --work-tree={TMP} checkout some-branch                       |
      | /tmp        | git --git-dir={TMP}/.git --work-tree={TMP} checkout some-branch  |
      | /tmp        | git --work-tree {TMP} checkout some-branch                       |
      | /tmp        | git --git-dir {TMP}/.git --work-tree {TMP} checkout some-branch  |
      | /tmp        | GIT_DIR={TMP}/.git GIT_WORK_TREE={TMP} git checkout some-branch  |
      | /tmp        | GIT_WORK_TREE={TMP} git checkout some-branch                     |
      | /tmp        | git --namespace=foo --work-tree={TMP} checkout some-branch       |

  # The command can move where git runs before it gets there.
  Scenario Outline: a cd, a chained -C or an exported GIT_DIR that lands in $HOME is denied
    Given the working directory is "{PROJ}"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                                    |
      | cd ~ && git checkout some-branch                                           |
      | cd {TMP}; git switch some-branch                                           |
      | pushd {TMP}/subdir && git checkout some-branch                             |
      | cd && git checkout some-branch                                             |
      | export GIT_DIR={TMP}/.git; git checkout some-branch                        |
      | git -C {TMP}/.claude/worktrees/fake-task -C ../../.. checkout some-branch  |

  # yadm keeps its repo outside $HOME, with core.worktree pointing back at it.
  Scenario: --git-dir to a repo whose work tree is $HOME is denied
    Given a yadm-style repository at "{TMP}/.local/share/yadm/repo.git" whose work tree is "{TMP}"
    And the working directory is "/tmp"
    When the agent runs `git --git-dir={TMP}/.local/share/yadm/repo.git checkout some-branch`
    Then the guard denies

  # Fails closed: where the guard can't tell which directory git runs in,
  # it denies rather than guess.
  Scenario Outline: a directory the guard can't resolve is denied
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | cwd          | command                                     |
      | /nonexistent | git checkout some-branch                    |
      | {PROJ}       | cd "$SOMEWHERE" && git checkout some-branch |
      | {PROJ}       | cd - && git checkout some-branch            |
      | {PROJ}       | git -C "$SOMEWHERE" -C sub checkout x       |
      | {PROJ}       | cd "$X" && cd sub && git checkout some-branch |

  # A cd replaces the directory git is judged from. The scanner drops
  # subshell parentheses, so the last row is a known false allow; see
  # docs/agent_decisions.md.
  Scenario Outline: a cd away from $HOME is judged from where it lands
    Given the working directory is "{TMP}"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                     |
      | cd {PROJ} && git checkout some-branch                       |
      | cd {TMP}/.claude/worktrees/fake-task && git switch some-branch |
      | (cd {PROJ}); git checkout some-branch                       |

  # A file restore leaves the branch alone. `switch` has no such form.
  Scenario Outline: a file restore is allowed even in $HOME
    Given the working directory is "{TMP}"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                     |
      | yadm checkout -- .npmrc                     |
      | yadm checkout main -- .npmrc                |
      | yadm checkout -- .npmrc && ls               |

  Scenario Outline: git outside $HOME, and nothing pointing back at it, is allowed
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | cwd                           | command                                              |
      | {PROJ}                        | git checkout some-branch                             |
      | {PROJ}                        | git switch some-branch                               |
      | {PROJ}                        | git -C {PROJ} checkout some-branch                   |
      | /tmp                          | git --git-dir={PROJ}/.git checkout some-branch       |
      | /tmp                          | GIT_DIR={PROJ}/.git git checkout some-branch         |
      | {TMP}/.claude/worktrees/fake-task | git checkout some-branch                         |
      | /tmp                          | cd {TMP}/.claude/worktrees/fake-task && git checkout some-branch |
      | /tmp                          | cd {PROJ} && git checkout some-branch                |
      | {PROJ}                        | git -C {TMP}/.claude/worktrees/fake-task checkout -b probe |

  # -C already says where the command runs, so a session that happens to sit
  # in $HOME is not judged for a checkout in an unrelated repo.
  Scenario Outline: -C to an unrelated repo is allowed even when the session sits in $HOME
    Given the working directory is "{TMP}"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                 |
      | git -C {PROJ} checkout -b probe         |
      | git -C {PROJ} switch some-branch        |

  Scenario Outline: a command that is not a checkout is allowed
    Given the working directory is "{TMP}"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                  |
      | yadm status                              |
      | echo 'yadm checkout some-branch'         |
      | git status                               |
