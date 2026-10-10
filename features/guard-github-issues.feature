@python
Feature: guard-github-issues
  One GitHub issue create, transfer or delete per human turn. The human's
  own turn is the door: it opens on UserPromptSubmit and the first identifier
  write of that turn to run spends it. The door is named apart from the claude
  plugin's own copy of this hook, so the two never spend each other's.

  Why. An issue number is an identifier things link to where no agent can
  see, so minting or moving one is a one-way door (Solace, 2026-09-30): one
  create, transfer or delete per human turn, never two in one call, never one
  in a loop.

  Claimed before the call, spent after it. PreToolUse claims the door by
  renaming it to `<door>.held`, which only one call can win, and writes its
  tool_use_id there; PostToolUse and PostToolUseFailure delete the claim once
  the call has run. A claim whose call already has a result in the
  transcript, but was never spent, belongs to a call another guard denied: it
  never ran, so the next write takes the claim over. Each guard is its own
  hook process and cannot see the others' verdicts; spending at PreToolUse
  shut the door on a create another guard denied, with nothing posted. A
  claim whose call has no result yet is still in flight, and a second write
  is denied. The door is replaced, never followed: a symlink planted at the
  door path must not be written through. After the call a deny has nothing
  left to refuse, so an unreadable call fails closed by spending the door.

  Counts as an identifier write: `gh issue create|new|transfer|delete`; a
  `gh api` POST to repos/o/r/issues; a graphql createIssue, transferIssue or
  deleteIssue; the MCP create_issue, transfer_issue, delete_issue, and
  issue_write with method create. The command is read through the shell
  scanner, so `sh -c`, `eval` and `xargs` bodies are seen; a script file is
  not. The door is named apart from the claude plugin's own copy because the
  same session_id can run both plugins, and a shared name would let one
  plugin's UserPromptSubmit spend the other's door.

  This is a gate, so it fails closed: a call that mentions an issue and
  cannot be read is denied.

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
      | gh api repos/o/r/issues/12/comments -f body=hi         |

  Scenario Outline: an identifier write with the door shut is denied, however it is reached
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                            |
      | gh issue create --title t --body b                 |
      | gh issue new -t t -b b                              |
      | gh issue transfer 4 o/other                         |
      | gh issue delete 4 --yes                             |
      | GH_REPO=o/r gh issue create -t t -b b               |
      | cd /w && gh issue create -t t -b b                  |
      | /usr/bin/gh issue create -t t -b b                  |
      | { gh issue create -t t -b b; }                      |
      | sh -c "gh issue create -t t -b b"                   |
      | eval "gh issue transfer 4 o/x"                      |
      | url=$(gh issue create -t t -b b)                     |
      | gh api repos/o/r/issues -f title=t                  |

    @also_guard-bypass-labels
    Examples:
      | command                                            |
      | gh api -X POST repos/o/r/issues --input body.json   |

  Scenario: a graphql createIssue mutation is denied, door shut
    When the agent runs `gh api graphql -f query='mutation { createIssue(input:{}) { issue { id } } }'`
    Then the guard denies

  @also_guard-bypass-labels
  Scenario: a graphql mutation on its own line in a heredoc is denied, door shut
    When the agent runs:
      """
      gh api graphql -F query=@- <<EOF
      mutation {
        transferIssue(input:{}) { issue { id } }
      }
      EOF
      """
    Then the guard denies

  Scenario Outline: a -R/--repo flag before the subcommand is still seen
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                      |
      | gh issue -R o/r create -t t -b b             |
      | gh issue --repo o/r delete 5                 |
      | gh -R o/r issue create -t t -b b              |
      | gh --repo o/r issue transfer 4 o/other        |

  Scenario Outline: an MCP identifier write is judged the same as the gh CLI
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                      | input                              | verdict   |
      | Read                                      | {"file_path":"/x"}                   | is silent |
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

  Scenario: the first write of a turn may be an MCP call; a second write after it is still denied
    When the human speaks, opening the door
    And the agent calls MCP tool "mcp__github__create_issue" with input `{"title":"t"}`
    And the agent runs `gh issue transfer 4 o/other`
    Then the guard denies

  Scenario: a loop keyword inside a flag value is not mistaken for an open loop
    When the human speaks, opening the door
    And the agent runs `gh issue create --title "Retry for uploads while offline" -b b`
    Then the guard is silent

  Scenario: a loop closed earlier in the command does not gate a later create
    When the human speaks, opening the door
    And the agent runs `for f in a b; do echo "$f"; done; gh issue create -t one -b b`
    Then the guard is silent

  Scenario Outline: never a batch, door open or not
    When the human speaks, opening the door
    And the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                            |
      | gh issue create -t a -b b; gh issue create -t c -b d               |
      | gh issue create -t a -b b && gh issue transfer 4 o/x               |
      | for t in a b c; do gh issue create -t "$t" -b x; done              |
      | while read t; do gh issue create -t "$t" -b x; done < list         |
      | until false; do gh issue create -t t -b x; done                   |
      | cat list \| xargs -I{} gh issue create -t {} -b x                  |
      | for t in a b; do for s in x y; do :; done; gh issue create -t "$t" -b b; done |
      | if true; then for t in a b; do gh issue create -t "$t" -b b; done; fi |
      | find . -name "*.md" -exec gh issue create -F {} \;                 |
      | parallel gh issue create -t {} -b x ::: a b                        |

  Scenario: a denied batch does not spend the door
    When the human speaks, opening the door
    And the agent runs `for t in a b c; do gh issue create -t "$t" -b x; done`
    And the agent runs `gh issue create -t one -b b`
    Then the guard is silent

  Scenario: a write another guard denies never ran, so it does not spend the door
    When the human speaks, opening the door
    And another guard denies `gh issue create --title t --body-file /nonexistent`
    And the agent runs `gh issue create -t t -b b`
    Then the guard is silent

  Scenario: the write that ran spends the door, whatever another guard said first
    When the human speaks, opening the door
    And another guard denies `gh issue create --title t --body-file /nonexistent`
    And the agent runs `gh issue create -t t -b b`
    And the agent runs `gh issue create -t u -b c`
    Then the guard denies

  Scenario: a write while the turn's first is still running is denied
    When the human speaks, opening the door
    And the agent starts `gh issue create -t t -b b`
    And the agent runs `gh issue create -t u -b c`
    Then the guard denies

  Scenario: a write that ran keeps the door spent even if its post hook never did
    When the human speaks, opening the door
    And the agent starts `gh issue create -t t -b b`
    And that call ran, but its post hook never did
    And the agent runs `gh issue create -t u -b c`
    Then the guard denies

  Scenario: a claim planted as a link is removed, not written through
    Given the door file is a symlink to "{TMP}/victim"
    When the agent runs `gh issue create -t t -b b`
    Then the guard is silent
    And "{TMP}/victim" still holds "keep"

  Scenario: another session's turn does not open this one's door
    Given the session is "s2"
    When the human speaks, opening the door
    And the session is "s1"
    And the agent runs `gh issue create -t t -b b`
    Then the guard denies


  Scenario: the deny reason says what to do
    When the agent runs `gh issue create -t t -b b`
    Then the guard denies, naming "wait for their yes"

  Scenario: this door and the claude plugin's door do not spend each other
    Given the claude plugin's door file is already present
    When the human speaks, opening the door
    And the agent runs `gh issue create -t t -b b`
    Then the guard is silent
    And the claude plugin's door file is still present

  Scenario: a symlink planted at the door path is replaced, not written through
    Given the door file is a symlink to "{TMP}/victim"
    When the human speaks, opening the door
    Then the door file is a plain file and "{TMP}/victim" still holds "keep"
    When the agent runs `gh issue create -t t -b b`
    Then the guard is silent
