@shell
Feature: wiring
  Each command in hooks/hooks.json, run the way Claude Code runs it (sh -c,
  CLAUDE_PLUGIN_ROOT set to this repo), judges a payload and fails closed.
  A plain `sh missing.sh` exits 127, which Claude Code reads as a
  non-blocking error, so a missing or crashing script has to come out as a
  deny. ask-first judges only in a project that lists the command.
  no-bypass-labels judges an MCP tool's labels field as well as Bash.

  Background:
    Given a project directory
    And the file ".languette/ask-first.json" holds:
      """
      {"commands": [{"id": "walk", "match": [{"cmd": "npm", "args": ["run", "walk"]}],
                     "cost": "long", "approve_label": "Run walk"}]}
      """
    And the private terms file holds:
      """
      Wanderlust
      """
    And the stub "prose-budget" is the engine
    And PROSE_BUDGET_FAIL is "1"

  Scenario Outline: each hooks.json command judges a payload
    Given the hook is the hooks.json command for "<guard>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | guard                  | command                       | verdict   |
      | no-git-footguns        | git add -A                    | denies    |
      | no-rm-tree             | rm -rf build                  | denies    |
      | no-delete-stacked-base | git push origin --delete "$b" | asks      |
      | ask-first              | npm run walk                  | denies    |
      | issue-door             | gh issue create -t t -b b     | denies    |
      | prose-budget-commit    | git commit -m x               | denies    |
      | public-issue-guard     | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | no-bypass-labels       | gh pr edit 4 --add-label churn-ok | denies    |

  Scenario: the hooks.json command for no-bypass-labels judges an MCP call
    Given the hook is the hooks.json command for "no-bypass-labels"
    When the agent calls MCP tool "mcp__github__update_issue" with input `{"owner":"o","repo":"r","issue_number":3,"labels":["churn-ok"]}`
    Then the guard denies

  # The prompt hook is the only thing that opens the door. Dropped or
  # mis-argumented in hooks.json, the PreToolUse hook would deny every create.
  Scenario: the hooks.json prompt hook opens the door the hooks.json issue-door hook spends
    Given the hook is the hooks.json command for "issue-door"
    When the human speaks, through the hooks.json prompt hook
    And the agent runs `gh issue create -t t -b b`
    Then the guard is silent

  Scenario Outline: a script missing from the plugin directory is a deny
    Given the hook is the hooks.json command for "<guard>"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | guard                  | command                       |
      | no-git-footguns        | git add -A                    |
      | no-rm-tree             | rm -rf build                  |
      | no-delete-stacked-base | git push origin --delete "$b" |
      | ask-first              | npm run walk                  |
      | issue-door             | gh issue create -t t -b b     |
      | public-issue-guard     | gh issue comment 3 -R o/r -b Wanderlust |
      | no-bypass-labels       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | git commit -m x               |

  # The no-rm-tree command runs languette/run.py under python3 and falls back to
  # the shell guard when `command -v python3` fails. The PATH below holds the
  # shell guard's tools and no python3, so a silent harmless command also
  # proves the fallback judged rather than crashed.
  Scenario Outline: with python3 absent from PATH, the hooks.json no-rm-tree command falls back to the shell guard
    Given the hook is the hooks.json command for "no-rm-tree"
    And PATH holds only "sh jq awk cat cut dirname head printf readlink realpath git"
    And the working directory is "/x"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command          | verdict   |
      | rm -rf /some/dir | denies    |
      | ls -la           | is silent |

  # The run.py guards have no shell fallback, so with python3 absent they
  # still deny, but say why instead of blaming the plugin directory.
  Scenario Outline: with python3 absent from PATH, a run.py guard denies and says python3 is required
    Given the hook is the hooks.json command for "<guard>"
    And PATH holds only "sh cat printf dirname"
    When the agent runs `<command>`
    Then the guard denies, naming "python3 is required for <guard>"
    And the guard denies, naming "<option>=false"

    Examples:
      | guard            | option           | command                           |
      | ask-first        | ASK_FIRST        | npm run walk                      |
      | no-bypass-labels | NO_BYPASS_LABELS | gh pr edit 4 --add-label churn-ok |

  Scenario Outline: a script that crashes is a deny
    Given the hook is the hooks.json command for "<guard>"
    And the plugin's script for "<guard>" crashes
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | guard                  | command                       |
      | no-git-footguns        | git add -A                    |
      | no-rm-tree             | rm -rf build                  |
      | no-delete-stacked-base | git push origin --delete "$b" |
      | ask-first              | npm run walk                  |
      | issue-door             | gh issue create -t t -b b     |
      | public-issue-guard     | gh issue comment 3 -R o/r -b Wanderlust |
      | no-bypass-labels       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | git commit -m x               |

  Scenario Outline: the option set to false skips the guard
    Given the hook is the hooks.json command for "<guard>"
    And <option> is "false"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | guard                  | option                                      | command                       |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | git add -A                    |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | rm -rf build                  |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | git push origin --delete "$b" |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | npm run walk                  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | gh issue create -t t -b b     |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | gh issue comment 3 -R o/r -b Wanderlust |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | git commit -m x               |

  # Only the exact word false skips: unset, empty or anything else runs the
  # guard, so a misconfiguration cannot open the gate.
  Scenario Outline: any other value of the option runs the guard
    Given the hook is the hooks.json command for "<guard>"
    And <option> is "<value>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | guard                  | option                                      | value | command                       | verdict |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        |       | git add -A                    | denies  |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | 0     | git add -A                    | denies  |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | False | git add -A                    | denies  |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | no    | git add -A                    | denies  |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | true  | git add -A                    | denies  |
      | no-git-footguns        | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS        | 1     | git add -A                    | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             |       | rm -rf build                  | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | 0     | rm -rf build                  | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | False | rm -rf build                  | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | no    | rm -rf build                  | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | true  | rm -rf build                  | denies  |
      | no-rm-tree             | CLAUDE_PLUGIN_OPTION_NO_RM_TREE             | 1     | rm -rf build                  | denies  |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE |       | git push origin --delete "$b" | asks    |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | 0     | git push origin --delete "$b" | asks    |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | False | git push origin --delete "$b" | asks    |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | no    | git push origin --delete "$b" | asks    |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | true  | git push origin --delete "$b" | asks    |
      | no-delete-stacked-base | CLAUDE_PLUGIN_OPTION_NO_DELETE_STACKED_BASE | 1     | git push origin --delete "$b" | asks    |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              |       | npm run walk                  | denies  |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | 0     | npm run walk                  | denies  |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | False | npm run walk                  | denies  |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | no    | npm run walk                  | denies  |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | true  | npm run walk                  | denies  |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | 1     | npm run walk                  | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             |       | gh issue create -t t -b b     | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | 0     | gh issue create -t t -b b     | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | False | gh issue create -t t -b b     | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | no    | gh issue create -t t -b b     | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | true  | gh issue create -t t -b b     | denies  |
      | issue-door             | CLAUDE_PLUGIN_OPTION_ISSUE_DOOR             | 1     | gh issue create -t t -b b     | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     |       | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | 0     | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | False | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | no    | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | true  | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | public-issue-guard     | CLAUDE_PLUGIN_OPTION_PUBLIC_ISSUE_GUARD     | 1     | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    |       | git commit -m x               | denies    |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | 0     | git commit -m x               | denies    |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | False | git commit -m x               | denies    |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | no    | git commit -m x               | denies    |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | true  | git commit -m x               | denies    |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | 1     | git commit -m x               | denies    |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       |       | gh pr edit 4 --add-label churn-ok | denies  |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | 0     | gh pr edit 4 --add-label churn-ok | denies  |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | False | gh pr edit 4 --add-label churn-ok | denies  |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | no    | gh pr edit 4 --add-label churn-ok | denies  |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | true  | gh pr edit 4 --add-label churn-ok | denies  |
      | no-bypass-labels       | CLAUDE_PLUGIN_OPTION_NO_BYPASS_LABELS       | 1     | gh pr edit 4 --add-label churn-ok | denies  |

  # no-checkout-home is opt-in, the reverse of the guards above: it runs only
  # when its option is exactly "true", so a misconfiguration leaves it off.
  Scenario: the opt-in guard judges when its option is true
    Given the hook is the hooks.json command for "no-checkout-home"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_NO_CHECKOUT_HOME is "true"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  Scenario: the opt-in guard stays silent when its option is unset
    Given the hook is the hooks.json command for "no-checkout-home"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_NO_CHECKOUT_HOME is unset
    When the agent runs `git checkout some-branch`
    Then the guard is silent

  Scenario Outline: the opt-in guard stays silent for any value but true
    Given the hook is the hooks.json command for "no-checkout-home"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_NO_CHECKOUT_HOME is "<value>"
    When the agent runs `git checkout some-branch`
    Then the guard is silent

    Examples:
      | value |
      | false |
      |       |
      | 0     |
      | True  |
      | 1     |
      | yes   |

  Scenario: with the opt-in guard on, a script missing from the plugin directory is a deny
    Given the hook is the hooks.json command for "no-checkout-home"
    And CLAUDE_PLUGIN_OPTION_NO_CHECKOUT_HOME is "true"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  Scenario: with the opt-in guard on, a script that crashes is a deny
    Given the hook is the hooks.json command for "no-checkout-home"
    And the plugin's script for "no-checkout-home" crashes
    And CLAUDE_PLUGIN_OPTION_NO_CHECKOUT_HOME is "true"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  Scenario: with the opt-in guard off, a missing script is silent
    Given the hook is the hooks.json command for "no-checkout-home"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `git checkout some-branch`
    Then the guard is silent

  Scenario: the foreign-worktree guard judges when its option is true
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"
    And CLAUDE_PLUGIN_OPTION_NO_FOREIGN_WORKTREE is "true"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard denies

  Scenario Outline: the foreign-worktree guard stays silent unless its option is exactly true
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"
    And CLAUDE_PLUGIN_OPTION_NO_FOREIGN_WORKTREE is "<value>"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard is silent

    Examples:
      | value |
      | false |
      |       |
      | 0     |
      | True  |
      | 1     |
      | yes   |

  Scenario: the foreign-worktree guard stays silent when its option is unset
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"
    And CLAUDE_PLUGIN_OPTION_NO_FOREIGN_WORKTREE is unset
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard is silent

  Scenario: with the foreign-worktree guard on, a script missing from the plugin directory is a deny
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And CLAUDE_PLUGIN_OPTION_NO_FOREIGN_WORKTREE is "true"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `git status`
    Then the guard denies

  Scenario: with the foreign-worktree guard on, a script that crashes is a deny
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And the plugin's script for "no-foreign-worktree" crashes
    And CLAUDE_PLUGIN_OPTION_NO_FOREIGN_WORKTREE is "true"
    When the agent runs `git status`
    Then the guard denies

  Scenario: with the foreign-worktree guard off, a missing script is silent
    Given the hook is the hooks.json command for "no-foreign-worktree"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `git status`
    Then the guard is silent
