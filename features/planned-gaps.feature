@python @planned
Feature: planned-gaps
  Commands that lose work, history or something only GitHub holds, which no
  guard stops yet. Each row is the verdict languette means to give; the rows
  run against every guard together and are expected to fail until a guard
  covers them, so they never fail CI. A row that starts passing is reported
  as XPASS: move it into its guard's feature.

  The verdicts are proposals, not rulings (languette#134). Rewrites of
  commits already pushed (rebase, amend, cherry-pick) are not here: whether
  one loses anything depends on the remote, so those rows need a scenario
  with a repository behind them.

  Scenario Outline: local work beyond the reach of a one-path undo
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                        | verdict | note                                       |
      | git worktree remove --force ../other-tree      | denies  | drops the tree's uncommitted work          |
      | git worktree remove -f ../other-tree           | denies  |                                            |
      | git switch --discard-changes main              | denies  | the whole tree, as checkout . does         |
      | git read-tree --reset -u HEAD                  | denies  | the whole tree                             |
      | git update-ref -d refs/heads/topic             | denies  | branch -D by another name                  |
      | git reflog expire --expire=now --all           | denies  | the reflog is what brings lost work back   |
      | git gc --prune=now                             | denies  | unreachable commits go for good            |
      | git filter-repo --path notes.txt --invert-paths | denies | rewrites every commit                      |
      | git filter-branch --tree-filter 'rm -f notes.txt' HEAD | denies | rewrites every commit              |

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

  Scenario Outline: something only GitHub holds is deleted
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                   | verdict | note                         |
      | gh repo delete someone/project --yes                      | asks    |                              |
      | gh repo archive someone/project --yes                     | asks    |                              |
      | gh release delete v1.2.0 --yes                            | asks    |                              |
      | gh release delete-asset v1.2.0 app.tar.gz --yes           | asks    |                              |
      | gh secret delete DEPLOY_TOKEN                             | asks    | the workflows that read it break |
      | gh variable delete REGION                                 | asks    |                              |
      | gh gist delete 0123abcd --yes                             | asks    |                              |
      | gh ssh-key delete 12 --yes                                | asks    |                              |
      | gh repo deploy-key delete 34                              | asks    |                              |
      | gh api -X DELETE repos/someone/project/hooks/56           | asks    | a webhook                    |
      | gh api --method DELETE repos/someone/project/keys/78      | asks    | a deploy key                 |
      | gh api -X DELETE repos/someone/project/actions/secrets/X  | asks    |                              |
      | gh api -X DELETE repos/someone/project/releases/90        | asks    |                              |
      | gh api -X DELETE repos/someone/project                    | asks    | the repository itself        |

  Scenario Outline: a private repository is made public
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                         | verdict | note |
      | gh repo edit someone/project --visibility public | asks   |      |

  Scenario Outline: git's internals and the user's credentials are overwritten
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                   | verdict | note                                   |
      | echo 'exit 0' > .git/hooks/pre-commit     | denies  | the next commit runs this              |
      | cp settings.ini .git/config               | denies  | the next push may go somewhere else    |
      | echo token > ~/.git-credentials           | denies  |                                        |
      | cp key.pub ~/.ssh/authorized_keys         | denies  | replaces who may log in                |
      | mv notes.txt ~/.ssh/config                | denies  |                                        |
