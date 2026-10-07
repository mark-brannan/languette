@python @shell
Feature: guard-recursive-delete
  Recursive rm and find -delete are denied unless every target is a generated
  directory or the agent's own area. The working directory is {HOME}/project
  unless a scenario says otherwise.

  # The README's table under the promise is generated from these rows
  # (python3 tests/readme_table.py). The two known gaps: deletion from inside
  # an interpreter is out of scope, and a script's contents are never read.
  @table
  Scenario Outline: the promise, as the README's table shows it
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                             | verdict                                           | why                              |
      | rm -rf build                        | denies, naming "is none of those"                 | not an allowlisted generated dir |
      | rm -rf node_modules                 | is silent                                         | allowlisted                      |
      | rm -rf "$DIR"                       | denies, naming "variable or command substitution" | unresolvable word; loud          |
      | rm -rf dist{,2}                     | denies, naming "glob or brace expansion"          | brace expansion unresolved; loud |
      | sh -c "rm -rf build"                | denies, naming "rm -r build"                      | nested text scanned              |
      | find build -delete                  | denies, naming "is none of those"                 | rule covers find -delete         |
      | python3 -c "shutil.rmtree('build')" | is silent                                         | no rule; silent (known gap)      |
      | ./cleanup.sh                        | is silent                                         | no rule; silent (known gap)      |

  Scenario Outline: a recursive rm of a directory that is not generated is denied, however the flag is spelled
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                      | verdict   | note                                            |
      | rm -rf examples              | denies    | a misc directory in a repo is the user's        |
      | rm -r ./docs                 | denies    |                                                 |
      | rm -rf "$HOME/foo"           | denies    |                                                 |
      | rm -rf ~/Downloads           | denies    |                                                 |
      | rm -rf *                     | denies    |                                                 |
      | rm -rf dist/*                | denies    | a glob could name anything                      |
      | rm -rf dist/../src           | denies    | a .. segment steps out                          |
      | rm -Rf src                   | denies    | any recursive spelling                          |
      | rm -rf public                | denies    |                                                 |
      | rm -rf .                     | denies    |                                                 |
      | rm -rf ~                     | denies    | never $HOME itself                              |
      | cd x && rm -rf y             | denies    | a relative target after a cd cannot be resolved |
      | sudo rm -rf /srv/z           | denies    |                                                 |
      | timeout 5 rm -r a            | denies    |                                                 |
      | rm -rf node_modules examples | denies    | one target the user's is enough                 |
      | rm --recursive build         | denies    | --recursive spelled out                         |
      | rm --rec build               | denies    | GNU long-option prefix of --recursive           |
      | rm --r build                 | denies    | the shortest prefix GNU takes                   |
      | rm --rec node_modules        | is silent | the prefix spelling on an allowlisted dir       |
      | rm -rf ..                    | denies    | a bare .. segment                               |
      | rm -rf ~someone/foo          | denies    | only a leading ~/ is understood                 |
      | rm -rf -- examples           | denies    |                                                 |
      | rm -rf "$(pwd)/examples"     | denies    | command substitution                            |
      | rm -rf `pwd`/examples        | denies    | backtick substitution                           |

  Scenario: a recursive rm on a later line is still seen
    When the agent runs:
      """
      echo start
      rm -rf examples
      """
    Then the guard denies

  Scenario Outline: one target that is not Claude's denies the command, whichever side of an allowed target it stands
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                         | verdict                                           | note                                  |
      | rm -rf dist "$X"                | denies, naming "variable or command substitution" | allowed, then unresolved              |
      | rm -rf "$X" dist                | denies, naming "variable or command substitution" | unresolved, then allowed              |
      | rm -rf dist examples            | denies, naming "is none of those"                 | allowed, then a foreign path          |
      | rm -rf examples dist            | denies, naming "is none of those"                 | foreign path, then allowed            |
      | rm -rf dist /tmp/ok "$X"        | denies, naming "variable or command substitution" | two allowed, then unresolved          |
      | rm -rf dist dist/* node_modules | denies, naming "glob or brace expansion"          | allowed, a glob, allowed              |
      | find dist /home -delete         | denies, naming "is none of those"                 | find start paths follow the same rule |
      | rm -rf dist node_modules        | is silent                                         | every target allowed                  |

  Scenario Outline: rm reached through another command is still rm
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                       | note                                           |
      | find ~/precious -mindepth 1 -exec rm -rf {} + |                                                |
      | find . -name x -type d -exec rm -rf {} \;     |                                                |
      | find ~/precious -type f \| xargs rm -rf       | rm reached through xargs has no visible target |
      | for i in 1; do rm -rf ~/precious; done        |                                                |
      | if true; then rm -rf examples; fi             |                                                |
      | time rm -rf examples                          |                                                |
      | chronic rm -rf examples                       | an unknown wrapper                             |
      | find examples -type f -delete                 |                                                |
      | rm -rf node_modules & rm -rf examples         | after &                                        |
      | (cd sub && rm -rf examples)                   | in a subshell                                  |
      | { rm -rf examples; }                          | in a brace group                               |

  Scenario Outline: quoting and escapes do not hide a recursive rm
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | cwd                                 | command                                | note                                            |
      | /tmp                                | rm -rf "/home/user/private dir"        | a quoted path with a space, even from /tmp      |
      | {HOME}/.local/state/claude-tmpdir/x | rm -rf "my dir"                        | a quoted path with a space, from the scratchpad |
      | {HOME}/project                      | rm -rf examples "a b"                  |                                                 |
      | {HOME}/project                      | sh -c 'rm -rf examples'                |                                                 |
      | {HOME}/project                      | bash -c "cd ~/proj && rm -rf examples" |                                                 |
      | {HOME}/project                      | eval "rm -rf examples"                 |                                                 |
      | {HOME}/project                      | ls \| xargs -I{} sh -c 'rm -rf {}'     |                                                 |
      | {HOME}/project                      | r\m -rf examples                       | an escaped command word is still rm             |
      | {HOME}/project                      | \rm -rf examples                       | the alias bypass                                |
      | {HOME}/project                      | 'rm' -rf examples                      | a quoted command word                           |
      | {HOME}/project                      | rm -rf node_modules{,/../examples}     | a brace expansion glued to an allowed name      |
      | {HOME}/project                      | rm -rf {examples,docs}                 | a brace list, no visible target                 |
      | {HOME}/project                      | rm -rf my\ dir                         | an escaped space in the target                  |

  Scenario: a line continuation does not split rm from its target
    When the agent runs:
      """
      rm -rf \
      examples
      """
    Then the guard denies

  Scenario Outline: a target is judged where it lands, not by its name
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | cwd                                 | command                         | note                                                      |
      | /tmp                                | cd ~/project && rm -rf examples | a cd moves the target out of /tmp                         |
      | {HOME}/.local/state/claude-tmpdir/x | cd ~/project; rm -rf examples   | a cd moves the target out of the scratchpad               |
      | {HOME}                              | rm -rf .                        | the cwd is $HOME                                          |
      | {HOME}/project                      | rm -rf ~/dist                   | a generated name directly under $HOME is just a directory |
      | {HOME}                              | rm -rf coverage                 | the same, reached from $HOME                              |
      | {HOME}/project                      | rm -rf /dist                    | a generated name directly under /                         |
      | /                                   | rm -rf coverage                 | the same, reached from /                                  |

  Scenario Outline: generated directories, the agent's own areas, and anything that is not a recursive rm
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | cwd                | command                                              | verdict   | note                                            |
      | {HOME}/project     | rm -rf dist                                          | is silent |                                                 |
      | {HOME}/project     | rm -rf ./dist coverage                               | is silent |                                                 |
      | {HOME}/project     | rm -rf dist/assets                                   | is silent | a component of the path is allowlisted          |
      | {HOME}/project     | rm -rf -- dist                                       | is silent |                                                 |
      | /opt/proj          | rm -rf dist                                          | is silent | a generated name nested under /                 |
      | {HOME}/project     | rm -rf {HOME}/.local/state/claude-tmpdir/anything    | is silent | the scratchpad                                  |
      | {HOME}/project     | rm -rf /tmp/whatever                                 | is silent | /tmp is the agent's                             |
      | {HOME}/project     | rm -rf ~/.claude/worktrees/foo                       | is silent | an agent worktree                               |
      | {HOME}/project     | rm foo.txt                                           | is silent | not recursive                                   |
      | {HOME}/project     | rm -f a b                                            | is silent |                                                 |
      | {HOME}/project     | for f in *.log; do rm "$f"; done                     | is silent |                                                 |
      | {HOME}/project     | git commit -m "hooks: block rm -rf on examples"      | is silent | prose in a commit message                       |
      | {HOME}/project     | echo "do not rm -rf examples"                        | is silent | prose that names the command is not the command |
      | {HOME}/project     | git rm -r examples                                   | is silent | rm is git's subcommand here                     |
      | {HOME}/project     | yadm rm -r examples                                  | is silent |                                                 |
      | {HOME}/project     | git rm -r --cached examples && git commit -m x       | is silent |                                                 |
      | {HOME}/project     | docker rm -f mycontainer                             | is silent |                                                 |
      | {HOME}/project/sub | rm -rf dist                                          | is silent | from a deeper cwd                               |
      | {HOME}/project/sub | rm -rf {HOME}/.claude/worktrees/x                    | is silent | an absolute worktree, from a deeper cwd         |
      | {HOME}/project     | rm -rf node_modules 2>/dev/null                      | is silent | a redirection is not a target                   |
      | {HOME}/project     | rm -rf node_modules > /dev/null 2>&1                 | is silent |                                                 |
      | {HOME}/project     | find . -name "*.orig" -exec rm -f {} +               | is silent | find -exec rm without -r                        |
      | {HOME}/project     | find dist -name "*.map" -delete                      | is silent | find -delete on a generated dir                 |
      | {HOME}/project     | echo "it's fine" && echo "don't rm -rf examples"     | is silent | apostrophes in quoted prose                     |
      | {HOME}/project     | cd ~/project && rm -rf {HOME}/project/node_modules   | is silent | a cd does not move an absolute target           |
      | {HOME}/project     | rm -rf /tmp/my\ dir                                  | is silent | an escaped space inside /tmp                    |
      | {HOME}/project     | sh -c 'rm -rf node_modules'                          | is silent |                                                 |
      | {HOME}/project     | grep -rn "rm -rf" .                                  | is silent | grep's pattern is prose                         |
      | {HOME}/project     | grep -rn "rm -rf examples" . && git grep "rm -rf ."  | is silent |                                                 |
      | {HOME}/project     | echo rm -rf examples                                 | is silent | echo prints, unquoted too                       |
      | {HOME}/project     | printf "%s\\n" "rm -rf examples" > notes.txt         | is silent |                                                 |
      | {HOME}/project     | echo "rm -rf examples" \| sh                         | denies    | prose piped into a shell is executed            |
      | {HOME}/project     | echo rm -rf examples \| bash                         | denies    |                                                 |
      | {HOME}/project     | python3 -c "import os; os.system('rm -rf examples')" | denies    | an unknown consumer's quoted text is scanned    |
      | {HOME}/project     | mytool --run "rm -rf examples"                       | denies    | an unknown consumer's quoted text is scanned    |

  Scenario: a heredoc body is not run
    When the agent runs:
      """
      cat <<EOF
      never run rm -rf x
      EOF
      """
    Then the guard is silent

  Scenario: a command substitution in an unquoted heredoc body is run
    When the agent runs:
      """
      cat <<EOF
      $(rm -rf examples)
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a command substitution in a <<- heredoc body, tab-indented, is run
    When the agent runs:
      """
      cat <<-EOF
      	today is $(rm -rf examples)
      	EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a backtick substitution in an unquoted heredoc body is run
    When the agent runs:
      """
      cat <<EOF
      `rm -rf examples`
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a heredoc opener inside a kept substitution does not hide the lines after the heredoc
    When the agent runs:
      """
      cat <<EOF
      $(cat <<X)
      EOF
      rm -rf examples
      X
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a single-quoted heredoc delimiter makes the body text, substitutions too
    When the agent runs:
      """
      cat <<'EOF'
      $(rm -rf examples) `rm -rf examples`
      EOF
      """
    Then the guard is silent

  Scenario: a double-quoted heredoc delimiter makes the body text, substitutions too
    When the agent runs:
      """
      cat <<"EOF"
      $(rm -rf examples) `rm -rf examples`
      EOF
      """
    Then the guard is silent

  Scenario: an escaped $ in an unquoted heredoc body is text
    When the agent runs:
      """
      cat <<EOF
      \$(rm -rf examples)
      EOF
      """
    Then the guard is silent

  Scenario: a partially quoted heredoc delimiter still closes on its unquoted word
    When the agent runs:
      """
      cat <<E"O"F
      hi
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a partially quoted heredoc delimiter makes the body text
    When the agent runs:
      """
      cat <<E"O"F
      $(rm -rf examples)
      EOF
      """
    Then the guard is silent

  Scenario: a backslash-quoted heredoc delimiter makes the body text
    When the agent runs:
      """
      cat <<\EOF
      $(rm -rf examples)
      EOF
      """
    Then the guard is silent

  Scenario: the rest of a heredoc opener line is run
    When the agent runs:
      """
      cat <<EOF && rm -rf examples
      hi
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a here-string is not a heredoc opener
    When the agent runs:
      """
      cat <<<foo; rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: two heredocs on one line take their bodies in turn, the second unquoted
    When the agent runs:
      """
      cat <<A <<B
      a
      A
      $(rm -rf examples)
      B
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: two heredocs on one line take their bodies in turn, the second quoted
    When the agent runs:
      """
      cat <<A <<'B'
      a
      A
      $(rm -rf examples)
      B
      """
    Then the guard is silent

  # On the shfmt rung run.py's parse check denies it first (guard-unparsable).
  @no_shfmt
  Scenario: a heredoc that never closes is read as commands
    When the agent runs:
      """
      cat <<EOF
      $(rm -rf examples)
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a heredoc inside bash -c keeps its substitutions
    When the agent runs:
      """
      bash -c 'cat <<EOF
      $(rm -rf examples)
      EOF'
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a nested substitution in an unquoted heredoc body is run
    When the agent runs:
      """
      cat <<EOF
      $(echo $(rm -rf examples) ")")
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a quoted heredoc, then a <<- heredoc with a backtick substitution
    When the agent runs:
      """
      cat <<'A'
      $(rm -rf src)
      A
      cat <<-B
      	`rm -rf examples`
      	B
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a case pattern's ) does not close a substitution in a heredoc body
    When the agent runs:
      """
      cat <<EOF
      $(case x in a) rm -rf examples;; esac)
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a ) in a comment does not close a substitution in a heredoc body
    When the agent runs:
      """
      cat <<EOF
      $(echo hi # )
      rm -rf examples)
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a ) inside nested quotes does not close a substitution in a heredoc body
    When the agent runs:
      """
      cat <<EOF
      $(echo "$(echo ")")" ; rm -rf examples)
      EOF
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: an apostrophe kept from a heredoc body does not hide the commands after it
    When the agent runs:
      """
      cat <<EOF
      $(echo "it's") don't
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a quoted heredoc delimiter with a dash closes only on the whole word
    When the agent runs:
      """
      cat <<'END-X'
      END
      rm -rf examples
      END-X
      """
    Then the guard is silent

  Scenario: an escaped blank before # in a kept substitution does not hide the commands after it
    When the agent runs:
      """
      cat <<EOF
      $(echo a\ #'
      ')
      echo hi
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  # On the shfmt rung run.py's parse check denies it first (guard-unparsable).
  @no_shfmt
  Scenario: an escaped ; before # in a kept backtick substitution does not hide the commands after it
    When the agent runs:
      """
      cat <<EOF
      `echo \;#'`
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: an escaped < before a second heredoc opener on a line
    When the agent runs:
      """
      cat <<\<<< EOF
      <
      echo it's
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "rm -r examples"

  Scenario Outline: a command substitution inside double quotes is run, though the words around it are prose
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                              | verdict                            | why                                         |
      | echo "$(rm -rf examples)"                            | denies, naming "rm -r examples"    | echo prints what rm left behind             |
      | git commit -m "msg: $(rm -rf examples)"              | denies, naming "rm -r examples"    | the message is prose; its substitution runs |
      | echo "$(echo "x"; rm -rf examples)"                  | denies, naming "rm -r examples"    | quotes nested inside the substitution       |
      | echo "a $(echo "$(rm -rf examples)") b"              | denies, naming "rm -r examples"    | a substitution inside a substitution        |
      | echo "$(rm -rf node_modules)"                        | is silent                          | an allowed target stays allowed             |
      | git commit -m "hooks: $(date) block rm -rf examples" | is silent                          | only the substitution is scanned, not prose |
      | echo '$(rm -rf examples)'                            | is silent                          | single quotes make it text                  |
      | echo "\$(rm -rf examples)"                           | is silent                          | an escaped $ is text                        |

  Scenario: a backtick substitution inside double quotes is run
    When the agent runs:
      """
      echo "today `rm -rf examples` again"
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: an escaped backtick inside a backtick substitution inside double quotes is run
    When the agent runs:
      """
      echo "`echo \`rm -rf examples\``"
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a substitution in an unquoted heredoc inside a quoted commit message is run
    When the agent runs:
      """
      git commit -m "$(cat <<EOF
      $(rm -rf examples)
      EOF
      )"
      """
    Then the guard denies, naming "rm -r examples"

  Scenario: a quoted heredoc inside a quoted commit message stays prose
    When the agent runs:
      """
      git commit -m "$(cat <<'EOF'
      hooks: block rm -rf examples, and $(rm -rf examples) too
      EOF
      )"
      """
    Then the guard is silent

  Scenario: a comment is not run
    When the agent runs:
      """
      # rm -rf examples would be bad
      ls
      """
    Then the guard is silent

  Scenario Outline: a target must be allowed where its symlinks lead, too
    Given the directory "{TMP}/real"
    And the symlink "{TMP}/escape" to "{HOME}"
    And the symlink "{TMP}/inside" to "{TMP}/real"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                       | verdict   | note                                      |
      | rm -rf {TMP}/escape/Documents | denies    | under /tmp by name, into $HOME by symlink |
      | rm -rf {TMP}/escape/          | denies    | a trailing slash follows the link         |
      | rm -rf {TMP}/inside/x         | is silent | a symlink under /tmp into /tmp            |
      | rm -rf {TMP}/real             | is silent |                                           |
      | rm -rf {TMP}/not/yet/here     | is silent | not there yet, still under /tmp           |

  Scenario Outline: the denial names what the agent ran
    When the agent runs `<command>`
    Then the guard denies, naming "<named>"

    Examples:
      | command                    | named                                 |
      | find build -delete         | `find build -delete` is blocked       |
      | find -name "*.log" -delete | `find -delete` is blocked             |
      | find b* -delete            | `find b* -delete` is blocked          |
      | find ~/Downloads -delete   | `find ~/Downloads -delete` is blocked |
      | rm -rf build               | `rm -r build` is blocked              |
      | find . -exec rm -rf {} +   | `rm -r` is blocked                    |

  Scenario Outline: LANGUETTE_RM_ALLOW adds to the built-in lists and never replaces them
    Given LANGUETTE_RM_ALLOW is <allow>
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | allow                   | command                           | verdict                           | note                                |
      | unset                   | rm -rf proj/build                 | denies, naming "is none of those" |                                     |
      | ""                      | rm -rf proj/build                 | denies, naming "is none of those" | empty is unset                      |
      | ""                      | rm -rf /tmp/ok                    | is silent                         | empty is unset, and says nothing    |
      | "build"                 | rm -rf proj/build                 | is silent                         |                                     |
      | "build"                 | rm -rf proj/build/sub             | is silent                         |                                     |
      | "build"                 | find proj/build -delete           | is silent                         |                                     |
      | "build:.next:out"       | rm -rf proj/.next                 | is silent                         | one of several names                |
      | "build:.next"           | rm -rf proj/examples              | denies, naming "is none of those" | names not listed stay denied        |
      | "build"                 | rm -rf proj/node_modules          | is silent                         | built-in names survive a value      |
      | "build"                 | rm -rf {HOME}/.claude/worktrees/x | is silent                         | built-in roots survive a value      |
      | "build"                 | rm -rf {HOME}/build               | denies, naming "is none of those" | an added name directly under $HOME  |
      | "/srv/agent-area"       | rm -rf /srv/agent-area/x          | is silent                         | an absolute path is added as a root |
      | "/srv/agent-area/"      | rm -rf /srv/agent-area/x          | is silent                         |                                     |
      | "/srv/agent-area"       | rm -rf /srv/other/x               | denies, naming "is none of those" |                                     |
      | "/srv/agent-area"       | rm -rf /srv/agent-area2/x         | denies, naming "is none of those" | a sibling sharing a prefix          |
      | unset                   | ls -la                            | is silent                         |                                     |
      | "build:/srv/agent-area" | ls -la                            | is silent                         | a valid value says nothing          |

  Scenario Outline: a LANGUETTE_RM_ALLOW that does not parse denies a recursive delete, naming the variable
    Given LANGUETTE_RM_ALLOW is "<value>"
    When the agent runs `rm -rf /tmp/ok`
    Then the guard denies, naming "LANGUETTE_RM_ALLOW"

    Examples:
      | value       |
      | build:      |
      | :build      |
      | a::b        |
      | :           |
      | a b         |
      | dist*       |
      | $X          |
      | a/b         |
      | rel/path    |
      | .           |
      | ..          |
      | /           |
      | //          |
      | {HOME}      |
      | {HOME}/     |
      | /srv/../etc |
      | /srv/./x    |
      | /srv//x     |
      | a;b         |
      | "x"         |

  Scenario Outline: a LANGUETTE_RM_ALLOW root that is a symlink to $HOME or / does not parse
    Given the symlink "{TMP}/link" to "<target>"
    And LANGUETTE_RM_ALLOW is "{TMP}/link"
    When the agent runs `rm -rf proj/x`
    Then the guard denies, naming "LANGUETTE_RM_ALLOW"

    Examples:
      | target |
      | {HOME} |
      | /      |

  Scenario Outline: a LANGUETTE_RM_ALLOW that does not parse warns on every other command
    Given LANGUETTE_RM_ALLOW is "<value>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | value    | command                  | verdict                             |
      | a b      | ls -la                   | warns about "LANGUETTE_RM_ALLOW"    |
      | a b      | rm build.log             | warns about "LANGUETTE_RM_ALLOW"    |
      | a b      | git rm -r --cached build | warns about "LANGUETTE_RM_ALLOW"    |
      | a b      | find /tmp/ok -delete     | denies, naming "LANGUETTE_RM_ALLOW" |
      | build:   | ls -la                   | warns about "LANGUETTE_RM_ALLOW"    |
      | build:   | rm build.log             | warns about "LANGUETTE_RM_ALLOW"    |
      | build:   | git rm -r --cached build | warns about "LANGUETTE_RM_ALLOW"    |
      | build:   | find /tmp/ok -delete     | denies, naming "LANGUETTE_RM_ALLOW" |
      | rel/path | ls -la                   | warns about "LANGUETTE_RM_ALLOW"    |
      | rel/path | rm build.log             | warns about "LANGUETTE_RM_ALLOW"    |
      | rel/path | git rm -r --cached build | warns about "LANGUETTE_RM_ALLOW"    |
      | rel/path | find /tmp/ok -delete     | denies, naming "LANGUETTE_RM_ALLOW" |
      | /        | ls -la                   | warns about "LANGUETTE_RM_ALLOW"    |
      | /        | rm build.log             | warns about "LANGUETTE_RM_ALLOW"    |
      | /        | git rm -r --cached build | warns about "LANGUETTE_RM_ALLOW"    |
      | /        | find /tmp/ok -delete     | denies, naming "LANGUETTE_RM_ALLOW" |
      | {HOME}   | ls -la                   | warns about "LANGUETTE_RM_ALLOW"    |
      | {HOME}   | rm build.log             | warns about "LANGUETTE_RM_ALLOW"    |
      | {HOME}   | git rm -r --cached build | warns about "LANGUETTE_RM_ALLOW"    |
      | {HOME}   | find /tmp/ok -delete     | denies, naming "LANGUETTE_RM_ALLOW" |

  @shell_only
  Scenario: with no jq or awk on PATH the guard denies
    Given PATH holds only "sh cat printf dirname head cut readlink"
    And the working directory is "/x"
    When the agent runs `rm -rf node_modules`
    Then the guard denies

  Scenario: a payload that does not parse is denied
    When the payload is:
      """
      not json
      """
    Then the guard denies
