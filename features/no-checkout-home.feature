@shell
Feature: no-checkout-home
  Opt-in: the plugin option no_checkout_home turns this guard on (see
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
