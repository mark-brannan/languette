@python
Feature: guard-private-terms
  Text bound for a public GitHub repo is checked against the user's private
  terms file, wherever the text travels: a flag value, a heredoc, a file, an
  MCP field. The file is the private_terms_file option. Without one the guard
  is inert; with one that cannot be read it is closed. The long tail of
  shell shapes is walked by the scenarios below.

  Why. A private repo or notes directory holds details (boat names,
  hostnames, service URLs, account identifiers) that must not reach the
  public code repos, and a rule kept as prose in CLAUDE.md has already failed
  at that. Once a term is in a public issue or PR comment it is in GitHub's
  history and every mirror of it; the undo is a support ticket, not an edit.
  So the check moves from the model's memory to the moment the text leaves
  the machine.

  It fires on PreToolUse for Bash `gh issue|pr create|comment|edit|review|
  close|reopen|merge`, `gh api` writing to repos/*/*/issues|pulls, a graphql
  mutation that comments on or opens an issue or PR, and the GitHub MCP tools
  that create or edit an issue, PR, comment or review (matched on the tool
  name's tail). A body posted from `python -c`, `curl` or a script file is
  not inspected. The text judged is only what is genuinely posted: literal
  --body, --title, --comment, --subject and --label values, `gh api`
  -f/-F/--field/--raw-field values, every heredoc body, and the contents of
  --body-file, --comment-file, -F, --input and `-F key=@file`, never the path
  itself, which is read, not posted. A value built from `$(...)` or an unfed
  `$VAR` is refused, not scanned around. Matching is case-insensitive fixed
  substrings; the reason names the terms that hit and nothing around them. A
  --body-file path is read as the shell would read it, `~`, `.` and `..`
  included, after replaying what the command does before the gh (a cd, an
  assignment).

  A home-directory path in that text is a sanitization job, not a denial job:
  where this Claude Code version's PreToolUse hooks support rewriting the
  call (`updatedInput`) the guard replaces it with `~` and allows; otherwise
  it stays a denial whose reason names the substitution to make by hand.

  The target repo is --repo/-R, GH_REPO=, a positional issue or PR URL or
  `owner/repo#n`, the `gh api` path, or MCP owner/repo; failing those, the
  origin of the payload's cwd, unless the command also runs `cd`, in which
  case it is unknown. A graphql mutation names its target by node id, so its
  repo is always unknown, never the cwd's. Unknown is scanned. Only a repo
  listed in the private_repos option (comma-separated owner/name, default
  empty) is allowed unscanned, and only when every target of the command is
  one.

  Inert without a terms file: a guard that denied every public post for want
  of a list would be unusable for anyone who has none. Once the option is
  set the file is load-bearing, and the guard is a gate: a body it cannot
  see, a gh write whose flag shape it does not recognise as carrying text, or
  a terms file that is set but unreadable or empty while a target is not a
  private repo is a deny, with the fix in the reason.

  Background:
    Given the private terms file holds:
      """
      # one term per line
      Wanderlust
      gateway.home.example
      """

  Scenario Outline: a term in the posted text is denied, naming the term
    When the agent runs `<command>`
    Then the guard denies, naming "<term>"

    Examples:
      | command                                                         | term                 |
      | gh issue create -R o/r -t t -b "seen on Wanderlust last night"  | Wanderlust           |
      | gh issue create -R o/r -t "WANDERLUST: AIS drops" -b b          | Wanderlust           |
      | gh pr comment 12 -R o/r --body="host is gateway.home.example"   | gateway.home.example |
      | sh -c 'gh issue create -R o/r -t t -b "on Wanderlust"'          | Wanderlust           |
      | gh api repos/o/r/issues -f title=t -f body=Wanderlust           | Wanderlust           |

  Scenario Outline: text with no term, a read, or a command that posts nothing is silent
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                    |
      | gh issue create -R o/r -t t -b "all public"                |
      | gh issue list -R o/r --search Wanderlust                   |
      | gh issue view 3 -R o/r                                     |
      | echo Wanderlust > note.md                                  |
      | gh pr comment 12 -R o/r -b "private terms -- see the file" |

  Scenario: a term in a heredoc body is denied
    When the agent runs:
      """
      gh issue create -R o/r -t t -F - <<'EOF'
      ssh to gateway.home.example
      EOF
      """
    Then the guard denies, naming "gateway.home.example"

  Scenario: a term in the file named by --body-file is denied, one only in its path is not
    Given a project directory
    And the file "body.md" holds:
      """
      reproduced aboard Wanderlust
      """
    And the file "Wanderlust/clean.md" holds:
      """
      nothing private here
      """
    When the agent runs `gh issue create -R o/r -t t --body-file {PROJ}/body.md`
    Then the guard denies, naming "Wanderlust"
    When the agent runs `gh issue create -R o/r -t t --body-file {PROJ}/Wanderlust/clean.md`
    Then the guard is silent

  Scenario: a repo listed in private_repos is never scanned
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "you/notes,you/scratch"
    When the agent runs `gh issue create -R you/scratch -t t -b "Wanderlust"`
    Then the guard is silent
    When the agent runs `gh issue comment https://github.com/you/notes/issues/1 -b "Wanderlust"`
    Then the guard is silent

  Scenario: with private_repos unset, every repo is scanned
    When the agent runs `gh issue create -R you/notes -t t -b "Wanderlust"`
    Then the guard denies, naming "Wanderlust"

  Scenario Outline: a positional target or a graphql mutation is scanned against its own repo
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "you/notes"
    When the agent runs `<command>`
    Then the guard denies, naming "Wanderlust"

    Examples:
      | command                                                                  |
      | gh issue comment https://github.com/o/r/issues/1 -b Wanderlust           |
      | gh pr comment o/r#1 -b Wanderlust                                        |
      | gh api graphql -f query='mutation { addComment(input:{body:"Wanderlust"}) { clientMutationId } }' |

  Scenario: a body built at run time that no heredoc feeds cannot be seen, so it is denied
    When the agent runs `gh issue create -R o/r -t t -b "$(date)"`
    Then the guard denies

  Scenario Outline: an id or number field built at run time carries no text, so it is not refused
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                                     | verdict   |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id=$id           | is silent |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id=${id}         | is silent |
      | work-item brief c1 'gh api repos/o/r/issues/1/sub_issues -F sub_issue_id=$id' | is silent |
      | gh api repos/o/r/issues/1/comments -f body=$x                               | denies    |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id="$(cat f)"    | denies    |

  Scenario Outline: an MCP tool's text is judged the same as the gh CLI
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                         | input                                                      | verdict   |
      | mcp__github__create_issue                    | {"owner":"o","repo":"r","title":"t","body":"Wanderlust"}   | denies    |
      | mcp__plugin_github_github__add_issue_comment | {"owner":"o","repo":"r","body":"on gateway.home.example"}  | denies    |
      | mcp__github__create_issue                    | {"owner":"o","repo":"r","title":"t","body":"clean"}        | is silent |
      | mcp__github__get_issue                       | {"owner":"o","repo":"r","body":"Wanderlust"}               | is silent |

  Scenario: the home directory in the text is rewritten to ~ and the post allowed
    Given the private terms file holds:
      """
      {HOME}
      """
    When the agent runs `gh issue comment 3 -R o/r -b {HOME}/x`
    Then the guard allows, rewriting the command to "gh issue comment 3 -R o/r -b ~/x"

  Scenario: a terms file that is set but cannot be read denies, naming the option
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is "{HOME}/no-such-terms.txt"
    When the agent runs `gh issue create -R o/r -t t -b "all public"`
    Then the guard denies, naming "private_terms_file"

  Scenario: a terms file with no terms in it denies
    Given the private terms file holds:
      """
      # comments only

      """
    When the agent runs `gh issue create -R o/r -t t -b "all public"`
    Then the guard denies, naming "no terms in it"

  Scenario: with the option unset the guard is inert
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard is silent

  Scenario: with the option empty the guard is inert
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is ""
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard is silent
