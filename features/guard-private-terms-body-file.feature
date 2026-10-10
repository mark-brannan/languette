@python
Feature: guard-private-terms
  How the guard finds the file a post reads its text from, against the rule
  stated in guard-private-terms.feature: the file's contents are scanned and
  its path is not, and the path is read as the shell will read it, after
  replaying what the command does first. A cd or pushd moves where a relative
  path starts; an assignment in the same command fills a $VAR; `.` and `..`
  collapse. Where the shell's place cannot be known (popd, cd -, a cd in a
  pipeline, a subshell or the background, a CDPATH prefix, a $VAR nothing
  assigned), a relative path is denied, never read from a guess.

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
