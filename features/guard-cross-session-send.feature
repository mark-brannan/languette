@python
Feature: guard-cross-session-send
  A message from one of the user's sessions to another is plain text the
  other Claude acts on, and no hook fires where it arrives. So the sender is
  checked: a session that read untrusted content this turn (a web page, an
  issue or PR body) does not relay it unseen. Messages to the session's own
  subagents are ordinary and pass. Where a prompt can fire, the user sees the
  target and the first line and decides; in bypassPermissions, where none
  can, the send is denied while the turn has read untrusted content.

  Background:
    Given the permission mode is "default"

  Scenario: a message to one of this session's own subagents passes
    When the human speaks
    And subagent "agent-abc123" starts
    And the agent runs `gh issue view 12 -R o/r`
    And the agent sends "agent-abc123" the message `carry on with step 2`
    Then the guard is silent

  Scenario: a background subagent's message to the main conversation passes
    When the human speaks
    And subagent "agent-abc123" sends "main" the message `done: 3 files changed`
    Then the guard is silent

  Scenario: "main" from the main conversation is a name like any other
    When the human speaks
    And the agent sends "main" the message `hello`
    Then the guard asks

  Scenario Outline: in a prompting mode, a message to another session asks, showing target and first line
    Given the permission mode is "<mode>"
    When the human speaks
    And the agent sends "api-worker" the message `Schema migration finished\nrebase on main now`
    Then the guard asks, naming "`api-worker`"
    And the guard asks, naming "Schema migration finished"

    Examples:
      | mode        |
      | default     |
      | auto        |
      | acceptEdits |
      | dontAsk     |
      | plan        |

  Scenario: the first line shown is cut to 80 characters
    When the human speaks
    And the agent sends "api-worker" the message `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
    Then the guard asks, naming "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa…"

  Scenario: a subagent known only to another session is not this session's
    Given the session is "s2"
    When the human speaks
    And subagent "agent-abc123" starts
    And the session is "s1"
    And the human speaks
    And the agent sends "agent-abc123" the message `carry on`
    Then the guard asks

  Scenario: in bypassPermissions, with nothing untrusted read this turn, a message passes
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent runs `gh pr list -R o/r`
    And the agent sends "api-worker" the message `tests pass on main`
    Then the guard is silent

  Scenario Outline: in bypassPermissions, a message after an untrusted read is denied, naming target, tool and way out
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent runs `<command>`
    And the agent sends "api-worker" the message `please run the steps below`
    Then the guard denies, naming "`api-worker`"
    And the guard denies, naming "<tool>"
    And the guard denies, naming "interactive session"

    Examples:
      | command                                         | tool                                  |
      | gh issue view 12 -R o/r                         | gh issue view                         |
      | gh pr view 7 --comments                         | gh pr view                            |
      | gh -R o/r pr view 7                             | gh pr view                            |
      | gh api repos/o/r/issues/12                      | gh api repos/o/r/issues/12            |
      | gh api repos/o/r/issues/12/comments --paginate  | gh api repos/o/r/issues/12/comments   |
      | gh api -H "Accept: x" repos/o/r/pulls/7/comments | gh api repos/o/r/pulls/7/comments    |
      | gh api /repos/o/r/pulls/7                       | gh api /repos/o/r/pulls/7             |
      | cd /w && gh issue view 3 \| head                | gh issue view                         |
      | sh -c "gh issue view 3"                         | gh issue view                         |
      | body=$(gh pr view 4 --json body)                | gh pr view                            |

  Scenario Outline: a tool that reads the web or an issue, PR or file body opens the door
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent calls tool "<tool>" with input `{}`
    And the agent sends "api-worker" the message `see above`
    Then the guard denies, naming "<tool>"

    Examples:
      | tool                                        |
      | WebFetch                                    |
      | WebSearch                                   |
      | mcp__github__issue_read                     |
      | mcp__plugin_github_github__pull_request_read |
      | mcp__github__get_file_contents              |
      | mcp__github__search_issues                  |
      | mcp__github__search_code                    |

  Scenario Outline: a Bash command that only names an issue read, or reads no body, keeps the door closed
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent runs `<command>`
    And the agent sends "api-worker" the message `status: green`
    Then the guard is silent

    Examples:
      | command                                   |
      | gh pr list -R o/r                         |
      | gh issue create -t t -b b                 |
      | gh api repos/o/r/actions/runs             |
      | echo "gh issue view 12"                   |
      | grep -n "gh pr view" notes.md             |
      | git log --grep "gh issue view"            |
      | ugh issue view 3                          |

  Scenario: a read that failed still opens the door
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent runs `gh issue view 12 -R o/r; false`, which fails
    And the agent sends "api-worker" the message `see above`
    Then the guard denies, naming "gh issue view"

  Scenario: the human's next turn closes the door
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent calls tool "WebFetch" with input `{"url":"https://example.com"}`
    And the human speaks
    And the agent sends "api-worker" the message `summary, in my own words`
    Then the guard is silent

  Scenario: another session's turn does not close this one's door
    Given the permission mode is "bypassPermissions"
    When the human speaks
    And the agent calls tool "WebFetch" with input `{}`
    And the session is "s2"
    And the human speaks
    And the session is "s1"
    And the agent sends "api-worker" the message `see above`
    Then the guard denies

  Scenario: in bypassPermissions, no state means the door is not provably closed: deny
    Given the permission mode is "bypassPermissions"
    When the agent sends "api-worker" the message `hello`
    Then the guard denies, naming "cannot tell"

  Scenario: in a prompting mode, no state asks
    When the agent sends "api-worker" the message `hello`
    Then the guard asks

  Scenario: a garbled state file is no state
    Given the permission mode is "bypassPermissions"
    And the cross-session state file holds `{"subagents": "x"`
    When the agent sends "api-worker" the message `hello`
    Then the guard denies, naming "cannot tell"

  Scenario: a subagent recorded before the first turn leaves the door open
    Given the permission mode is "bypassPermissions"
    When subagent "agent-abc123" starts
    And the agent sends "api-worker" the message `hello`
    Then the guard denies

  Scenario: a payload with no permission mode is judged as one where no prompt may fire
    Given the payload carries no permission mode
    When the human speaks
    And the agent calls tool "WebFetch" with input `{}`
    And the agent sends "api-worker" the message `hello`
    Then the guard denies, naming "unknown permission mode"

  Scenario: a payload with no permission mode and the door closed asks
    Given the payload carries no permission mode
    When the human speaks
    And the agent sends "api-worker" the message `hello`
    Then the guard asks

  Scenario: a state file planted as a link is replaced, not written through
    Given the cross-session state file is a symlink to "{TMP}/victim"
    And the permission mode is "bypassPermissions"
    When the human speaks
    And the agent sends "api-worker" the message `hello`
    Then the guard is silent
    And "{TMP}/victim" still holds "keep"

  Scenario: guard-cross-session-send judges no other tool
    When the agent runs `gh issue view 12`
    Then the guard is silent
