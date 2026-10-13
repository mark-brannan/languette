@python @family
Feature: git-gating
  A placeholder name for the family that gates git work loss and the rest of
  git's own state; what it is finally called is not settled. A family is a
  configuration key that groups guards; this file holds the verdicts the
  family gives, run against every guard together.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every other
  scenario is allowed by design and fails CI when a guard stops allowing it.

  Rewrites of commits already pushed (rebase, amend, cherry-pick) are
  allowed here only as everyday work on a branch; whether one loses anything
  depends on the remote, so the rows that would gate one need a scenario
  with a repository behind them.

  Scenario Outline: everyday git on the agent's own branch is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                          | note                           |
      | git rebase origin/main                           |                                |
      | git rebase --onto main base-tag topic            |                                |
      | git commit --amend --no-edit                     |                                |
      | git commit --amend -m "notes: fix a typo"        |                                |
      | git cherry-pick 4f2a9c1                          |                                |
      | git cherry-pick --continue                       |                                |
      | git push --force-with-lease origin topic         | the one legitimate force       |
      | git push -u origin topic                         |                                |
      | git branch -d topic                              | -d refuses unmerged work       |
      | git stash drop stash@{2}                         | by ref                         |
      | git restore --staged notes.txt                   | unstaging is reversible        |
      | git restore notes.txt                            | one path                       |
      | git checkout main                                | a branch, not a discard        |
      | git checkout -b topic origin/main                |                                |
      | git rm --cached notes.txt                        |                                |
      | git show HEAD:notes.txt > notes.old              | a copy beside the file         |
      | git branch "$NEW_BRANCH" origin/main             | a branch named by a variable   |

  Scenario Outline: prose that names a git command is not the command
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                    | note                 |
      | git commit -m "docs: never git push --force to main"       | a commit message     |
      | git commit -m "drop the git clean -fdx step"               |                      |
      | echo "git checkout -- . throws away edits"                 | echo prints          |
      | grep -n "git add -A" notes.md                              | grep's pattern       |
      | printf '%s\n' "git push -f origin topic"                   |                      |
      | gh pr comment 12 --body "rebased; git push --force-with-lease next" |             |

  @planned
  Scenario Outline: local work beyond the reach of a one-path undo
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                 | verdict | note                                       |
      | git worktree remove --force ../other-tree               | denies  | drops the tree's uncommitted work          |
      | git worktree remove -f ../other-tree                    | denies  |                                            |
      | git switch --discard-changes main                       | denies  | the whole tree, as checkout . does         |
      | git checkout -f release                                 | denies  | the whole tree, on the way to a branch     |
      | git checkout --force main                               | denies  |                                            |
      | git read-tree --reset -u HEAD                           | denies  | the whole tree                             |
      | git reset --merge HEAD~1                                | denies  | drops staged work the merge did not touch  |
      | git update-ref -d refs/heads/topic                      | denies  | branch -D by another name                  |
      | git submodule deinit -f vendor/lib                      | denies  | the submodule's own uncommitted work       |
      | git submodule deinit --all --force                      | denies  |                                            |

  @planned
  Scenario Outline: the history that brings lost work back is destroyed or rewritten
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                 | verdict | note                                       |
      | git reflog expire --expire=now --all                    | denies  | the reflog is what brings lost work back   |
      | git reflog expire --expire-unreachable=now refs/heads/topic | denies |                                         |
      | git gc --prune=now                                      | denies  | unreachable commits go for good            |
      | git gc --aggressive --prune=now                         | denies  |                                            |
      | git filter-repo --path notes.txt --invert-paths         | denies  | rewrites every commit                      |
      | git filter-repo --replace-text expressions.txt          | denies  |                                            |
      | git filter-branch --tree-filter 'rm -f notes.txt' HEAD  | denies  | rewrites every commit                      |
      | git filter-branch --index-filter 'git rm --cached -r --ignore-unmatch out' -- --all | denies |          |
      | git lfs migrate import --everything --include='*.bin'   | denies  | rewrites every branch                      |
      | git lfs migrate export --include='*.psd' --everything   | denies  |                                            |

  @planned
  Scenario Outline: a push that replaces the remote wholesale
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                   | verdict | note                                       |
      | git push --mirror origin                  | denies  | deletes every remote ref missing here      |
      | git push --mirror git@example.com:o/r.git | denies  |                                            |

  @planned
  Scenario Outline: git's own subcommand programs, spelled with a hyphen, are git
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                         | verdict | note                       |
      | git-push --force origin topic   | denies  | git-push is git push       |
      | git-push origin +topic:topic    | denies  |                            |
      | git-add -A                      | denies  |                            |
      | git-reset --hard                | denies  |                            |
      | git-stash clear                 | denies  |                            |

  @planned
  Scenario Outline: git's internals are overwritten
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                         | verdict | note                                   |
      | echo 'exit 0' > .git/hooks/pre-commit           | denies  | the next commit runs this              |
      | cp settings.ini .git/config                     | denies  | the next push may go somewhere else    |
      | printf '[core]\n' >> .git/config                | denies  | an append still adds config            |
      | echo deadbeef > .git/refs/heads/main            | denies  | moves a branch with no reflog entry    |
      | echo 'ref: refs/heads/other' > .git/HEAD        | denies  |                                        |
      | truncate -s 0 .git/index                        | denies  | the staging area                       |
      | cat /dev/null > ../repo/.git/packed-refs        | denies  | another checkout's refs                |

  @planned
  Scenario Outline: an inline script does what the guard denies in the shell
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                              | verdict | note                    |
      | python3 -c 'import subprocess; subprocess.run(["git", "reset", "--hard"])' | denies | reset --hard by another door |
