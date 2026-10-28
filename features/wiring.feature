@hook
Feature: wiring
  Each command in hooks/hooks.json, run the way Claude Code runs it (sh -c,
  CLAUDE_PLUGIN_ROOT set to this repo), judges a payload and fails closed.
  A plain `sh missing.sh` exits 127, which Claude Code reads as a
  non-blocking error, so a missing or crashing script has to come out as a
  deny. ask-first judges only in a project that lists the command.
  guard-bypass-labels judges an MCP tool's labels field as well as Bash.

  Background:
    Given a project directory
    And the file ".languette/ask-first.json" holds:
      """
      {"commands": [{"id": "walk", "match": [{"cmd": "npm", "args": ["run", "walk"]}],
                     "cost": "long", "approve_label": "Run walk"}]}
      """
    And the blocked terms file holds:
      """
      Wanderlust
      """
    And the file ".languette/secrets.json" holds:
      """
      {"patterns": [{"id": "acme-key", "description": "Acme API key", "regex": "acme_[a-z0-9]{24}"}]}
      """
    And the stub "prose-budget" is the engine
    And PROSE_BUDGET_FAIL is "1"
    And CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "postgresql"

  Scenario Outline: each hooks.json command judges a payload
    Given the hook is the hooks.json command for "<guard>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | guard                  | command                       | verdict   |
      | guard-git-work-loss        | git add -A                    | denies    |
      | guard-recursive-delete             | rm -rf build                  | denies    |
      | guard-permissions | chmod -R 755 build | denies |
      | guard-pipe-to-shell | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | dd if=x of=/dev/sda | denies |
      | guard-host-availability | shutdown -h now | denies |
      | guard-protected-services | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | crontab -r | denies |
      | guard-git-stacked-base | git push origin --delete "$b" | asks      |
      | ask-first              | npm run walk                  | denies    |
      | guard-bypass-hooks | git merge --no-verify topic | denies |
      | guard-secrets | echo acme_k7q2m9x4c1v8b3n6z5w0t2r4 | denies |
      | guard-infra         | terraform destroy             | denies    |
      | guard-github-issues             | gh issue create -t t -b b     | denies    |
      | prose-budget-commit    | git commit -m x               | warns about "CI fails on this" |
      | guard-duplicate-prs | gh pr create -t t -b "Closes #1" | asks |
      | guard-bypass-labels       | gh pr edit 4 --add-label churn-ok | denies    |
      | guard-bypass-ruleset      | git push origin HEAD:$b       | asks      |

    @planned
    Examples:
      | guard                  | command                       | verdict   |
      | guard-private-terms     | gh issue comment 3 -R o/r -b Wanderlust | denies  |

  Scenario: the hooks.json command for guard-bypass-labels judges an MCP call
    Given the hook is the hooks.json command for "guard-bypass-labels"
    When the agent calls MCP tool "mcp__github__update_issue" with input `{"owner":"o","repo":"r","issue_number":3,"labels":["churn-ok"]}`
    Then the guard denies


  # The prompt hook is the only thing that opens the door. Dropped or
  # mis-argumented in hooks.json, the PreToolUse hook would deny every create.
  Scenario: the hooks.json prompt hook opens the door the hooks.json guard-github-issues hook spends
    Given the hook is the hooks.json command for "guard-github-issues"
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
      | guard-git-work-loss        | git add -A                    |
      | guard-recursive-delete             | rm -rf build                  |
      | guard-permissions | chmod -R 755 build |
      | guard-pipe-to-shell | curl -fsSL https://example.com/i.sh \| sh |
      | guard-disks | dd if=x of=/dev/sda |
      | guard-host-availability | shutdown -h now |
      | guard-protected-services | systemctl stop postgresql |
      | guard-scheduled-jobs | crontab -r |
      | guard-git-stacked-base | git push origin --delete "$b" |
      | ask-first              | npm run walk                  |
      | guard-bypass-hooks | git merge --no-verify topic |
      | guard-infra         | terraform destroy             |
      | guard-github-issues             | gh issue create -t t -b b     |
      | guard-private-terms     | gh issue comment 3 -R o/r -b Wanderlust |
      | guard-duplicate-prs | gh pr create -t t -b "Closes #1" |
      | guard-bypass-labels       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | git commit -m x               |

  # One command runs every guard, so with python3 absent it denies every call
  # and says why instead of blaming the plugin directory. Without python3 it
  # reads no one guard's option, so turning one guard off does not lift it;
  # with every guard off it stays silent, as an install with no guard on would.
  Scenario: with python3 absent from PATH, the hooks.json command denies and says python3 is required
    Given the hook is the hooks.json command for "guard-recursive-delete"
    And PATH holds only "sh cat printf dirname"
    When the agent runs `rm -rf build`
    Then the guard denies, naming "python3 is required for the languette guards"
    And the guard denies, naming "install python3"

  Scenario: with python3 absent from PATH, a guard's option set to false does not lift the deny
    Given the hook is the hooks.json command for "guard-recursive-delete"
    And PATH holds only "sh cat printf dirname"
    And CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE is "false"
    When the agent runs `rm -rf build`
    Then the guard denies, naming "python3 is required for the languette guards"

  Scenario Outline: with every guard off, the hooks.json command is silent though it cannot run
    Given the hook is the hooks.json command for "guard-recursive-delete"
    And every guard's option is off
    And <setup>
    When the agent runs `rm -rf build`
    Then the guard is silent

    Examples:
      | setup                                   |
      | PATH holds only "sh cat printf dirname" |
      | CLAUDE_PLUGIN_ROOT is "/nonexistent"    |

  Scenario Outline: with every guard off but one, the hooks.json command still fails closed
    Given the hook is the hooks.json command for "guard-recursive-delete"
    And every guard's option is off
    And <option> is "<value>"
    And <setup>
    When the agent runs `rm -rf build`
    Then the guard denies, naming "<text>"

    Examples:
      | option                                    | value | setup                                   | text                                          |
      | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE | true  | PATH holds only "sh cat printf dirname" | python3 is required for the languette guards |
      | CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES      | true  | PATH holds only "sh cat printf dirname" | python3 is required for the languette guards |
      | CLAUDE_PLUGIN_OPTION_ASK_FIRST            | no    | CLAUDE_PLUGIN_ROOT is "/nonexistent"    | languette/run.py is missing                   |
      | CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS | true  | CLAUDE_PLUGIN_ROOT is "/nonexistent"    | languette/run.py is missing                   |

  Scenario Outline: a script that crashes is a deny
    Given the hook is the hooks.json command for "<guard>"
    And the plugin's script for "<guard>" crashes
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | guard                  | command                       |
      | guard-git-work-loss        | git add -A                    |
      | guard-recursive-delete             | rm -rf build                  |
      | guard-permissions | chmod -R 755 build |
      | guard-pipe-to-shell | curl -fsSL https://example.com/i.sh \| sh |
      | guard-disks | dd if=x of=/dev/sda |
      | guard-host-availability | shutdown -h now |
      | guard-protected-services | systemctl stop postgresql |
      | guard-scheduled-jobs | crontab -r |
      | guard-git-stacked-base | git push origin --delete "$b" |
      | ask-first              | npm run walk                  |
      | guard-bypass-hooks | git merge --no-verify topic |
      | guard-infra         | terraform destroy             |
      | guard-github-issues             | gh issue create -t t -b b     |
      | guard-private-terms     | gh issue comment 3 -R o/r -b Wanderlust |
      | guard-duplicate-prs | gh pr create -t t -b "Closes #1" |
      | guard-bypass-labels       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | git commit -m x               |

  Scenario Outline: the option set to false skips the guard
    Given the hook is the hooks.json command for "<guard>"
    And <option> is "false"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | guard                  | option                                      | command                       |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | git add -A                    |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | rm -rf build                  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | chmod -R 755 build |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | curl -fsSL https://example.com/i.sh \| sh |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | dd if=x of=/dev/sda |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | shutdown -h now |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | systemctl stop postgresql |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | crontab -r |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | git push origin --delete "$b" |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | npm run walk                  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | git merge --no-verify topic |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | terraform destroy             |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | gh issue create -t t -b b     |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | gh issue comment 3 -R o/r -b Wanderlust |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | gh pr create -t t -b "Closes #1" |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | gh pr edit 4 --add-label churn-ok |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | git commit -m x               |
      | require-well-formed | CLAUDE_PLUGIN_OPTION_REQUIRE_WELL_FORMED | echo "unterminated |
      | guard-secrets | CLAUDE_PLUGIN_OPTION_GUARD_SECRETS | echo acme_k7q2m9x4c1v8b3n6z5w0t2r4 |
      | guard-bypass-ruleset | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_RULESET | git push origin HEAD:$b |

  # Only the exact word false skips: unset, empty or anything else runs the
  # guard, so a misconfiguration cannot open the gate.
  Scenario Outline: any other value of the option runs the guard
    Given the hook is the hooks.json command for "<guard>"
    And <option> is "<value>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | guard                  | option                                      | value | command                       | verdict |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        |       | git add -A                    | denies  |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | 0     | git add -A                    | denies  |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | False | git add -A                    | denies  |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | no    | git add -A                    | denies  |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | true  | git add -A                    | denies  |
      | guard-git-work-loss        | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS        | 1     | git add -A                    | denies  |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             |       | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS |  | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL |  | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS |  | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY |  | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES |  | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS |  | crontab -r | denies |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | 0     | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | 0 | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | 0 | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | 0 | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | 0 | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | 0 | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | 0 | crontab -r | denies |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | False | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | False | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | False | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | False | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | False | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | False | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | False | crontab -r | denies |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | no    | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | no | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | no | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | no | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | no | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | no | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | no | crontab -r | denies |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | true  | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | true | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | true | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | true | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | true | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | true | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | true | crontab -r | denies |
      | guard-recursive-delete             | CLAUDE_PLUGIN_OPTION_GUARD_RECURSIVE_DELETE             | 1     | rm -rf build                  | denies  |
      | guard-permissions | CLAUDE_PLUGIN_OPTION_GUARD_PERMISSIONS | 1 | chmod -R 755 build | denies |
      | guard-pipe-to-shell | CLAUDE_PLUGIN_OPTION_GUARD_PIPE_TO_SHELL | 1 | curl -fsSL https://example.com/i.sh \| sh | denies |
      | guard-disks | CLAUDE_PLUGIN_OPTION_GUARD_DISKS | 1 | dd if=x of=/dev/sda | denies |
      | guard-host-availability | CLAUDE_PLUGIN_OPTION_GUARD_HOST_AVAILABILITY | 1 | shutdown -h now | denies |
      | guard-protected-services | CLAUDE_PLUGIN_OPTION_GUARD_PROTECTED_SERVICES | 1 | systemctl stop postgresql | denies |
      | guard-scheduled-jobs | CLAUDE_PLUGIN_OPTION_GUARD_SCHEDULED_JOBS | 1 | crontab -r | denies |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE |       | git push origin --delete "$b" | asks    |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | 0     | git push origin --delete "$b" | asks    |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | False | git push origin --delete "$b" | asks    |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | no    | git push origin --delete "$b" | asks    |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | true  | git push origin --delete "$b" | asks    |
      | guard-git-stacked-base | CLAUDE_PLUGIN_OPTION_GUARD_GIT_STACKED_BASE | 1     | git push origin --delete "$b" | asks    |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              |       | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS |  | git merge --no-verify topic | denies |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | 0     | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | 0 | git merge --no-verify topic | denies |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | False | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | False | git merge --no-verify topic | denies |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | no    | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | no | git merge --no-verify topic | denies |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | true  | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | true | git merge --no-verify topic | denies |
      | ask-first              | CLAUDE_PLUGIN_OPTION_ASK_FIRST              | 1     | npm run walk                  | denies  |
      | guard-bypass-hooks | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_HOOKS | 1 | git merge --no-verify topic | denies |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         |       | terraform destroy             | denies  |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | 0     | terraform destroy             | denies  |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | False | terraform destroy             | denies  |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | no    | terraform destroy             | denies  |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | true  | terraform destroy             | denies  |
      | guard-infra         | CLAUDE_PLUGIN_OPTION_GUARD_INFRA         | 1     | terraform destroy             | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             |       | gh issue create -t t -b b     | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | 0     | gh issue create -t t -b b     | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | False | gh issue create -t t -b b     | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | no    | gh issue create -t t -b b     | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | true  | gh issue create -t t -b b     | denies  |
      | guard-github-issues             | CLAUDE_PLUGIN_OPTION_GUARD_GITHUB_ISSUES             | 1     | gh issue create -t t -b b     | denies  |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS |  | gh pr create -t t -b "Closes #1" | asks |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | 0 | gh pr create -t t -b "Closes #1" | asks |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | False | gh pr create -t t -b "Closes #1" | asks |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | no | gh pr create -t t -b "Closes #1" | asks |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | true | gh pr create -t t -b "Closes #1" | asks |
      | guard-duplicate-prs | CLAUDE_PLUGIN_OPTION_GUARD_DUPLICATE_PRS | 1 | gh pr create -t t -b "Closes #1" | asks |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    |       | git commit -m x               | warns about "CI fails on this" |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | 0     | git commit -m x               | warns about "CI fails on this" |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | False | git commit -m x               | warns about "CI fails on this" |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | no    | git commit -m x               | warns about "CI fails on this" |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | true  | git commit -m x               | warns about "CI fails on this" |
      | prose-budget-commit    | CLAUDE_PLUGIN_OPTION_PROSE_BUDGET_COMMIT    | 1     | git commit -m x               | warns about "CI fails on this" |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       |       | gh pr edit 4 --add-label churn-ok | denies  |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | 0     | gh pr edit 4 --add-label churn-ok | denies  |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | False | gh pr edit 4 --add-label churn-ok | denies  |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | no    | gh pr edit 4 --add-label churn-ok | denies  |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | true  | gh pr edit 4 --add-label churn-ok | denies  |
      | guard-bypass-labels       | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_LABELS       | 1     | gh pr edit 4 --add-label churn-ok | denies  |
      | require-well-formed | CLAUDE_PLUGIN_OPTION_REQUIRE_WELL_FORMED | true | echo "unterminated | denies |
      | guard-secrets | CLAUDE_PLUGIN_OPTION_GUARD_SECRETS | true | echo acme_k7q2m9x4c1v8b3n6z5w0t2r4 | denies |
      | guard-bypass-ruleset | CLAUDE_PLUGIN_OPTION_GUARD_BYPASS_RULESET | true | git push origin HEAD:$b | asks |

    @planned
    Examples:
      | guard                  | option                                      | value | command                       | verdict |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     |       | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | 0     | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | False | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | no    | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | true  | gh issue comment 3 -R o/r -b Wanderlust | denies  |
      | guard-private-terms     | CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS     | 1     | gh issue comment 3 -R o/r -b Wanderlust | denies  |

  # guard-worktrees is opt-in, the reverse of the guards above: it runs only
  # when its option is exactly "true", so a misconfiguration leaves it off.
  Scenario: the opt-in guard judges when its option is true
    Given the hook is the hooks.json command for "guard-worktrees"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  Scenario: the opt-in guard stays silent when its option is unset
    Given the hook is the hooks.json command for "guard-worktrees"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is unset
    When the agent runs `git checkout some-branch`
    Then the guard is silent

  Scenario Outline: the opt-in guard stays silent for any value but true
    Given the hook is the hooks.json command for "guard-worktrees"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "<value>"
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
    Given the hook is the hooks.json command for "guard-worktrees"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  Scenario: with the opt-in guard on, a script that crashes is a deny
    Given the hook is the hooks.json command for "guard-worktrees"
    And the plugin's script for "guard-worktrees" crashes
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    When the agent runs `git checkout some-branch`
    Then the guard denies

  # guard-worktrees runs two parts; each has its own off switch under the
  # guard's.
  Scenario: with the opt-in guard on, a reach into another worktree is a deny
    Given the hook is the hooks.json command for "guard-worktrees"
    And a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard denies

  Scenario: the foreign part set to false lets a reach into another worktree through
    Given the hook is the hooks.json command for "guard-worktrees"
    And a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_FOREIGN is "false"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard is silent

  Scenario: the checkout-home part set to false lets a branch switch in HOME through
    Given the hook is the hooks.json command for "guard-worktrees"
    And HOME is "{TMP}"
    And a git repository at "{TMP}"
    And the working directory is "{TMP}"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES is "true"
    And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_CHECKOUT_HOME is "false"
    When the agent runs `git checkout some-branch`
    Then the guard is silent

  # guard-signed-comments is opt-in too: its signature is a convention a
  # workflow sets, so it runs only when its option is exactly "true".
  Scenario: the opt-in signed-comments guard judges when its option is true
    Given the hook is the hooks.json command for "guard-signed-comments"
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is "true"
    When the agent runs `gh pr comment 3 -R o/r -b Done`
    Then the guard denies

  Scenario: with the opt-in signed-comments guard on, the hooks.json command judges an MCP call
    Given the hook is the hooks.json command for "guard-signed-comments"
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is "true"
    When the agent calls MCP tool "mcp__plugin_github_github__add_reply_to_pull_request_comment" with input `{"owner":"o","repo":"r","pullNumber":4,"commentId":9,"body":"Replacement is the intent"}`
    Then the guard denies

  Scenario: the opt-in signed-comments guard stays silent when its option is unset
    Given the hook is the hooks.json command for "guard-signed-comments"
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is unset
    When the agent runs `gh pr comment 3 -R o/r -b Done`
    Then the guard is silent

  Scenario Outline: the opt-in signed-comments guard stays silent for any value but true
    Given the hook is the hooks.json command for "guard-signed-comments"
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is "<value>"
    When the agent runs `gh pr comment 3 -R o/r -b Done`
    Then the guard is silent

    Examples:
      | value |
      | false |
      |       |
      | 0     |
      | True  |
      | 1     |
      | yes   |

  # guard-review-threads is opt-in too: what a dismissal must point at is a
  # convention a workflow sets, so it runs only when its option is exactly "true".
  Scenario: the opt-in review-threads guard judges when its option is true
    Given the hook is the hooks.json command for "guard-review-threads"
    And CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS is "true"
    When the agent runs `gh api graphql -f query=resolveReviewThread -f id="$t"`
    Then the guard denies

  Scenario: the opt-in review-threads guard stays silent when its option is unset
    Given the hook is the hooks.json command for "guard-review-threads"
    And CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS is unset
    When the agent runs `gh api graphql -f query=resolveReviewThread -f id="$t"`
    Then the guard is silent

  Scenario Outline: the opt-in review-threads guard stays silent for any value but true
    Given the hook is the hooks.json command for "guard-review-threads"
    And CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS is "<value>"
    When the agent runs `gh api graphql -f query=resolveReviewThread -f id="$t"`
    Then the guard is silent

    Examples:
      | value |
      | false |
      |       |
      | 0     |
      | True  |
      | 1     |
      | yes   |

  Scenario: with the opt-in signed-comments guard on, a script missing from the plugin directory is a deny
    Given the hook is the hooks.json command for "guard-signed-comments"
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is "true"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `gh pr comment 3 -R o/r -b Done`
    Then the guard denies

  Scenario: with the opt-in signed-comments guard on, a script that crashes is a deny
    Given the hook is the hooks.json command for "guard-signed-comments"
    And the plugin's script for "guard-signed-comments" crashes
    And CLAUDE_PLUGIN_OPTION_GUARD_SIGNED_COMMENTS is "true"
    When the agent runs `gh pr comment 3 -R o/r -b Done`
    Then the guard denies

  Scenario: with the opt-in review-threads guard on, a script missing from the plugin directory is a deny
    Given the hook is the hooks.json command for "guard-review-threads"
    And CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS is "true"
    And CLAUDE_PLUGIN_ROOT is "/nonexistent"
    When the agent runs `gh api graphql -f query=resolveReviewThread -f id="$t"`
    Then the guard denies

  Scenario: with the opt-in review-threads guard on, a script that crashes is a deny
    Given the hook is the hooks.json command for "guard-review-threads"
    And the plugin's script for "guard-review-threads" crashes
    And CLAUDE_PLUGIN_OPTION_GUARD_REVIEW_THREADS is "true"
    When the agent runs `gh api graphql -f query=resolveReviewThread -f id="$t"`
    Then the guard denies

  # guard-cross-session-send judges SendMessage, not Bash, so it has its own rows.
  Scenario Outline: the hooks.json command for guard-cross-session-send judges a send and fails closed
    Given the hook is the hooks.json command for "guard-cross-session-send"
    And the permission mode is "default"
    And <setup>
    When the agent sends "api-worker" the message `hello`
    Then the guard <verdict>

    Examples:
      | verdict   | setup                                                      |
      | asks      | CLAUDE_PLUGIN_OPTION_GUARD_CROSS_SESSION_SEND is "true"    |
      | is silent | CLAUDE_PLUGIN_OPTION_GUARD_CROSS_SESSION_SEND is "false"   |
      | denies    | CLAUDE_PLUGIN_ROOT is "/nonexistent"                       |
      | denies    | the plugin's script for "guard-cross-session-send" crashes |

  # Its state hooks never object; one that fails leaves an open door in place
  # of the session's state, since no state reads as a closed one.
  Scenario: the hooks.json PostToolUse command for guard-cross-session-send opens the door
    Given the hook is the hooks.json PostToolUse command for "guard-cross-session-send"
    And the cross-session state file holds `{"subagents": [], "read": null}`
    When Claude Code fires PostToolUse for tool "WebFetch"
    Then the guard is silent
    And the cross-session state file names "WebFetch"

  Scenario Outline: a guard-cross-session-send state hook that fails leaves the door open
    Given the hook is the hooks.json <event> command for "guard-cross-session-send"
    And the cross-session state file holds `{"subagents": [], "read": null}`
    And <setup>
    When Claude Code fires <event> for tool "WebFetch"
    Then the guard is silent
    And the cross-session state file names "an unknown tool (a state hook failed)"

    Examples:
      | event         | setup                                                            |
      | PostToolUse   | the plugin's script for "guard-cross-session-send" crashes       |
      | PostToolUse   | CLAUDE_PLUGIN_ROOT is "/nonexistent"                             |
      | PostToolUse   | the plugin's script for "guard-cross-session-send" prints a deny |
      | SessionStart  | the plugin's script for "guard-cross-session-send" crashes       |
      | SubagentStart | PATH holds only "sh cat printf dirname sed head rm"              |

  # The Python failure path and the sh fallback agree: with the option off, no file is written.
  Scenario: a guard-cross-session-send state hook that fails inside run.py leaves the door open
    Given the hook is the hooks.json PostToolUse command for "guard-cross-session-send"
    And the plugin's script for "guard-cross-session-send" fails after reading its payload
    When Claude Code fires PostToolUse for tool "WebFetch"
    Then the guard is silent
    And the cross-session state file names "an unknown tool (a state hook failed)"

  Scenario: a guard-cross-session-send state hook that fails inside run.py writes no file when the option is false
    Given the hook is the hooks.json PostToolUse command for "guard-cross-session-send"
    And the plugin's script for "guard-cross-session-send" fails after reading its payload
    And CLAUDE_PLUGIN_OPTION_GUARD_CROSS_SESSION_SEND is "false"
    When Claude Code fires PostToolUse for tool "WebFetch"
    Then the guard is silent
    And the cross-session state file is gone
