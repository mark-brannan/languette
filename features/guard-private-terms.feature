@python
Feature: guard-private-terms
  Text bound for a public GitHub repo is judged twice, wherever it travels:
  a flag value, a heredoc, a file, an MCP field.

  Anonymize. A home-directory path in that text, $HOME or another spelling
  of it (/home/<user>, /Users/<user>, /mnt/c/Users/<user>, <user> the login
  name), is rewritten to `~` and the call is allowed, as a secret is
  redacted. It is on by default, needs no configuration and runs whether or
  not a terms file is set; the guard_private_terms_anonymize option turns it
  off. It never denies for text it cannot read: it cannot help there, so the
  call goes through.

  Hard block. A short list of terms so sensitive that even a redacted post
  could leak a concept or a strategy (a company name, a code name). A hit
  denies the whole post. Only this half needs a terms file, and only this
  half fails closed.

  Why. A private repo or notes directory holds details (hostnames,
  service URLs, account identifiers, project code names) that must not reach the
  public code repos, and a rule kept as prose in an instructions file is not
  enough. Once a term is in a public issue or PR comment it is in GitHub's
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

  The anonymize rewrite (`updatedInput`) replaces the home path with `~` in
  the posted text alone and allows the call. A path the command also holds
  outside the posted text is a denial, since a text match cannot tell which
  copy is posted, and so is a Claude Code version whose PreToolUse hooks
  cannot rewrite the call; either reason names the substitution to make by
  hand. A home path inside a file's contents (--body-file) is out of the
  rewrite's reach: it stays a denial with the fix in the reason. Open:
  whether that file case should deny, pass or be handled another way.

  The target repo is --repo/-R, GH_REPO=, a positional issue or PR URL or
  `owner/repo#n`, the `gh api` path, or MCP owner/repo; failing those, the
  origin of the payload's cwd, unless the command also runs `cd`, in which
  case it is unknown. A graphql mutation names its target by node id, so its
  repo is always unknown, never the cwd's. Unknown is scanned. Only a repo
  listed in the private_repos option (comma-separated owner/name, default
  empty) is allowed unscanned, and only when every target of the command is
  one.

  The terms file is the private_terms_file option. Current thinking: the
  option expands a leading `~` or `$HOME` itself, since Claude Code does not
  expand plugin options, so settings need no machine-specific absolute
  path. Current thinking: with the option unset or empty, the guard reads
  ~/.config/languette/private-terms.txt if it exists; a CI job or a cloud VM
  provisions terms by writing that file, from a secret say, and no
  environment variable is read. No file at either place means no hard
  block: a guard that denied every public post for want of a list would be
  unusable for anyone who has none, and anonymize still runs.

  Once a terms file is found the hard block is load-bearing, and the guard
  is a gate: a body it cannot see, a gh write whose flag shape it does not
  recognise as carrying text, or a terms file that is set but unreadable or
  empty while a target is not a private repo is a deny, with the fix in the
  reason.

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

    @also_guard-signed-comments
    Examples:
      | command                                                         | term                 |
      | gh pr comment 12 -R o/r --body="host is gateway.home.example"   | gateway.home.example |

    @also_guard-github-issues
    Examples:
      | command                                                         | term                 |
      | gh issue create -R o/r -t t -b "seen on Wanderlust last night"  | Wanderlust           |
      | gh issue create -R o/r -t "WANDERLUST: AIS drops" -b b          | Wanderlust           |
      | sh -c 'gh issue create -R o/r -t t -b "on Wanderlust"'          | Wanderlust           |
      | gh api repos/o/r/issues -f title=t -f body=Wanderlust           | Wanderlust           |

  Scenario Outline: text with no term, a read, or a command that posts nothing is silent
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                    |
      | gh issue list -R o/r --search Wanderlust                   |
      | gh issue view 3 -R o/r                                     |
      | echo Wanderlust > note.md                                  |

    @also_guard-signed-comments
    Examples:
      | command                                                    |
      | gh pr comment 12 -R o/r -b "private terms -- see the file" |

    @also_guard-github-issues
    Examples:
      | command                                                    |
      | gh issue create -R o/r -t t -b "all public"                |

  @also_guard-github-issues
  Scenario: a term in a heredoc body is denied
    When the agent runs:
      """
      gh issue create -R o/r -t t -F - <<'EOF'
      ssh to gateway.home.example
      EOF
      """
    Then the guard denies, naming "gateway.home.example"

  @also_guard-github-issues
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

  @also_guard-github-issues @also_guard-signed-comments
  Scenario: a repo listed in private_repos is never scanned
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "you/notes,you/scratch"
    When the agent runs `gh issue create -R you/scratch -t t -b "Wanderlust"`
    Then the guard is silent
    When the agent runs `gh issue comment https://github.com/you/notes/issues/1 -b "Wanderlust"`
    Then the guard is silent

  @also_guard-github-issues
  Scenario: with private_repos unset, every repo is scanned
    When the agent runs `gh issue create -R you/notes -t t -b "Wanderlust"`
    Then the guard denies, naming "Wanderlust"

  Scenario Outline: a positional target or a graphql mutation is scanned against its own repo
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "you/notes"
    When the agent runs `<command>`
    Then the guard denies, naming "Wanderlust"

    @also_guard-signed-comments
    Examples:
      | command                                                                  |
      | gh issue comment https://github.com/o/r/issues/1 -b Wanderlust           |
      | gh pr comment o/r#1 -b Wanderlust                                        |
      | gh api graphql -f query='mutation { addComment(input:{body:"Wanderlust"}) { clientMutationId } }' |

  @also_guard-github-issues
  Scenario: a body built at run time that no heredoc feeds cannot be seen, so it is denied
    When the agent runs `gh issue create -R o/r -t t -b "$(date)"`
    Then the guard denies

  Scenario Outline: an id or number field built at run time carries no text, so it is not refused
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                                      | verdict   |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id=$id            | is silent |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id=${id}          | is silent |
      | some-tool note c1 'gh api repos/o/r/issues/1/sub_issues -F sub_issue_id=$id' | is silent |
      | gh api -X POST repos/o/r/issues/76/sub_issues -F sub_issue_id="$(cat f)"     | denies    |

    @also_guard-signed-comments
    Examples:
      | command                                                                     | verdict   |
      | gh api repos/o/r/issues/1/comments -f body=$x                               | denies    |

  Scenario Outline: an MCP tool's text is judged the same as the gh CLI
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                           | input                                                                     | verdict   |
      | mcp__github__get_issue                         | {"owner":"o","repo":"r","body":"Wanderlust"}                              | is silent |

    @also_guard-signed-comments
    Examples:
      | tool                                           | input                                                                     | verdict   |
      | mcp__plugin_github_github__add_issue_comment   | {"owner":"o","repo":"r","body":"on gateway.home.example"}                 | denies    |
      | mcp__github__add_reply_to_pull_request_comment | {"owner":"o","repo":"r","pullNumber":1,"commentId":9,"body":"Wanderlust"} | denies    |
      | mcp__github__update_issue_comment              | {"owner":"o","repo":"r","commentId":9,"body":"on gateway.home.example"}   | denies    |

    @also_guard-github-issues
    Examples:
      | tool                                           | input                                                                     | verdict   |
      | mcp__github__create_issue                      | {"owner":"o","repo":"r","title":"t","body":"Wanderlust"}                  | denies    |
      | mcp__github__create_issue                      | {"owner":"o","repo":"r","title":"t","body":"clean"}                       | is silent |

  # --- anonymize: a home path is rewritten to ~ and the call allowed -------------

  @also_guard-signed-comments
  Scenario: the home directory in the text is rewritten to ~ and the call allowed
    When the agent runs `gh issue comment 3 -R o/r -b {HOME}/x`
    Then the guard allows, rewriting the command to "gh issue comment 3 -R o/r -b \~/x"

  @also_guard-signed-comments
  Scenario: anonymize needs no terms file
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    When the agent runs `gh pr comment 3 -R o/r --body "repro under {HOME}/x"`
    Then the guard allows, rewriting the command to `gh pr comment 3 -R o/r --body "repro under ~/x"`

  Scenario Outline: another spelling of the home directory is rewritten too, another user's is not
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    When the agent runs `gh issue comment 3 -R o/r -b <path>/x`
    Then the guard <verdict>

    @also_guard-signed-comments
    Examples:
      | path                    | verdict                                                                  |
      | /home/{USER}            | allows, rewriting the command to "gh issue comment 3 -R o/r -b \~/x"     |
      | /Users/{USER}           | allows, rewriting the command to "gh issue comment 3 -R o/r -b \~/x"     |
      | /mnt/c/Users/{USER}     | allows, rewriting the command to "gh issue comment 3 -R o/r -b \~/x"     |
      | /home/someone-else      | is silent                                                                |

  Scenario Outline: the guard_private_terms_anonymize option turns the rewrite off
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    And CLAUDE_PLUGIN_OPTION_GUARD_PRIVATE_TERMS_ANONYMIZE is "<value>"
    When the agent runs `gh issue comment 3 -R o/r -b {HOME}/x`
    Then the guard <verdict>

    @also_guard-signed-comments
    Examples:
      | value | verdict                                                              |
      | true  | allows, rewriting the command to "gh issue comment 3 -R o/r -b \~/x" |
      | false | is silent                                                            |

  # Anonymize cannot help with text it cannot read, so it lets the call through;
  # only the hard block, with terms to protect, fails closed (the Rule below).
  Scenario Outline: with no terms file, text the guard cannot read passes
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                         |
      | gh issue comment 3 -R o/r --response-body-file /tmp/x           |

    @also_guard-github-issues
    Examples:
      | command                                                         |
      | gh issue create -R o/r -t t -b "$(date)"                        |
      | cat notes.md \| gh issue create -R o/r -t x -F -                |
      | gh issue create -R o/r -t x --body-file /nowhere/absent.md      |

  @also_guard-signed-comments
  Scenario: only the posted text is rewritten, not a cd before it
    When the agent runs `cd "{HOME}/x" && gh pr comment 3 -R o/r --body "under {HOME}/x"`
    Then the guard allows, rewriting the command to `cd "{HOME}/x" && gh pr comment 3 -R o/r --body "under ~/x"`

  @also_guard-signed-comments
  Scenario: a path the command also uses outside the posted text is a denial, not a guess at which is posted
    When the agent runs `gh pr comment 3 -R o/r --body "{HOME}/x" && cd {HOME}/x`
    Then the guard denies, naming "by hand"

  @also_guard-signed-comments
  Scenario: a body that repeats an earlier cd path is a denial too
    When the agent runs `cd "{HOME}/x" && gh pr comment 3 -R o/r --body "{HOME}/x"`
    Then the guard denies, naming "by hand"

  @also_guard-signed-comments
  Scenario: a path used by a later command is a denial that says to write ~ by hand
    When the agent runs `gh pr comment 3 -R o/r --body "{HOME}/x"; ls {HOME}/x`
    Then the guard denies, naming "by hand"

  @also_guard-signed-comments
  Scenario: a ~ is escaped wherever a bare word has the path, not only at its start
    When the agent runs `gh pr comment 3 -R o/r -b note={HOME}/x`
    Then the guard allows, rewriting the command to "gh pr comment 3 -R o/r -b note=\~/x"

  @also_guard-github-issues
  Scenario: a title and a body with the same path are both rewritten
    When the agent runs `gh issue create -R o/r -t {HOME}/x -b {HOME}/x`
    Then the guard allows, rewriting the command to "gh issue create -R o/r -t \~/x -b \~/x"

  @also_guard-signed-comments
  Scenario: a multi-line quoted body is rewritten
    When the agent runs:
      """
      gh pr comment 3 -R o/r --body "line1
      see {HOME}/x"
      """
    Then the guard allows, rewriting the command to:
      """
      gh pr comment 3 -R o/r --body "line1
      see ~/x"
      """

  @also_guard-signed-comments
  Scenario: a cd whose path matches a multi-line body once flattened is a denial
    When the agent runs:
      """
      cd "{HOME}/x y" && gh pr comment 3 -R o/r --body "{HOME}/x
      y"
      """
    Then the guard denies, naming "by hand"

  # --- the hard block: a term denies the whole post -----------------------------

  @also_guard-github-issues
  Scenario: a terms file that is set but cannot be read denies, naming the option
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is "{HOME}/no-such-terms.txt"
    When the agent runs `gh issue create -R o/r -t t -b "all public"`
    Then the guard denies, naming "private_terms_file"

  @also_guard-github-issues
  Scenario: a terms file with no terms in it denies
    Given the private terms file holds:
      """
      # comments only

      """
    When the agent runs `gh issue create -R o/r -t t -b "all public"`
    Then the guard denies, naming "no terms in it"

  # Current thinking: Claude Code does not expand a plugin option, so the
  # guard does, and settings need no machine-specific absolute path.
  Scenario Outline: the terms file option may start with ~ or $HOME
    Given the file "{HOME}/pt-terms.txt" holds:
      """
      Wanderlust
      """
    And CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is "<option>"
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard denies, naming "Wanderlust"

    @also_guard-github-issues
    Examples:
      | option             |
      | ~/pt-terms.txt     |
      | $HOME/pt-terms.txt |

  # Current thinking: a CI job or a cloud VM provisions terms by writing this
  # file, from a secret say; no environment variable is read.
  @also_guard-github-issues
  Scenario: with the option unset, a terms file at the default path is read
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    And the default private terms file holds:
      """
      Wanderlust
      """
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard denies, naming "Wanderlust"
    When the agent runs `gh issue create -R o/r -t t -b "all public"`
    Then the guard is silent

  @also_guard-github-issues
  Scenario: with the option unset and no file at the default path, no term is blocked
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard is silent

  @also_guard-github-issues
  Scenario: with the option empty and no file at the default path, no term is blocked
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is ""
    When the agent runs `gh issue create -R o/r -t t -b "seen on Wanderlust"`
    Then the guard is silent

  Rule: the long tail of shapes a post takes
    A private term is caught wherever the text travels (a flag value, a
    heredoc, an MCP field, another case), a repo in private_repos is never
    scanned, reads are never touched, and the gate is loud when it cannot see
    the text or the denylist. These scenarios walk the long tail of shapes
    those promises take, with a terms file set, so the hard block is on.

    Background:
      Given the private terms file holds:
        """
        # private terms -- lines starting with # are comments

        Wanderlust
        gateway.home.example
          acct-4471
        """
      And CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "someone/else, you/notes"

    # --- a term in the body, wherever it travels ----------------------------------

    @also_guard-github-issues
    Scenario: the deny names the term and nothing around it
      When the agent runs `gh issue create -R o/r -t "Log rotation" --body "seen on Wanderlust last night"`
      Then the guard denies, naming "Wanderlust"
      And the guard denies, not naming "last night"
      And the guard denies, naming "private_repos"
      And the guard denies, naming "rewrite the body"

    Scenario Outline: a term is found in whichever flag, spelling or position carries it
      When the agent runs `<command>`
      Then the guard denies, naming "<term>"

      Examples:
        | command                                                              | term                 |
        | gh issue edit 3 -R o/r --body="host is gateway.home.example"         | gateway.home.example |
        | make build && gh pr create -R o/r --title x --body "cf Wanderlust"   | Wanderlust           |

      @also_guard-signed-comments
      Examples:
        | command                                                              | term                 |
        | gh pr comment 12 -R o/r -b"tested on Wanderlust"                     | Wanderlust           |
        | gh pr review 9 -R o/r --approve --body "ok from acct-4471"           | acct-4471            |
        | gh issue close 3 -R o/r -c "moved to Wanderlust log"                 | Wanderlust           |

      @also_guard-bypass-ruleset
      Examples:
        | command                                                              | term                 |
        | gh pr merge 5 -R o/r --squash -b "tested on wanderlust"              | Wanderlust           |

      @also_guard-github-issues
      Examples:
        | command                                                              | term                 |
        | gh issue create -R o/r -t x -b Wander\\lust                          | Wanderlust           |
        | gh issue create -R o/r -t x -b 'Wander'"lust"                        | Wanderlust           |
        | gh issue create -R o/r -t x -b "ACCT-4471 again"                     | acct-4471            |
        | gh issue create -R o/r -t x -b "WANDERLUST"                          | Wanderlust           |

    @also_guard-github-issues
    Scenario: a term is found in the body a variable carries out of a heredoc
      When the agent runs:
        """
        body=$(cat <<EOF
        crew of Wanderlust
        EOF
        )
        gh issue create -R o/r -t x -b "$body"
        """
      Then the guard denies, naming "Wanderlust"

    @also_guard-github-issues
    Scenario: a dot in a term is a dot, not any character
      When the agent runs `gh issue create -R o/r -t x -b "gatewayXhomeXexample"`
      Then the guard is silent

    # --- MCP ----------------------------------------------------------------------

    Scenario Outline: an MCP tool's field is judged wherever it sits in the input
      When the agent calls MCP tool "<tool>" with input `<input>`
      Then the guard <verdict>

      @also_guard-github-issues
      Examples:
        | tool                                  | input                                                                                              | verdict   |
        | mcp__github__issue_write              | {"method":"create","owner":"o","repo":"r","title":"Wanderlust AIS"}                                | denies    |
        | mcp__github__create_issue             | {"owner":"you","repo":"notes","title":"x","body":"Wanderlust"}                                      | is silent |

      @also_guard-signed-comments
      Examples:
        | tool                                  | input                                                                                              | verdict   |
        | mcp__github__create_pull_request_review | {"owner":"o","repo":"r","pullNumber":1,"event":"COMMENT","comments":[{"path":"a.ts","body":"acct-4471"}]} | denies    |

    @also_guard-signed-comments
    Scenario: the home directory in an MCP body is rewritten to ~ and the call allowed
      When the agent calls MCP tool "mcp__github__add_issue_comment" with input `{"owner":"o","repo":"r","issue_number":3,"body":"repro under {HOME}/project"}`
      Then the guard allows, rewriting the input field "body" to "repro under ~/project"

    # --- gh api -------------------------------------------------------------------

    Scenario Outline: a gh api write is judged, a read is not
      When the agent runs `<command>`
      Then the guard <verdict>

      Examples:
        | command                                                                                   | verdict   |
        | gh api -X PATCH repos/o/r/issues/3 -f body=gateway.home.example                           | denies    |
        | gh api repos/o/r/issues --jq ".[].title"                                                  | is silent |
        | gh api graphql -f query='{ repository(owner:"o",name:"r"){ issue(number:3){ title } } }'  | is silent |

      @also_guard-signed-comments
      Examples:
        | command                                                                                   | verdict   |
        | gh api repos/o/r/pulls/3/reviews -f event=COMMENT -f body="acct-4471"                     | denies    |

      @also_guard-github-issues
      Examples:
        | command                                                                                   | verdict   |
        | gh api repos/you/notes/issues -f title=x -f body=Wanderlust                               | is silent |

    # --- which repo a post targets ------------------------------------------------

    Scenario Outline: a repo named on the command line is never scanned when it is listed
      When the agent runs `<command>`
      Then the guard is silent

      @also_guard-github-issues
      Examples:
        | command                                                                 |
        | gh issue create --repo you/notes -t x -b 'aboard Wanderlust'            |
        | gh issue create -R You/Notes -t x -b Wanderlust                         |
        | GH_REPO=you/notes gh issue create -t x -b Wanderlust                    |

      @also_guard-signed-comments
      Examples:
        | command                                                                 |
        | gh issue comment 3 --repo=https://github.com/you/notes -b Wanderlust    |

    @also_guard-github-issues
    Scenario: with private_repos empty, nothing is private
      Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is ""
      When the agent runs `gh issue create -R you/notes -t x -b Wanderlust`
      Then the guard denies, naming "Wanderlust"

    Scenario Outline: with no repo named, the origin of the working directory decides, unless the command moves
      Given a clone of "git@github.com:you/notes.git" at "{TMP}/private" on branch "main"
      And a clone of "https://github.com/o/r.git" at "{TMP}/public" on branch "main"
      And the directory "{TMP}/nogit"
      And the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-github-issues
      Examples:
        | cwd              | command                                                                                                              | verdict   |
        | {TMP}/private    | gh issue create -t x -b "aboard Wanderlust"                                                                          | is silent |
        | {TMP}/public     | gh issue create -t x -b Wanderlust                                                                                   | denies    |
        | {TMP}/nogit      | gh issue create -t x -b Wanderlust                                                                                   | denies    |
        | {TMP}/private    | cd {TMP}/public && gh issue create -t x -b Wanderlust                                                                | denies    |

      @also_guard-signed-comments
      Examples:
        | cwd              | command                                                                                                              | verdict   |
        | {TMP}/private    | gh issue comment https://github.com/o/r/issues/1 -b Wanderlust                                                      | denies    |
        | {TMP}/private    | gh pr comment o/r#1 -b Wanderlust                                                                                    | denies    |
        | {TMP}/public     | gh issue comment https://github.com/you/notes/issues/1 -b Wanderlust                                                 | is silent |
        | {TMP}/private    | gh api graphql -f query='mutation { addComment(input:{subjectId:"I_1", body:"from Wanderlust"}) { clientMutationId } }' | denies    |

      @also_guard-github-issues @also_guard-signed-comments
      Examples:
        | cwd              | command                                                                                                              | verdict   |
        | {TMP}/public     | gh issue create --repo you/notes -t x -b Wanderlust && gh issue comment 3 --repo o/r -b Wanderlust                   | denies    |

    # --- reads and clean text pass ------------------------------------------------

    Scenario Outline: a read, clean text, or no command at all is silent
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                                                                                                     |
        | gh issue list -R o/r --label ready                                                                                                                          |
        | gh pr view 12 -R o/r --comments                                                                                                                             |
        | gh pr checks 12 --watch                                                                                                                                     |
        | gh pr merge 12 --squash --delete-branch                                                                                                                     |
        | echo "gh issue create --body hi"                                                                                                                            |
        | ls -la                                                                                                                                                      |

      @also_guard-github-issues
      Examples:
        | command                                                                                                                           |
        | gh issue create -R o/r -t "Design note" -b "Argument in o/r requirements.md; see https://github.com/o/r-engine/pull/25 and o/r#3" |

    Scenario: a Bash call with no command, and a tool this guard does not gate, are silent
      When the agent calls tool "Bash" with input `{}`
      Then the guard is silent
      When the agent calls tool "Read" with input `{"file_path": "/x"}`
      Then the guard is silent

    # --- the gate is loud when it cannot see --------------------------------------

    @also_guard-github-issues
    Scenario: a body from stdin with no heredoc to read is denied
      When the agent runs `cat notes.md | gh issue create -R o/r -t x -F -`
      Then the guard denies, naming "stdin"

    @also_guard-github-issues
    Scenario: a body from stdin is read from the heredoc that feeds it
      When the agent runs:
        """
        gh issue create -R o/r -t x -F - <<EOF
        all public
        EOF
        """
      Then the guard is silent

    @also_guard-github-issues @also_guard-signed-comments
    Scenario: a body built at run time is denied, and says so
      When the agent runs `gh issue create -R o/r -t x -b "$(cat notes.md)"`
      Then the guard denies, naming "run time"
      When the agent runs `gh pr comment 3 -R o/r --body "$body"`
      Then the guard denies

    Scenario: a heredoc inside the body's own $(...) is the text the gate reads
      When the agent runs:
        """
        gh pr create -R o/r -t x --body "$(cat <<'EOF'
        nothing private
        EOF
        )"
        """
      Then the guard is silent
      When the agent runs:
        """
        gh pr create -R o/r -t x --body "$(cat <<'EOF'
        seen aboard Wanderlust
        EOF
        )"
        """
      Then the guard denies, naming "Wanderlust"

    @also_guard-github-issues @also_guard-signed-comments
    Scenario: a variable fed by a clean heredoc is read, one fed by anything else is not
      When the agent runs:
        """
        b=$(cat <<EOF
        public text
        EOF
        ); gh pr comment 3 -R o/r --body "$b"
        """
      Then the guard is silent
      When the agent runs:
        """
        cat <<EOF
        hello
        EOF
        gh issue create -R o/r -t x --body "$(cat notes.md)"
        """
      Then the guard denies, naming "no heredoc in this command feeds it"
      When the agent runs:
        """
        body=$(cat notes.md); cat <<EOF
        hi
        EOF
        gh pr comment 3 -R o/r --body "$body"
        """
      Then the guard denies

    Scenario Outline: single quotes make $ and a backtick ordinary characters, double quotes do not
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-signed-comments
      Examples:
        | command                                                      | verdict                      |
        | gh pr comment 3 -R o/r -b 'Fixed in `abc123`, see `prose-budget`.' | is silent             |
        | gh pr comment 3 -R o/r -b "Fixed in `git rev-parse HEAD`"    | denies                       |
        | gh pr comment 3 -R o/r -b 'Fixed on `Wanderlust`.'           | denies, naming "Wanderlust"  |

      @also_guard-github-issues
      Examples:
        | command                                                      | verdict                      |
        | gh issue create -R o/r -t x -b 'run $(date) yourself'        | is silent                    |

    # --- fail closed: a flag that looks like it carries text ----------------------

    Scenario: an unrecognised flag shaped like a body is refused, naming the flag
      When the agent runs `gh issue comment 3 -R o/r --response-body-file /tmp/x`
      Then the guard denies, naming "--response-body-file"
      And the guard denies, naming "doesn't recognise its shape"

    @also_guard-github-issues
    Scenario: an unrecognised flag is refused on gh api too
      When the agent runs `gh api repos/o/r/issues -f title=x --long-comment-blob=hi`
      Then the guard denies

    Scenario: an unrecognised flag aimed at a private repo is not scanned
      When the agent runs `gh issue comment 3 --repo you/notes --response-body-file /tmp/x`
      Then the guard is silent

    # --- a path in the command is read, never posted ------------------------------
    # Three false positives from the transcripts (2026-09-12): a `cd` prefix, a
    # --body-file under a scratchpad path, an unrecognised --comment-file. The raw
    # command line was scanned, and a path under $HOME collides with a denylist
    # that names $HOME.

    Scenario Outline: a path under the home directory that the command reads is not posted text, so nothing is rewritten
      Given the file "{HOME}/pt-scratch-body.md" holds:
        """
        a clean scratchpad body
        """
      And the file "{HOME}/pt-scratch-comment.md" holds:
        """
        a clean scratchpad comment
        """
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                |
        | gh issue comment 3 -R o/r --comment-file {HOME}/pt-scratch-comment.md  |

      @also_guard-signed-comments
      Examples:
        | command                                                                |
        | cd {HOME}/worktrees/xyz && gh issue comment 3 -R o/r -b 'ready for review' |

      @also_guard-github-issues
      Examples:
        | command                                                                |
        | gh issue create -R o/r -t x --body-file {HOME}/pt-scratch-body.md      |

    Scenario: a term in a --comment-file's content still denies
      Given a project directory
      And the file "comment-term.md" holds:
        """
        seen aboard Wanderlust
        """
      When the agent runs `gh issue comment 3 -R o/r --comment-file {PROJ}/comment-term.md`
      Then the guard denies, naming "Wanderlust"

    # --- the home directory: a sanitization job, until it is not one --------------
    # Open: a rewrite of the call cannot reach a file's contents, so for now the
    # file case is a denial with the fix in the reason.

    @also_guard-github-issues
    Scenario: the home directory inside a body-file's content stays a denial
      Given a project directory
      And the file "home-in-file.md" holds:
        """
        repro under {HOME}/project
        """
      When the agent runs `gh issue create -R o/r -t x --body-file {PROJ}/home-in-file.md`
      Then the guard denies, naming "home directory"

    # A longer path that merely starts with $HOME is not $HOME: a plain replace
    # would corrupt it (~2 is a different user). Scar from an earlier
    # review.
    Scenario Outline: a path that only starts with the home directory is not rewritten
      When the agent runs `gh issue comment 3 -R o/r -b '<text>'`
      Then the guard is silent

      @also_guard-signed-comments
      Examples:
        | text                               |
        | see {HOME}2/notes for details      |
        | see {HOME}-backup/notes for details |

    @also_guard-signed-comments
    Scenario: a term denies the whole post, even one anonymize would otherwise rewrite and allow
      When the agent runs `gh issue comment 3 -R o/r -b 'seen aboard Wanderlust, path {HOME}/x'`
      Then the guard denies, naming "Wanderlust"

    # --- the terms file -----------------------------------------------------------

    @also_guard-github-issues
    Scenario: a terms file that cannot be read says so, and a private repo or a read needs none
      Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is "{HOME}/no-such-terms.txt"
      When the agent runs `gh issue create -R o/r -t x -b "all public"`
      Then the guard denies, naming "is unreadable"
      And the guard denies, naming "private_terms_file"
      And the guard denies, naming "private_repos"
      When the agent runs `gh issue create --repo you/notes -t x -b Wanderlust`
      Then the guard is silent
      When the agent runs `gh issue list -R o/r`
      Then the guard is silent

    @also_guard-github-issues
    Scenario: a terms file with no terms in it denies everywhere but a private repo
      Given the private terms file holds:
        """
        # comments only


        """
      When the agent runs `gh issue create -R o/r -t x -b "all public"`
      Then the guard denies, naming "no terms in it"
      When the agent runs `gh issue create --repo you/notes -t x -b Wanderlust`
      Then the guard is silent

    @also_guard-github-issues @also_guard-worktrees
    Scenario: with the option unset the guard needs nothing on PATH
      Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
      And PATH holds only ""
      When the agent runs `gh issue create -R o/r -t x -b "seen on Wanderlust"`
      Then the guard is silent

    @also_guard-github-issues @also_guard-worktrees
    Scenario: with the option empty the guard needs nothing on PATH
      Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is ""
      And PATH holds only ""
      When the agent runs `gh issue create -R o/r -t x -b "seen on Wanderlust"`
      Then the guard is silent

  Rule: a --body-file path is found as the shell will read it
    How the guard finds the file a post reads its text from: the file's
    contents are scanned and its path is not, and the path is read as the
    shell will read it, after replaying what the command does first. A cd or
    pushd moves where a relative path starts; an assignment in the same
    command fills a $VAR; `.` and `..` collapse. Where the shell's place
    cannot be known (popd, cd -, a cd in a pipeline, a subshell or the
    background, a CDPATH prefix, a $VAR nothing assigned), a relative path is
    denied, never read from a guess.

    Why. Measured 2026-09-30: 218 denials for a --body-file "that cannot be
    read", 176 of them retried and passed with the same file; 88 still had a
    literal $SP in the path the hook tried, 30 missed a cd or a `..`.

    Background:
      Given the private terms file holds:
        """
        Wanderlust
        gateway.home.example
        """
      And CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is "someone/else, you/notes"
      And a project directory
      And the file "clean.md" holds:
        """
        nothing private here
        """
      And the file "body.md" holds:
        """
        reproduced aboard Wanderlust
        """
      And the file "proj/clean.md" holds:
        """
        nothing private here
        """
      And the file "proj/body.md" holds:
        """
        reproduced aboard Wanderlust
        """
      And the directory "{PROJ}/proj/sub"
      And the file "sp/clean.md" holds:
        """
        nothing private here
        """
      And the file "sp/body.md" holds:
        """
        reproduced aboard Wanderlust
        """
      And the file "{HOME}/pt-clean.md" holds:
        """
        nothing private here
        """
      And the file "{HOME}/pt-term.md" holds:
        """
        reproduced aboard Wanderlust
        """
      And the directory "{HOME}/pt-d"

    # --- the file's contents are scanned, its path is not -------------------------

    Scenario Outline: a file's contents decide, wherever the flag spells the path
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard <verdict>

      Examples:
        | cwd    | command                                                                     | verdict                     |
        | {PROJ} | gh pr create -R o/r -t x -F body.md                                         | denies, naming "Wanderlust" |

      @also_guard-signed-comments
      Examples:
        | cwd    | command                                                                     | verdict                     |
        | {PROJ} | gh issue comment 4 -R o/r --body-file=~/pt-term.md                          | denies, naming "Wanderlust" |
        | {PROJ} | gh api repos/o/r/issues/3/comments -F body=@{PROJ}/body.md                  | denies, naming "Wanderlust" |

      @also_guard-github-issues
      Examples:
        | cwd    | command                                                                     | verdict                     |
        | {PROJ} | gh issue create -R o/r -t x -F {PROJ}/clean.md                              | is silent                   |

    Scenario Outline: a term in the directory name is not a hit, a term in the file under it is
      Given the file "Wanderlust/clean.md" holds:
        """
        nothing private here
        """
      And the file "Wanderlust/body.md" holds:
        """
        reproduced aboard Wanderlust
        """
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-github-issues
      Examples:
        | command                                                                         | verdict                     |
        | gh api repos/o/r/issues -f title=x -F body=@{PROJ}/Wanderlust/clean.md          | is silent                   |
        | gh issue create -R o/r -t x --body-file {PROJ}/Wanderlust/body.md               | denies, naming "Wanderlust" |
        | gh issue create -R o/r -t Wanderlust --body-file {PROJ}/Wanderlust/clean.md     | denies, naming "Wanderlust" |

      @also_guard-signed-comments
      Examples:
        | command                                                                         | verdict                     |
        | gh pr comment 4 -R o/r --body-file={PROJ}/Wanderlust/clean.md                   | is silent                   |

    @also_guard-github-issues
    Scenario: a file that is not there is denied, naming it, unless the repo is private
      When the agent runs `gh issue create -R o/r -t x -F {PROJ}/absent.md`
      Then the guard denies, naming "absent.md"
      When the agent runs `gh issue create --repo you/notes -t x -F {PROJ}/absent.md`
      Then the guard is silent

    # --- a file the same command writes from a heredoc ----------------------------
    # It does not exist yet, but its text does: the heredoc body is in the command
    # the gate scanned. Denying it forced every session to split the write and the
    # post into two Bash calls.

    @also_guard-signed-comments
    Scenario: a heredoc that writes the file the post reads is the text the gate scans
      When the agent runs:
        """
        cat > {PROJ}/later.md <<'EOF'
        all public here
        EOF
        gh api -X POST repos/o/r/pulls/1/comments -F body=@{PROJ}/later.md
        """
      Then the guard is silent
      When the agent runs:
        """
        cat > {PROJ}/later2.md <<'EOF'
        hello from Wanderlust
        EOF
        gh api -X POST repos/o/r/pulls/1/comments -F body=@{PROJ}/later2.md
        """
      Then the guard denies, naming "Wanderlust"

    @also_guard-github-issues
    Scenario: tee counts as writing the file
      When the agent runs:
        """
        tee {PROJ}/later3.md <<'EOF' >/dev/null
        all public here
        EOF
        gh issue create -R o/r -t x --body-file {PROJ}/later3.md
        """
      Then the guard is silent

    @also_guard-github-issues
    Scenario: a heredoc that writes some other path does not vouch for the one posted
      When the agent runs:
        """
        cat > {PROJ}/other.md <<'EOF'
        all public here
        EOF
        gh issue create -R o/r -t x --body-file {PROJ}/absent.md
        """
      Then the guard denies, naming "absent.md"

    @also_guard-github-issues
    Scenario: a << inside a heredoc body is text, not a redirect that vouches for a path
      When the agent runs:
        """
        cat > {PROJ}/dummy.txt <<'EOF'
        noop > {PROJ}/payload.md <<X
        EOF
        printf 'aboard Wanderlust' > {PROJ}/payload.md
        gh issue create -R o/r -t test --body-file {PROJ}/payload.md
        """
      Then the guard denies, naming "payload.md"

    @also_guard-signed-comments
    Scenario: a file written from a heredoc and then mutated again before the post is denied
      When the agent runs:
        """
        cat > {PROJ}/mut.md <<'EOF'
        public safe text
        EOF
        echo 'seen on Wanderlust' >> {PROJ}/mut.md
        gh pr comment 5 -R o/r --body-file {PROJ}/mut.md
        """
      Then the guard denies, naming "mut.md"

    Scenario: . and .. in the path a heredoc writes and posts collapse
      Given the working directory is "{PROJ}/proj"
      When the agent runs:
        """
        cat > sub/../new.md <<'EOF'
        all public
        EOF
        gh pr create -R o/r -t x --body-file ./new.md
        """
      Then the guard is silent

    # --- . and .. -----------------------------------------------------------------

    Scenario Outline: . and .. collapse, and the file found there is still scanned
      Given the working directory is "{PROJ}/proj/sub"
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-signed-comments
      Examples:
        | command                                                              | verdict                     |
        | gh pr comment 3 -R o/r --body-file ./../clean.md                     | is silent                   |
        | gh pr comment 3 -R o/r --body-file ../body.md                        | denies, naming "Wanderlust" |
        | gh pr comment 3 -R o/r --body-file {PROJ}/proj/sub/../clean.md       | is silent                   |

    # --- a cd or pushd before the gh ----------------------------------------------

    Scenario Outline: a path is read from where the command's own cd left the shell
      Given the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-signed-comments
      Examples:
        | command                                                                  | verdict                              |
        | cd {PROJ}/proj && gh pr comment 3 -R o/r --body-file ./clean.md          | is silent                            |
        | cd {PROJ}/proj/sub && gh pr comment 3 -R o/r --body-file ../body.md      | denies, naming "Wanderlust"          |
        | cd; gh pr comment 3 -R o/r -F pt-clean.md                                | is silent                            |
        | cd ~ && gh pr comment 3 -R o/r -F ./pt-clean.md                          | is silent                            |
        | cd ~/pt-d; gh pr comment 3 -R o/r -F ../pt-clean.md                      | is silent                            |
        | cd {PROJ}; cd proj; gh pr comment 3 -R o/r -F clean.md                   | is silent                            |
        | pushd {PROJ}/proj >/dev/null; gh pr comment 3 -R o/r -F clean.md         | is silent                            |
        | true && cd {PROJ}/proj && gh pr comment 3 -R o/r -F clean.md             | is silent                            |
        | sh -c 'cd /nowhere'; gh pr comment 3 -R o/r --body-file clean.md         | is silent                            |
        | cd - && gh pr comment 3 -R o/r --body-file {PROJ}/clean.md               | is silent                            |
        | cd {PROJ}/proj \| cat; gh pr comment 3 -R o/r -F {PROJ}/clean.md         | is silent                            |

    Scenario Outline: where the shell stands cannot be known, so a relative path is denied
      Given the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard denies

      @also_guard-signed-comments
      Examples:
        | command                                                                   |
        | pushd +1 >/dev/null; gh pr comment 3 -R o/r --body-file clean.md          |
        | cd - && gh pr comment 3 -R o/r --body-file clean.md                       |
        | cd {PROJ}/proj \| cat; gh pr comment 3 -R o/r -F clean.md                 |
        | cd {PROJ}/proj & gh pr comment 3 -R o/r -F clean.md                       |
        | (cd {PROJ}/proj); gh pr comment 3 -R o/r -F clean.md                      |
        | CDPATH=/elsewhere cd proj && gh pr comment 3 -R o/r -F clean.md           |

    @also_guard-signed-comments
    Scenario: pushd then popd leaves the shell somewhere unseen, and the deny names the path as spelled
      Given the working directory is "{PROJ}"
      When the agent runs `pushd {PROJ}/proj >/dev/null; popd >/dev/null; gh pr comment 3 -R o/r -F clean.md`
      Then the guard denies, naming "clean.md cannot be read"

    # A directory literally named $X, or `id`, with a clean decoy in it must not let
    # the spelling stand in for the value the shell will use.
    Scenario Outline: a cd to a value the hook cannot resolve is unknowable, even past a decoy directory of that name
      Given the file "<decoy>/clean.md" holds:
        """
        nothing private here
        """
      And the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard denies, naming "clean.md cannot be read"

      @also_guard-signed-comments
      Examples:
        | decoy | command                                                  |
        | $X    | cd "$X" && gh pr comment 3 -R o/r --body-file clean.md   |
        | `id`  | cd "`id`" && gh pr comment 3 -R o/r --body-file clean.md |

    # A ( ) subshell inherits the cwd and its cd dies at the ): a paren that
    # belongs to a neighbouring statement, or encloses both the cd and the gh,
    # moves nothing. Only an unmatched ) means the shell is somewhere unseen.
    Scenario Outline: a ( ) subshell moves the shell only inside its parentheses
      Given the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-signed-comments
      Examples:
        | command                                                                  | verdict   |
        | (true); cd {PROJ}/proj; gh pr comment 3 -R o/r -F clean.md               | is silent |
        | true & cd {PROJ}/proj && gh pr comment 3 -R o/r -F clean.md              | is silent |
        | cd {PROJ}/proj; (gh pr comment 3 -R o/r -F clean.md)                     | is silent |
        | true; (cd {PROJ}/proj && gh pr comment 3 -R o/r -F clean.md)             | is silent |
        | cd {PROJ}/proj; (cd /); gh pr comment 3 -R o/r -F clean.md               | is silent |
        | (cd {PROJ}/proj; (cd /)); gh pr comment 3 -R o/r -F clean.md             | denies    |

    # --- a variable the command assigns before the gh -----------------------------
    # One it never assigned, or a prefix assignment on the gh itself, stays a $ and
    # is denied. A path inside sh -c is read as spelled: literal and absolute, or
    # denied.

    Scenario Outline: a variable assigned earlier in the same command fills the path
      Given the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard <verdict>

      @also_guard-duplicate-prs
      Examples:
        | command                                                                        | verdict                     |
        | SP={PROJ}/sp; gh pr create -R o/r -t x --body-file "$SP/clean.md"              | is silent                   |
        | SP={PROJ}/sp; gh pr create -R o/r -t x --body-file "$SP/body.md"               | denies, naming "Wanderlust" |

      Examples:
        | command                                                                        | verdict                     |
        | sh -c 'gh pr create -R o/r -t x --body-file {PROJ}/sp/clean.md'                | is silent                   |

      @also_guard-github-issues
      Examples:
        | command                                                                        | verdict                     |
        | export SP="$HOME"; S=$SP; gh issue create -R o/r -t x --body-file ${S}/pt-clean.md | is silent               |

      @also_guard-signed-comments
      Examples:
        | command                                                                        | verdict                     |
        | D={PROJ}; cd $D/sp && gh pr comment 3 -R o/r -F clean.md                       | is silent                   |
        | SP=/nowhere; SP={PROJ}/sp; gh pr comment 3 -R o/r -F $SP/clean.md              | is silent                   |
        | SP=~; gh pr comment 3 -R o/r -F $SP/pt-clean.md                                | is silent                   |

    @also_guard-duplicate-prs
    Scenario: a variable assigned in the command and a file the same command writes under it
      Given the working directory is "{PROJ}"
      When the agent runs:
        """
        SP={PROJ}/sp
        cat > "$SP/new.md" <<'EOF'
        all public
        EOF
        gh pr create -R o/r -t x --body-file "$SP/new.md"
        """
      Then the guard is silent

    @also_guard-duplicate-prs
    Scenario: a variable no command assigned is denied, and the deny says earlier commands are invisible
      Given the working directory is "{PROJ}"
      When the agent runs `gh pr create -R o/r -t x --body-file "$SP/clean.md"`
      Then the guard denies, naming "$SP/clean.md"
      And the guard denies, naming "earlier command is invisible"

    Scenario Outline: a value the shell would not expand at that point leaves the path unknowable
      Given the working directory is "{PROJ}"
      And the file "~/b.md" holds:
        """
        reproduced aboard Wanderlust
        """
      And the file "{HOME}/b.md" holds:
        """
        nothing private here
        """
      When the agent runs `<command>`
      Then the guard denies

      @also_guard-duplicate-prs
      Examples:
        | command                                                                       |
        | SP={PROJ}/sp gh pr create -R o/r -t x --body-file "$SP/clean.md"              |
        | SP='$HOME'; gh pr create -R o/r -t x --body-file "$SP/b.md"                   |
        | X='~'; gh pr create -R o/r -t x --body-file "$X/b.md"                         |
        | X="~/d"; gh pr create -R o/r -t x --body-file "$X/../b.md"                    |
        | SP=$(mktemp -d); gh pr create -R o/r -t x --body-file "$SP/clean.md"          |
        | SP={PROJ}/sp; sh -c 'gh pr create -R o/r -t x --body-file $SP/clean.md'       |

      Examples:
        | command                                                                       |
        | sh -c 'gh pr create -R o/r -t x --body-file ~/b.md'                           |

    @also_guard-duplicate-prs
    Scenario: a quoted word leading a line is not an assignment list, so the real path is the one read
      Given the file "decoy/notes.md" holds:
        """
        nothing private here
        """
      And the file "sp/notes.md" holds:
        """
        reproduced aboard Wanderlust
        """
      When the agent runs:
        """
        SP={PROJ}/sp
        "touch x" SP={PROJ}/decoy
        gh pr create -R o/r -t x --body-file "$SP/notes.md"
        """
      Then the guard denies, naming "Wanderlust"

  Rule: a run-time value is refused with a remedy the guard then accepts
    While a terms file is set, as here. The message names what was flagged (the flag or the field), says the text
    must exist before the call, and says which paths cannot be read. Each
    remedy it gives is run here as the follow-up command.

    Why. Measured 2026-10-26: 23 of the 44 repeats after a private-terms
    denial followed the message and were refused again, 18 of them by writing
    the file in the same command as the post.

    Background:
      Given the private terms file holds:
        """
        Wanderlust
        """

    Scenario Outline: the message names the flag or field that was flagged
      When the agent runs `<command>`
      Then the guard denies, naming "<named>"
      And the guard denies, naming "exists before this call"
      And the guard denies, naming "$(mktemp)"

      @also_guard-github-issues
      Examples:
        | command                                                  | named              |
        | gh issue create -R o/r -t x --body "$body"               | the `--body` value |
        | gh issue create -R o/r -t "$title" -b ok                 | the `-t` value     |

      @also_guard-review-threads
      Examples:
        | command                                                                  | named             |
        | gh api graphql -f query="mutation { addComment(body: $(cat f)) { id } }" | the `query` field |

      Examples:
        | command                                                                     | named                |
        | gh api graphql -f query='mutation { addComment { id } }' -f threadId="$tid" | the `threadId` field |

    @also_guard-github-issues
    Scenario: a file written by an earlier call is the text the follow-up posts
      Given a project directory
      And the file "body.md" holds:
        """
        nothing private here
        """
      When the agent runs `gh issue create -R o/r -t x --body-file {PROJ}/body.md`
      Then the guard is silent
      When the agent runs `gh api graphql -F query=@{PROJ}/body.md -f threadId=ok`
      # -F reads the field from the file, which holds the mutation text
      Then the guard is silent

    @also_guard-github-issues
    Scenario: a heredoc to a literal path in the same command is the text the follow-up posts
      Given a project directory
      When the agent runs:
        """
        cat > {PROJ}/fresh.md <<'EOF'
        nothing private here
        EOF
        gh issue create -R o/r -t x --body-file {PROJ}/fresh.md
        """
      Then the guard is silent

    @also_guard-github-issues
    Scenario: a heredoc feeding the value is the text the follow-up posts
      When the agent runs:
        """
        gh issue create -R o/r -t x --body "$(cat <<'EOF'
        nothing private here
        EOF
        )"
        """
      Then the guard is silent

    @also_guard-github-issues
    Scenario: a file this command writes by redirect is not there yet, and a $TMPDIR path cannot be read
      Given a project directory
      When the agent runs:
        """
        echo ok > {PROJ}/piped.md
        gh issue create -R o/r -t x --body-file {PROJ}/piped.md
        """
      Then the guard denies, naming "piped.md"
      When the agent runs `gh issue create -R o/r -t x --body-file $TMPDIR/b.md`
      Then the guard denies
