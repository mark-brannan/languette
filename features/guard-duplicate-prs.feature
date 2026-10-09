@python
Feature: guard-duplicate-prs
  A second open PR that closes an issue an open PR already references is
  denied. Two sessions working one issue each open a PR for it, minutes
  apart, and neither reads the issue first: the work is done twice and the
  review is split. So the check sits at the moment the second PR is opened.

  It fires on `gh pr create`, on `gh api` writing to repos/o/r/pulls, and
  on the MCP tool create_pull_request. Every closing reference in the body
  (close, fix or resolve in any tense, an optional colon, then `#N`,
  `owner/repo#N` or an issue URL) is looked up in the issue's timeline; a
  cross-reference from an open pull request is an open PR already on it.
  A body that says `Supersedes` or `Replaces` that PR, in the same forms,
  passes. GitHub that cannot answer, or a page of timeline it fills with
  no open PR on it, asks, as the other guards that ask GitHub do; a body
  the guard cannot read is denied, with the fix.

  gh is a stub throughout: its timeline is empty unless GH_TIMELINE names
  what cross-references the issue. The clone's origin is github.com/o/r.

  Background:
    Given the stub "gh" is first on PATH, for a Python guard
    And a clone of "https://github.com/o/r.git" at "{TMP}/r" on branch "claude/topic"
    And the working directory is "{TMP}/r"

  Scenario Outline: an open PR already on the issue denies, naming it
    Given GH_TIMELINE is "open-pr"
    When the agent runs `<command>`
    Then the guard denies, naming "PR #120 (the first one) is open and already references #114"
    And the guard denies, naming "Supersedes #120"
    And the stub "gh" was called with "api repos/o/r/issues/114/timeline?per_page=100"

    Examples:
      | command                                                         | note                         |
      | gh pr create -t t -b "Closes #114"                              | -b                           |
      | gh pr create --title t --body "fixes: #114"                     | a colon, lower case          |
      | gh pr create -t t --body='Some work. Resolved #114.'            | --body=, mid-sentence        |
      | gh pr create -t t -b "Fixes https://github.com/o/r/issues/114"  | an issue URL                 |
      | gh pr create -t t -R o/r -b "closes o/r#114" --draft            | owner/repo#N, with -R        |
      | gh pr new -t t -b "Closes #114"                                 | gh's alias new               |
      | sh -c 'gh pr create -t t -b "Closes #114"'                      | nested in sh -c              |
      | gh api repos/o/r/pulls -f title=t -f head=h -f base=main -f body='Closes #114' | the REST spelling |
      | gh api repos/{owner}/{repo}/pulls -f title=t -f body='Closes #114' | gh's placeholders, the cwd's repo |

  Scenario: the body from a heredoc command substitution is read
    Given GH_TIMELINE is "open-pr"
    When the agent runs:
      """
      gh pr create -t t --body "$(cat <<'EOF'
      Splits the parser.

      Closes #114
      EOF
      )"
      """
    Then the guard denies, naming "PR #120"

  Scenario: the body from stdin fed by a heredoc is read
    Given GH_TIMELINE is "open-pr"
    When the agent runs:
      """
      gh pr create -t t --body-file - <<'EOF'
      Fixes #114
      EOF
      """
    Then the guard denies, naming "PR #120"

  Scenario: --repo names the repo when the working directory has none
    Given GH_TIMELINE is "open-pr"
    And the working directory is "{HOME}"
    When the agent runs `gh pr create -R o/r -t t -b "Closes #114"`
    Then the guard denies, naming "PR #120"

  Scenario Outline: nothing open on the issue passes
    Given GH_TIMELINE is <timeline>
    When the agent runs `gh pr create -t t -b "Closes #114"`
    Then the guard is silent

    Examples:
      | timeline    | note                                         |
      | "closed-pr" | the PR that referenced it is closed           |
      | "issue"     | an open issue referenced it, not a PR         |
      | unset       | nothing references it                         |

  Scenario Outline: a body that supersedes the open PR passes
    Given GH_TIMELINE is "open-pr"
    When the agent runs `gh pr create -t t -b "<body>"`
    Then the guard is silent

    Examples:
      | body                                          |
      | Closes #114. Supersedes #120.                 |
      | Fixes #114; replaces: o/r#120                 |
      | Fixes #114, replaces https://github.com/o/r/issues/120 |

  Scenario: superseding some other PR does not excuse it
    Given GH_TIMELINE is "open-pr"
    When the agent runs `gh pr create -t t -b "Closes #114. Supersedes #99."`
    Then the guard denies, naming "PR #120"

  Scenario Outline: a body that closes nothing is not looked up
    Given GH_TIMELINE is "open-pr"
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "gh" was not called

    Examples:
      | command                                         | note                             |
      | gh pr create -t t -b "Part of #114"             | a link in prose                  |
      | gh pr create -t t -b "See #114; it closes soon" | a keyword with no reference      |
      | gh pr create -t t -b "Prefixes #114"            | a keyword inside a longer word   |
      | gh pr create --fill                             | no body to judge                 |
      | gh pr create -t t                               | no body at all                   |
      | gh pr view 114                                  | not a create                     |
      | echo gh pr create -b "Closes #114"              | text, not a create               |
      | gh api repos/o/r/pulls                          | a read of the PR list            |
      | gh pr create -t "Closes #114" -b "a fix"        | the title is not the body        |

  Scenario: a body file is read and judged
    Given GH_TIMELINE is "open-pr"
    And a project directory
    And the file "body.md" holds:
      """
      Moves the parser.

      Closes #114
      """
    When the agent runs `gh pr create -R o/r -t t --body-file {PROJ}/body.md`
    Then the guard denies, naming "PR #120"

  Scenario: a body file that supersedes the open PR passes
    Given GH_TIMELINE is "open-pr"
    And a project directory
    And the file "body.md" holds:
      """
      Closes #114

      Supersedes #120
      """
    When the agent runs `gh pr create -R o/r -t t -F {PROJ}/body.md`
    Then the guard is silent

  Scenario Outline: a body the guard cannot read is denied, saying why
    When the agent runs `<command>`
    Then the guard denies, naming "<why>"

    Examples:
      | command                                      | why                    |
      | gh pr create -t t -b "$BODY"                 | built at run time      |
      | gh pr create -t t -b "$(cat notes.md)"       | built at run time      |
      | gh pr create -t t --body-file /nonexistent.md | cannot be read         |
      | gh pr create -t t --body-file /dev/null      | not a regular file     |
      | echo Closes \| gh pr create -t t -F -        | no heredoc             |
      | cd /tmp && gh pr create -t t -F body.md      | relative path after a cd |

  Scenario: a body file written from a heredoc in the same command is read from the heredoc
    Given GH_TIMELINE is "open-pr"
    When the agent runs:
      """
      cat > /nonexistent-dir/body.md <<'EOF'
      Closes #114
      EOF
      gh pr create -t t --body-file /nonexistent-dir/body.md
      """
    Then the guard denies, naming "PR #120"

  Scenario: a body file this command rewrites from a heredoc is judged by the heredoc, not the stale file
    Given GH_TIMELINE is "open-pr"
    And a project directory
    And the file "pr.md" holds:
      """
      An earlier body, closing nothing.
      """
    When the agent runs:
      """
      cat > {PROJ}/pr.md <<'EOF'
      Closes #114
      EOF
      gh pr create -R o/r -t t -F {PROJ}/pr.md
      """
    Then the guard denies, naming "PR #120"

  Scenario Outline: the MCP create_pull_request is judged the same
    Given GH_TIMELINE is "open-pr"
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                            | input                                                                  | verdict                    |
      | mcp__github__create_pull_request                | {"owner":"o","repo":"r","title":"t","head":"h","base":"main","body":"Closes #114"} | denies, naming "PR #120" |
      | mcp__plugin_github_github__create_pull_request  | {"owner":"o","repo":"r","title":"t","head":"h","base":"main","body":"Fixes #114\\nSupersedes #120"} | is silent |
      | mcp__github__create_pull_request                | {"owner":"o","repo":"r","title":"t","head":"h","base":"main","body":"Part of #114"} | is silent |
      | mcp__github__create_pull_request                | {"owner":"o","repo":"r","title":"t","head":"h","base":"main"}          | is silent                  |

  Scenario Outline: GitHub that cannot answer asks
    Given GH_FAIL is "1"
    When the agent runs `<command>`
    Then the guard asks, naming "GitHub couldn't say"

    Examples:
      | command                                      |
      | gh pr create -t t -b "Closes #114"           |
      | gh pr create -t t -b "Fixes other/repo#7"    |

  Scenario: a full page of timeline with no open PR on it asks, since an older one may sit past it
    Given GH_TIMELINE is "full"
    When the agent runs `gh pr create -t t -b "Closes #114"`
    Then the guard asks, naming "a timeline past 100 events"

  Scenario: GitHub that cannot answer asks for the MCP tool too
    Given GH_FAIL is "1"
    When the agent calls MCP tool "mcp__github__create_pull_request" with input `{"owner":"o","repo":"r","title":"t","head":"h","base":"main","body":"Closes #114"}`
    Then the guard asks, naming "GitHub couldn't say"

  Scenario: a repo the guard cannot tell asks
    Given the working directory is "{HOME}"
    When the agent runs `gh pr create -t t -b "Closes #114"`
    Then the guard asks, naming "can't tell which repo"
