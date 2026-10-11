@python
Feature: guard-private-terms
  Text bound for a public GitHub repo is checked against the user's private
  terms file, wherever the text travels: a flag value, a heredoc, a file, an
  MCP field. The file is the private_terms_file option. Without one the guard
  is inert; with one that cannot be read it is closed. The standalone suite,
  tests/guard-private-terms.test.sh, walks the long tail of shell shapes.

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
      | tool                                           | input                                                                     | verdict   |
      | mcp__github__create_issue                      | {"owner":"o","repo":"r","title":"t","body":"Wanderlust"}                  | denies    |
      | mcp__plugin_github_github__add_issue_comment   | {"owner":"o","repo":"r","body":"on gateway.home.example"}                 | denies    |
      | mcp__github__add_reply_to_pull_request_comment | {"owner":"o","repo":"r","pullNumber":1,"commentId":9,"body":"Wanderlust"} | denies    |
      | mcp__github__update_issue_comment              | {"owner":"o","repo":"r","commentId":9,"body":"on gateway.home.example"}   | denies    |
      | mcp__github__create_issue                      | {"owner":"o","repo":"r","title":"t","body":"clean"}                       | is silent |
      | mcp__github__get_issue                         | {"owner":"o","repo":"r","body":"Wanderlust"}                              | is silent |

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

  Rule: the long tail of shapes a post takes
    A private term is caught wherever the text travels (a flag value, a
    heredoc, an MCP field, another case), a repo in private_repos is never
    scanned, reads are never touched, and the gate is loud when it cannot see
    the text or the denylist. These scenarios walk the long tail of shapes
    those promises take.

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
        | {PROJ} | gh issue comment 4 -R o/r --body-file=~/pt-term.md                          | denies, naming "Wanderlust" |
        | {PROJ} | gh issue create -R o/r -t x -F {PROJ}/clean.md                              | is silent                   |
        | {PROJ} | gh api repos/o/r/issues/3/comments -F body=@{PROJ}/body.md                  | denies, naming "Wanderlust" |

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

      Examples:
        | command                                                                         | verdict                     |
        | gh pr comment 4 -R o/r --body-file={PROJ}/Wanderlust/clean.md                   | is silent                   |
        | gh api repos/o/r/issues -f title=x -F body=@{PROJ}/Wanderlust/clean.md          | is silent                   |
        | gh issue create -R o/r -t x --body-file {PROJ}/Wanderlust/body.md               | denies, naming "Wanderlust" |
        | gh issue create -R o/r -t Wanderlust --body-file {PROJ}/Wanderlust/clean.md     | denies, naming "Wanderlust" |

    Scenario: a file that is not there is denied, naming it, unless the repo is private
      When the agent runs `gh issue create -R o/r -t x -F {PROJ}/absent.md`
      Then the guard denies, naming "absent.md"
      When the agent runs `gh issue create --repo you/notes -t x -F {PROJ}/absent.md`
      Then the guard is silent

    # --- a file the same command writes from a heredoc ----------------------------
    # It does not exist yet, but its text does: the heredoc body is in the command
    # the gate scanned. Denying it forced every session to split the write and the
    # post into two Bash calls.

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

    Scenario: tee counts as writing the file
      When the agent runs:
        """
        tee {PROJ}/later3.md <<'EOF' >/dev/null
        all public here
        EOF
        gh issue create -R o/r -t x --body-file {PROJ}/later3.md
        """
      Then the guard is silent

    Scenario: a heredoc that writes some other path does not vouch for the one posted
      When the agent runs:
        """
        cat > {PROJ}/other.md <<'EOF'
        all public here
        EOF
        gh issue create -R o/r -t x --body-file {PROJ}/absent.md
        """
      Then the guard denies, naming "absent.md"

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

      Examples:
        | command                                                                   |
        | pushd +1 >/dev/null; gh pr comment 3 -R o/r --body-file clean.md          |
        | cd - && gh pr comment 3 -R o/r --body-file clean.md                       |
        | cd {PROJ}/proj \| cat; gh pr comment 3 -R o/r -F clean.md                 |
        | cd {PROJ}/proj & gh pr comment 3 -R o/r -F clean.md                       |
        | (cd {PROJ}/proj); gh pr comment 3 -R o/r -F clean.md                      |
        | CDPATH=/elsewhere cd proj && gh pr comment 3 -R o/r -F clean.md           |

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

      Examples:
        | command                                                                        | verdict                     |
        | SP={PROJ}/sp; gh pr create -R o/r -t x --body-file "$SP/clean.md"              | is silent                   |
        | SP={PROJ}/sp; gh pr create -R o/r -t x --body-file "$SP/body.md"               | denies, naming "Wanderlust" |
        | export SP="$HOME"; S=$SP; gh issue create -R o/r -t x --body-file ${S}/pt-clean.md | is silent               |
        | D={PROJ}; cd $D/sp && gh pr comment 3 -R o/r -F clean.md                       | is silent                   |
        | SP=/nowhere; SP={PROJ}/sp; gh pr comment 3 -R o/r -F $SP/clean.md              | is silent                   |
        | SP=~; gh pr comment 3 -R o/r -F $SP/pt-clean.md                                | is silent                   |
        | sh -c 'gh pr create -R o/r -t x --body-file {PROJ}/sp/clean.md'                | is silent                   |

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

      Examples:
        | command                                                                       |
        | SP={PROJ}/sp gh pr create -R o/r -t x --body-file "$SP/clean.md"              |
        | SP='$HOME'; gh pr create -R o/r -t x --body-file "$SP/b.md"                   |
        | X='~'; gh pr create -R o/r -t x --body-file "$X/b.md"                         |
        | X="~/d"; gh pr create -R o/r -t x --body-file "$X/../b.md"                    |
        | SP=$(mktemp -d); gh pr create -R o/r -t x --body-file "$SP/clean.md"          |
        | SP={PROJ}/sp; sh -c 'gh pr create -R o/r -t x --body-file $SP/clean.md'       |
        | sh -c 'gh pr create -R o/r -t x --body-file ~/b.md'                           |

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
