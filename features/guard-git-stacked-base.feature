@python
Feature: guard-git-stacked-base
  Deleting a remote branch an open PR uses is denied. gh and timeout are
  stubs throughout, so no scenario reaches the network: the stub lists three
  open PRs, #1 stacked on claude/base-branch (the head of #2), and #3 headed
  by claude/lonely, the base of nothing.

  Why. GitHub retargets a stacked PR only when its base branch disappears
  because the base PR merged. A base branch deleted any other way (by hand,
  by a cleanup pass, by a rebase that recreates it under a new name) closes
  every PR based on it, silently; the diff then reads as conflicting and the
  recovery is reopen-and-retarget, one PR at a time. Deleting the head branch
  of an open PR closes that PR the same way. So the guard fires on
  remote-branch deletion only and asks GitHub whether an open PR names the
  branch as base or head. The safe path is never blocked: `gh pr merge
  --delete-branch` names no branch, and a local `git branch -d` takes nothing
  from a PR. Not a stack? Then there is nothing here to hit; small changes in
  flight belong on parallel branches off main.

  The verdicts are not symmetric. An open PR found is a deny: destructive and
  known, not guessed. GitHub unreachable (no gh, no auth, an API error), a
  repository other than the session's (`git -C`, `--git-dir`, `GIT_DIR=`),
  or a gh call that hangs or cannot be bounded by timeout is an ask: a deny
  there would refuse every remote deletion on a machine that can make them,
  and an unbounded gh would stall the hook until the harness kills it, and a
  killed hook is not a decision. A command that does not parse is a deny:
  inspection failing is not inspection coming back empty.

  What counts as a remote-branch deletion: `git push [<remote>] --delete|-d
  <ref>...`, `git push <remote> :<ref>`, and `gh api -X DELETE
  .../git/refs/heads/<ref>`, with `refs/heads/` stripped. Known gap,
  deliberate: a deletion spelled through a variable resolves to a word the
  guard cannot expand, so it routes to ask, not to a silent allow.

  Background:
    Given the stubs "gh" and "timeout" are first on PATH
    And the working directory is "{TMP}"

  Scenario Outline: deleting a branch an open PR is stacked on is denied
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                  | note                          |
      | git push -d origin claude/base-branch                    | -d                            |
      | git push origin :claude/base-branch                      | a colon refspec               |
      | git push origin :refs/heads/claude/base-branch           | a colon refspec, qualified    |
      | git push origin --delete refs/heads/claude/base-branch   | refs/heads/ prefix stripped   |
      | git push --delete origin claude/base-branch              | --delete before the remote    |
      | git push origin --delete claude/spare claude/base-branch | one of several refs is a base |
      | yadm push origin --delete claude/base-branch             | yadm is git                   |

  Scenario Outline: deleting the head branch of an open PR is denied
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                     | note                                    |
      | git push origin --delete claude/stacked-one | the head of #1                          |
      | git push origin --delete claude/lonely      | the head of #3, which is nothing's base |

  Scenario Outline: the REST spelling of a delete is denied too
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                            |
      | gh api --method DELETE repos/o/r/git/refs/heads/claude/base-branch |
      | gh api -XDELETE repos/o/r/git/refs/heads/claude/base-branch        |
      | gh api --method=DELETE repos/o/r/git/refs/heads/claude/base-branch |

  Scenario Outline: the bypasses the shared scanner exists to close stay closed
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                | note                       |
      | sh -c 'git push origin --delete claude/base-branch'    | nested in sh -c            |
      | git push origin --delete claude/base-branch # harmless | trailing shell comment     |
      | /usr/bin/git push origin --delete claude/base-branch   | absolute-path invocation   |
      | echo hi && git push origin --delete claude/base-branch | after a compound separator |
      | git   push   origin   --delete   claude/base-branch    | unusual whitespace         |

  Scenario Outline: a branch or a PR list that cannot be resolved is asked about
    Given GH_FAIL is <gh_fail>
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | gh_fail | command                                                 | verdict | note                                                  |
      | unset   | git push origin --delete "$b"                           | asks    | a variable branch cannot be looked up: ask, not allow |
      | unset   | git push origin --delete claude/old-*                   | asks    | a glob cannot be looked up                            |
      | "1"     | git push origin --delete claude/base-branch             | asks    | gh cannot answer                                      |
      | unset   | git push origin --delete claude/base-branch pr merge -d | denies  | pr, merge and -d after a real delete do not excuse it |

  Scenario: a live PR is looked up under timeout 20, and denies
    When the agent runs `git push origin --delete claude/base-branch`
    Then the guard denies
    And the stub "timeout" was called with "20 gh pr list"

  Scenario: a gh pr list that outlives its timeout asks
    Given TIMEOUT_HANG is "1"
    When the agent runs `git push origin --delete claude/base-branch`
    Then the guard asks

  Scenario: the --head lookup is bounded too
    # The --base lookup is the first gh call and finds nothing for this
    # branch; the --head lookup is the second, and it is the one that hangs.
    Given TIMEOUT_HANG is "2"
    When the agent runs `git push origin --delete claude/lonely`
    Then the guard asks
    And the stub "timeout" was called 2 times

  Scenario: the gh api spelling runs gh under the same bound
    Given TIMEOUT_HANG is "1"
    When the agent runs `gh api -X DELETE repos/o/r/git/refs/heads/claude/base-branch`
    Then the guard asks

  Scenario Outline: with no timeout or gtimeout on PATH it asks, and never runs gh unbounded
    Given PATH holds only "sh" and the stub "gh"
    When the agent runs `<command>`
    Then the guard asks
    And the stub "gh" was not called

    @also_guard-worktrees
    Examples:
      | command                                        | note                            |
      | git push origin --delete claude/already-merged | a branch no open PR names       |
      | git push origin --delete claude/base-branch    | a branch an open PR is based on |

  Scenario Outline: git pointed at another repository is asked about
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                                 | verdict | note                                                 |
      | git -C /elsewhere push origin --delete claude/base-branch               | asks    |                                                      |
      | git --git-dir=/elsewhere/.git push origin --delete claude/base-branch   | asks    | git --git-dir                                        |
      | GIT_DIR=/elsewhere/.git git push origin --delete claude/base-branch     | asks    | GIT_DIR in the environment                           |
      | git -C /elsewhere status && git push origin --delete claude/base-branch | denies  | git -C on another command does not excuse the delete |

  Scenario: the REST endpoint names the repository the PR list is read from
    When the agent runs `gh api -X DELETE repos/o/r/git/refs/heads/claude/base-branch`
    Then the guard denies
    And the stub "gh" was called with "-R o/r"

  Scenario: a {owner}/{repo} placeholder means the cwd's repository
    When the agent runs `gh api -X DELETE repos/{owner}/{repo}/git/refs/heads/claude/base-branch`
    Then the guard denies
    And the stub "gh" was not called with "-R"

  Scenario: an endpoint whose repository cannot be resolved asks
    When the agent runs `gh api -X DELETE "repos/$OWNER/r/git/refs/heads/claude/base-branch"`
    Then the guard asks

  Scenario: a tab in a PR title still makes a deny that parses
    Given GH_TAB is "1"
    When the agent runs `git push origin --delete claude/base-branch`
    Then the guard denies

  # A push option's separate value is no remote and no ref: read as either, it
  # costs a lookup of a branch that is not being deleted.
  Scenario Outline: a push option's separate value is not looked up
    When the agent runs `<command>`
    Then the guard <verdict>
    And the stub "gh" was not called with "<ghost>"

    Examples:
      | command                                                                | verdict   | ghost         | note                |
      | git push -o ci.skip origin --delete claude/already-merged              | is silent | --base origin | -o                  |
      | git push --push-option ci.skip origin --delete claude/already-merged   | is silent | --base origin | --push-option       |
      | git push --repo origin origin --delete claude/already-merged           | is silent | --base origin | --repo              |
      | git push --receive-pack /bin/x origin --delete claude/already-merged   | is silent | --base /bin/x | --receive-pack      |
      | git push --exec /bin/x origin --delete claude/already-merged           | is silent | --base /bin/x | --exec, its alias   |
      | git push --push-opt x origin --delete claude/already-merged            | is silent | --base x      | an unambiguous prefix |
      | git push origin --delete claude/already-merged -o claude/base-branch   | is silent | --base claude/base-branch | the value after the ref |
      | git push -o ci.skip origin --delete claude/base-branch                 | denies    | --base origin | a real base still denies |

    @also_guard-git-work-loss
    Examples:
      | command                                                                | verdict   | ghost         | note                |
      | git push -fo ci.skip origin --delete claude/already-merged           | is silent | --base origin | -o ending a cluster |

  Scenario Outline: the safe deletions and the non-deletions pass silently
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                               | note                                 |
      | git push origin --delete claude/already-merged        | no open PR names it                  |
      | git push --force-with-lease origin claude/stacked-one | force-push of a stacked branch       |
      | git branch -d claude/base-branch                      |                                      |
      | gh pr merge 2 --delete-branch                         | the safe deletion names no branch    |
      | gh pr merge 2 -d                                      |                                      |
      | gh pr merge 2 --delete-branch && echo done            |                                      |
      | git status                                            | unrelated                            |
      | gh api repos/o/r/git/refs/heads/claude/base-branch    | a GET                                |
      | echo 'git push origin --delete claude/base-branch'    | a deletion quoted into prose         |

    @also_guard-bypass-ruleset
    Examples:
      | command                                               | note                                 |
      | git push origin main                                  | not a deletion                       |
      | git push origin HEAD:main                             |                                      |

    @also_guard-git-work-loss
    Examples:
      | command                                               | note                                 |
      | git branch -D claude/base-branch                      | local delete takes nothing from a PR |
