@python
Feature: guard-private-terms
  The long tail of shapes a post takes, against the rule stated in
  guard-private-terms.feature: a private term is caught wherever the text
  travels (a flag value, a heredoc, an MCP field, another case), a repo in
  private_repos is never scanned, reads are never touched, and the gate is
  loud when it cannot see the text or the denylist. How a --body-file path is
  resolved is in guard-private-terms-body-file.feature.

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
      | gh pr comment 12 -R o/r -b"tested on Wanderlust"                     | Wanderlust           |
      | gh issue edit 3 -R o/r --body="host is gateway.home.example"         | gateway.home.example |
      | gh pr review 9 -R o/r --approve --body "ok from acct-4471"           | acct-4471            |
      | gh issue close 3 -R o/r -c "moved to Wanderlust log"                 | Wanderlust           |
      | gh pr merge 5 -R o/r --squash -b "tested on wanderlust"              | Wanderlust           |
      | make build && gh pr create -R o/r --title x --body "cf Wanderlust"   | Wanderlust           |
      | gh issue create -R o/r -t x -b Wander\\lust                          | Wanderlust           |
      | gh issue create -R o/r -t x -b 'Wander'"lust"                        | Wanderlust           |
      | gh issue create -R o/r -t x -b "ACCT-4471 again"                     | acct-4471            |
      | gh issue create -R o/r -t x -b "WANDERLUST"                          | Wanderlust           |

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

  Scenario: a dot in a term is a dot, not any character
    When the agent runs `gh issue create -R o/r -t x -b "gatewayXhomeXexample"`
    Then the guard is silent

  # --- MCP ----------------------------------------------------------------------

  Scenario Outline: an MCP tool's field is judged wherever it sits in the input
    When the agent calls MCP tool "<tool>" with input `<input>`
    Then the guard <verdict>

    Examples:
      | tool                                  | input                                                                                              | verdict   |
      | mcp__github__issue_write              | {"method":"create","owner":"o","repo":"r","title":"Wanderlust AIS"}                                | denies    |
      | mcp__github__create_pull_request_review | {"owner":"o","repo":"r","pullNumber":1,"event":"COMMENT","comments":[{"path":"a.ts","body":"acct-4471"}]} | denies    |
      | mcp__github__create_issue             | {"owner":"you","repo":"notes","title":"x","body":"Wanderlust"}                                      | is silent |

  Scenario: the home directory in an MCP body is rewritten to ~
    Given the private terms file holds:
      """
      {HOME}
      """
    When the agent calls MCP tool "mcp__github__add_issue_comment" with input `{"owner":"o","repo":"r","issue_number":3,"body":"repro under {HOME}/project"}`
    Then the guard allows, rewriting the input field "body" to "repro under ~/project"

  # --- gh api -------------------------------------------------------------------

  Scenario Outline: a gh api write is judged, a read is not
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                                                   | verdict   |
      | gh api -X PATCH repos/o/r/issues/3 -f body=gateway.home.example                           | denies    |
      | gh api repos/o/r/pulls/3/reviews -f event=COMMENT -f body="acct-4471"                     | denies    |
      | gh api repos/o/r/issues --jq ".[].title"                                                  | is silent |
      | gh api graphql -f query='{ repository(owner:"o",name:"r"){ issue(number:3){ title } } }'  | is silent |
      | gh api repos/you/notes/issues -f title=x -f body=Wanderlust                               | is silent |

  # --- which repo a post targets ------------------------------------------------

  Scenario Outline: a repo named on the command line is never scanned when it is listed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                                 |
      | gh issue create --repo you/notes -t x -b 'aboard Wanderlust'            |
      | gh issue create -R You/Notes -t x -b Wanderlust                         |
      | gh issue comment 3 --repo=https://github.com/you/notes -b Wanderlust    |
      | GH_REPO=you/notes gh issue create -t x -b Wanderlust                    |

  Scenario: with private_repos empty, nothing is private
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS is ""
    When the agent runs `gh issue create -R you/notes -t x -b Wanderlust`
    Then the guard denies, naming "Wanderlust"

  Scenario Outline: with no repo named, the origin of the working directory decides, unless the command moves
    Given a clone of "git@github.com:you/notes.git" at "{TMP}/private" on branch "main"
    And a clone of "https://github.com/mark-brannan/colregs.git" at "{TMP}/public" on branch "main"
    And the directory "{TMP}/nogit"
    And the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | cwd              | command                                                                                                              | verdict   |
      | {TMP}/private    | gh issue create -t x -b "aboard Wanderlust"                                                                          | is silent |
      | {TMP}/public     | gh issue create -t x -b Wanderlust                                                                                   | denies    |
      | {TMP}/nogit      | gh issue create -t x -b Wanderlust                                                                                   | denies    |
      | {TMP}/private    | cd {TMP}/public && gh issue create -t x -b Wanderlust                                                                | denies    |
      | {TMP}/private    | gh issue comment https://github.com/o/r/issues/1 -b Wanderlust                                                      | denies    |
      | {TMP}/private    | gh pr comment o/r#1 -b Wanderlust                                                                                    | denies    |
      | {TMP}/public     | gh issue comment https://github.com/you/notes/issues/1 -b Wanderlust                                                 | is silent |
      | {TMP}/private    | gh api graphql -f query='mutation { addComment(input:{subjectId:"I_1", body:"from Wanderlust"}) { clientMutationId } }' | denies    |
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
      | gh issue create -R o/r -t "Ruling: Q-14" -b "Argument in mark-brannan/colregs requirements.md; see https://github.com/mark-brannan/colregs-engine/pull/25 and claude_prompts_scratch#3" |
      | gh pr merge 12 --squash --delete-branch                                                                                                                     |
      | echo "gh issue create --body hi"                                                                                                                            |
      | ls -la                                                                                                                                                      |

  Scenario: a Bash call with no command, and a tool this guard does not gate, are silent
    When the agent calls tool "Bash" with input `{}`
    Then the guard is silent
    When the agent calls tool "Read" with input `{"file_path": "/x"}`
    Then the guard is silent

  # --- the gate is loud when it cannot see --------------------------------------

  Scenario: a body from stdin with no heredoc to read is denied
    When the agent runs `cat notes.md | gh issue create -R o/r -t x -F -`
    Then the guard denies, naming "stdin"

  Scenario: a body from stdin is read from the heredoc that feeds it
    When the agent runs:
      """
      gh issue create -R o/r -t x -F - <<EOF
      all public
      EOF
      """
    Then the guard is silent

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

    Examples:
      | command                                                      | verdict                      |
      | gh pr comment 3 -R o/r -b 'Fixed in `abc123`, see `prose-budget`.' | is silent             |
      | gh issue create -R o/r -t x -b 'run $(date) yourself'        | is silent                    |
      | gh pr comment 3 -R o/r -b "Fixed in `git rev-parse HEAD`"    | denies                       |
      | gh pr comment 3 -R o/r -b 'Fixed on `Wanderlust`.'           | denies, naming "Wanderlust"  |

  # --- fail closed: a flag that looks like it carries text ----------------------

  Scenario: an unrecognised flag shaped like a body is refused, naming the flag
    When the agent runs `gh issue comment 3 -R o/r --response-body-file /tmp/x`
    Then the guard denies, naming "--response-body-file"
    And the guard denies, naming "doesn't recognise its shape"

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

  Scenario Outline: a path under the home directory is not posted text, when the denylist names the home directory
    Given the private terms file holds:
      """
      {HOME}
      """
    And the file "{HOME}/pt-scratch-body.md" holds:
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
      | cd {HOME}/worktrees/xyz && gh issue comment 3 -R o/r -b 'ready for review' |
      | gh issue create -R o/r -t x --body-file {HOME}/pt-scratch-body.md      |
      | gh issue comment 3 -R o/r --comment-file {HOME}/pt-scratch-comment.md  |

  Scenario: a term in a --comment-file's content still denies
    Given a project directory
    And the file "comment-term.md" holds:
      """
      seen aboard Wanderlust
      """
    When the agent runs `gh issue comment 3 -R o/r --comment-file {PROJ}/comment-term.md`
    Then the guard denies, naming "Wanderlust"

  # --- the home directory: a sanitization job, until it is not one --------------

  Scenario: the home directory inside a body-file's content stays a denial
    Given the private terms file holds:
      """
      {HOME}
      """
    And a project directory
    And the file "home-in-file.md" holds:
      """
      repro under {HOME}/project
      """
    When the agent runs `gh issue create -R o/r -t x --body-file {PROJ}/home-in-file.md`
    Then the guard denies, naming "{HOME}"

  # A longer path that merely starts with $HOME is not $HOME: a plain replace
  # would corrupt it (~2 is a different user). Scars from PR review on
  # dotfiles#184, rounds 1 and 2.
  Scenario Outline: a path that only starts with the home directory is not rewritten
    Given the private terms file holds:
      """
      {HOME}
      """
    When the agent runs `gh issue comment 3 -R o/r -b '<text>'`
    Then the guard denies, naming "{HOME}"

    Examples:
      | text                               |
      | see {HOME}2/notes for details      |
      | see {HOME}-backup/notes for details |

  Scenario: fixing the home directory alone would not make the post safe
    Given the private terms file holds:
      """
      {HOME}
      Wanderlust
      """
    When the agent runs `gh issue comment 3 -R o/r -b 'seen aboard Wanderlust, path {HOME}/x'`
    Then the guard denies, naming "Wanderlust"

  # --- the terms file -----------------------------------------------------------

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

  Scenario: a terms file with no terms in it denies everywhere but a private repo
    Given the private terms file holds:
      """
      # comments only


      """
    When the agent runs `gh issue create -R o/r -t x -b "all public"`
    Then the guard denies, naming "no terms in it"
    When the agent runs `gh issue create --repo you/notes -t x -b Wanderlust`
    Then the guard is silent

  Scenario: with the option unset the guard needs nothing on PATH
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is unset
    And PATH holds only ""
    When the agent runs `gh issue create -R o/r -t x -b "seen on Wanderlust"`
    Then the guard is silent

  Scenario: with the option empty the guard needs nothing on PATH
    Given CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE is ""
    And PATH holds only ""
    When the agent runs `gh issue create -R o/r -t x -b "seen on Wanderlust"`
    Then the guard is silent
