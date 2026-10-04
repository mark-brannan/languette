@shell
Feature: wiring
  Each command in hooks/hooks.json, run the way Claude Code runs it (sh -c,
  CLAUDE_PLUGIN_ROOT set to this repo), judges a payload and fails closed.
  A plain `sh missing.sh` exits 127, which Claude Code reads as a
  non-blocking error, so a missing or crashing script has to come out as a
  deny. ask-first judges only in a project that lists the command.

  Background:
    Given a project directory
    And the file ".languette/ask-first.json" holds:
      """
      {"commands": [{"id": "walk", "match": [{"cmd": "npm", "args": ["run", "walk"]}],
                     "cost": "long", "approve_label": "Run walk"}]}
      """

  Scenario Outline: each hooks.json command judges a payload
    Given the hook is the hooks.json command for "<guard>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | guard                  | command                       | verdict |
      | no-git-footguns        | git add -A                    | denies  |
      | no-rm-tree             | rm -rf build                  | denies  |
      | no-delete-stacked-base | git push origin --delete "$b" | asks    |
      | ask-first              | npm run walk                  | denies  |

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
