@shell
Feature: issue-door
  One GitHub issue create, transfer or delete per human turn. The human's
  own turn is the door: it opens on UserPromptSubmit and the first identifier
  write of that turn spends it. The door is named apart from the claude
  plugin's own copy of this hook, so the two never spend each other's.

  Scenario Outline: never an identifier write, door shut or not
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                |
      | gh issue view 12 -R o/r                                |
      | gh issue list --state open                             |
      | gh issue comment 12 --body "progress"                  |
      | gh issue edit 12 --add-label x                          |
      | gh pr create --title t --body "fixes the issue create path" |
      | gh api repos/o/r/issues                                |
      | gh api -X GET repos/o/r/issues -f state=open           |
      | echo "run gh issue create later" > note.md             |
      | grep -n "gh issue create" CLAUDE.md                    |
      | ugh issue create                                       |

  Scenario Outline: an identifier write with the door shut is denied, however it is reached
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                            |
      | gh issue create --title t --body b                 |
      | gh issue new -t t -b b                              |
      | gh issue transfer 4 o/other                         |
      | gh issue delete 4 --yes                             |
      | cd /w && gh issue create -t t -b b                  |
      | sh -c "gh issue create -t t -b b"                   |
      | eval "gh issue transfer 4 o/x"                      |
      | gh api repos/o/r/issues -f title=t                  |
      | gh api -X POST repos/o/r/issues --input body.json   |

  Scenario: a graphql createIssue mutation is denied, door shut
    When the agent runs `gh api graphql -f query='mutation { createIssue(input:{}) { issue { id } } }'`
    Then the guard denies

  Scenario Outline: an MCP identifier write is judged the same as the gh CLI
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                      | input                              | verdict   |
      | mcp__github__issue_write                  | {"method":"update","issue_number":3} | is silent |
      | mcp__github__create_issue                 | {"owner":"o","repo":"r","title":"t"} | denies    |
      | mcp__plugin_github_github__issue_write    | {"method":"create","title":"t"}      | denies    |

  Scenario: the human's turn opens the door; the first write spends it
    When the human speaks, opening the door
    And the agent runs `gh issue create -t t -b b`
    Then the guard is silent

  Scenario: a second identifier write in the same turn is denied
    When the human speaks, opening the door
    And the agent runs `gh issue create -t t -b b`
    And the agent runs `gh issue transfer 4 o/other`
    Then the guard denies

  Scenario Outline: never a batch, door open or not
    When the human speaks, opening the door
    And the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                            |
      | gh issue create -t a -b b; gh issue create -t c -b d               |
      | gh issue create -t a -b b && gh issue transfer 4 o/x               |
      | for t in a b c; do gh issue create -t "$t" -b x; done              |
      | cat list \| xargs -I{} gh issue create -t {} -b x                  |

  Scenario: a denied batch does not spend the door
    When the human speaks, opening the door
    And the agent runs `for t in a b c; do gh issue create -t "$t" -b x; done`
    And the agent runs `gh issue create -t one -b b`
    Then the guard is silent

  Scenario: another session's turn does not open this one's door
    Given the session is "s2"
    When the human speaks, opening the door
    And the session is "s1"
    And the agent runs `gh issue create -t t -b b`
    Then the guard denies

  @shell_only
  Scenario: with no jq or awk on PATH, a call that mentions an issue is denied
    Given PATH holds only "sh cat printf dirname head cut readlink"
    When the agent runs `gh issue create -t t -b b`
    Then the guard denies
