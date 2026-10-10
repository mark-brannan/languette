@python
Feature: guard-permissions
  A recursive chown, chgrp or chmod, chmod 777, and a find that runs one of
  them are denied unless every target is the agent's own area: the
  scratchpad, an agent worktree, /tmp, or a path LANGUETTE_PERM_ALLOW names.
  The working directory is {CWD}, a directory outside $HOME, unless a
  scenario says otherwise.

  Scenario Outline: a recursive sweep of anything but the agent's own area is denied, however the flag is spelled
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                         | naming                         | note                                            |
      | chmod -R 755 .                  | is none of those               | the working directory is the user's             |
      | chmod -R 755 src                | is none of those               |                                                 |
      | chown -R me:me ~/project        | is none of those               |                                                 |
      | chgrp -R staff build            | is none of those               |                                                 |
      | chmod --recursive 755 src       | is none of those               | --recursive spelled out                         |
      | chmod --rec 755 src             | is none of those               | GNU long-option prefix of --recursive           |
      | chmod -Rf 755 src               | is none of those               | a short cluster holding R                       |
      | chmod -vR 755 src               | is none of those               |                                                 |
      | chmod 755 -R src                | is none of those               | options may follow the operands                 |
      | chmod -R -x src                 | is none of those               | a mode that begins with a dash                  |
      | chmod --reference=ref -R src    | is none of those               | with --reference there is no mode operand       |
      | chmod -R 755 -- src             | is none of those               |                                                 |
      | sudo chown -R root /srv/x       | is none of those               |                                                 |
      | timeout 5 chmod -R 755 src      | is none of those               |                                                 |
      | chmod -R 755 /tmp/x ~/project   | is none of those               | one target the user's is enough                 |
      | chmod -R 755 /                  | root of the filesystem         | never /                                         |
      | chmod -R 755 ~                  | $HOME itself                   | never $HOME                                     |
      | chmod -R 755 "$DIR"             | variable or command substitution | unresolvable word; loud                       |
      | chmod -R 755 src/*              | glob or brace expansion        |                                                 |
      | chmod -R 755 dist{,2}           | glob or brace expansion        |                                                 |
      | chmod -R 755 {a,b}              | no target is visible           | a brace list, no visible target                 |
      | chmod -R 755 ../x               | `..` segment                   |                                                 |
      | chmod -R 755 ~someone/x         | only a leading `~/`            |                                                 |
      | chmod -R 755 "my dir"           | quoted string with whitespace  |                                                 |
      | cd x && chmod -R 755 y          | `cd` earlier                   | a relative target after a cd cannot be resolved |
      | xargs chmod -R 755              | no target is visible           | xargs hides the target                          |
      | chmod -R 755 /tmp/x/.git        | inside a .git                  | even in /tmp: a repository's own store          |
      | chmod -R 755 ~/.claude/worktrees/w/.git | inside a .git          | even in an agent worktree                       |

  Scenario Outline: chmod 777 is denied outside the agent's own area
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                | verdict   | note                                |
      | chmod 777 run.sh       | denies    |                                     |
      | chmod 0777 run.sh      | denies    |                                     |
      | chmod a+rwx run.sh     | denies    | 777 by another name                 |
      | chmod ugo+rwx run.sh   | denies    |                                     |
      | chmod a=rwx run.sh     | denies    |                                     |
      | chmod 777 "$f"         | denies    | an unresolvable target              |
      | ls \| xargs chmod 777  | denies    | no visible target                   |
      | chmod 777 /tmp/x       | is silent | /tmp is the agent's                 |
      | chmod 755 run.sh       | is silent |                                     |
      | chmod 1777 /tmp/x      | is silent | the sticky bit makes it not 777     |
      | chmod 775 run.sh       | is silent |                                     |

  Scenario Outline: find that runs a permission change over a tree is a sweep of its start paths
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                         | verdict   | note                                    |
      | find . -type d -exec chmod 755 {} +             | denies    | the start path is the working directory |
      | find ~/project -exec chown me {} \;             | denies    |                                         |
      | find src -name '*.sh' -exec chmod +x {} \;      | denies    | even a harmless-looking mode: a sweep   |
      | find . -execdir chgrp staff {} +                | denies    | -execdir                                |
      | find . -ok chmod 600 {} \;                      | denies    | -ok                                     |
      | find -exec chmod 600 {} +                       | denies    | no start path                           |
      | find /etc -exec sudo chmod 777 {} \;            | denies    | a wrapper between -exec and chmod       |
      | find . -exec env FOO=1 chmod 644 {} +           | denies    |                                         |
      | find . -exec nice chmod 644 {} +                | denies    |                                         |
      | find . -exec sudo -u root chown me {} +         | denies    | a wrapper with an option and a value    |
      | find ~/project -exec sh -c 'chmod 644 "$0"' {} \; | denies | a shell running chmod                   |
      | find /tmp/x -exec sudo chmod 644 {} \;          | is silent | the start path is the agent's           |
      | find /tmp/x -exec sh -c 'chmod 644 "$0"' {} \;  | is silent |                                         |
      | find . -exec sudo grep -l mode {} +             | is silent | a wrapper around something else         |
      | find /tmp/x -exec chmod 644 {} +                | is silent | the start path is the agent's           |
      | find /tmp/x -exec chmod -R 755 {} +             | is silent |                                         |
      | find /tmp/x -exec chmod 644 ~/project/f {} \;   | denies    | and a target of its own is judged too   |
      | find . -name '*.sh' -exec grep -l chmod {} +    | is silent | chmod is an argument of grep            |

    @also_guard-recursive-delete
    Examples:
      | command                                         | verdict   | note                                    |
      | find . -name '*.log' -delete                    | is silent | not a permission change                 |

  Scenario Outline: a permission change that is not a sweep, and the agent's own areas, pass
    Given the working directory is "<cwd>"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | cwd                                 | command                                     | note                                    |
      | {HOME}/project                      | chmod +x run.sh                             | not recursive                           |
      | {HOME}/project                      | chmod 644 notes.md                          |                                         |
      | {HOME}/project                      | chmod u+x,g-w a b                           |                                         |
      | {HOME}/project                      | chown me file                               |                                         |
      | {HOME}/project                      | chgrp staff file                            |                                         |
      | {HOME}/project                      | chmod -x run.sh                             | a mode that begins with a dash          |
      | {HOME}/project                      | chmod -R 755 /tmp/x                         | /tmp is the agent's                     |
      | {HOME}/project                      | chown -R me /tmp/a /tmp/b                   |                                         |
      | {HOME}/project                      | chmod -R 755 {HOME}/.local/state/claude-tmpdir/x | the scratchpad                     |
      | {HOME}/project                      | chmod -R 755 {HOME}/.claude/worktrees/w/src | an agent worktree                       |
      | {HOME}/project                      | chmod -R 755 ~/.claude/worktrees/w/src      | ~/ spelled out                          |
      | /tmp                                | chmod -R 755 .                              | the working directory is the agent's    |
      | /tmp/x                              | chmod -R 755 sub dir                        | relative targets resolve to /tmp        |
      | {HOME}/project                      | git commit -m "chmod -R 777 everything"     | prose that names it is not it           |
      | {HOME}/project                      | echo chmod -R 755 src                       |                                         |
      | {HOME}/project                      | grep -r "chmod -R" docs                     |                                         |
      | {HOME}/project                      | man chmod                                   |                                         |

  Scenario Outline: a wrapper that changes directory is a cd the guard cannot follow
    Given the working directory is "/tmp"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                              | verdict                             | note                                   |
      | env -C /etc chmod -R 755 .           | denies, naming "`cd` earlier"       | GNU env -C                             |
      | env --chdir=/etc chmod -R 755 .      | denies, naming "`cd` earlier"       |                                        |
      | sudo -D /etc chmod -R 755 .          | denies, naming "`cd` earlier"       | sudo -D                                |
      | sudo --chdir /etc chown -R me sub    | denies, naming "`cd` earlier"       |                                        |
      | env -C/etc chmod -R 755 .            | denies, naming "`cd` earlier"       | the value attached                     |
      | sudo -D/etc chmod -R 755 .           | denies, naming "`cd` earlier"       |                                        |
      | sudo -nD /etc chmod -R 755 .         | denies, naming "`cd` earlier"       | a short cluster                        |
      | env -iC /etc chmod -R 755 .          | denies, naming "`cd` earlier"       |                                        |
      | env --chd=/etc chmod -R 755 .        | denies, naming "`cd` earlier"       | a getopt prefix of --chdir             |
      | sudo -R /srv chmod -R 755 .          | denies, naming "`cd` earlier"       | sudo -R is a chroot: `.` moves too     |
      | sudo -u root chmod -R 755 .          | is silent                           | -u takes root as its value             |
      | sudo -E chmod -R 755 .               | is silent                           | chmod's own -R is not sudo's           |
      | env -C /etc chmod -R 755 /tmp/x      | is silent                           | an absolute target is still judged     |
      | env FOO=1 chmod -R 755 .             | is silent                           | env without a chdir option             |
      | sudo chmod -R 755 .                  | is silent                           | /tmp is the working directory          |

  Scenario: a sweep is judged where it lands, not by the working directory it began in
    Given the working directory is "/tmp"
    When the agent runs `cd ~/project && chmod -R 755 .`
    Then the guard denies, naming "`cd` earlier"

  Scenario Outline: a target must be allowed where its symlinks lead, too
    Given the directory "{TMP}/real"
    And the symlink "{TMP}/escape" to "{HOME}"
    And the symlink "{TMP}/inside" to "{TMP}/real"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                              | verdict                                    | note                                      |
      | chmod -R 755 {TMP}/escape/Documents  | denies, naming "resolves through a symlink" | under /tmp by name, into $HOME by symlink |
      | chmod -R 755 {TMP}/escape/           | denies, naming "resolves through a symlink" | a trailing slash follows the link         |
      | chmod -R 755 {TMP}/inside/x          | is silent                                  | a symlink under /tmp into /tmp            |
      | chmod -R 755 {TMP}/real              | is silent                                  |                                           |

  Scenario: the denial names the safe path
    When the agent runs `chmod -R 755 src`
    Then the guard denies, naming "chmod or chown the paths themselves, without -R"

  Scenario Outline: LANGUETTE_PERM_ALLOW adds absolute paths to the agent's areas, and nothing else
    Given LANGUETTE_PERM_ALLOW is "{HOME}/shared:{HOME}/other"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                  | verdict                           | note                                  |
      | chmod -R 755 {HOME}/shared/build         | is silent                         | under an allowed path                 |
      | chmod -R 755 {HOME}/other                | is silent                         | the path itself                       |
      | chmod -R 755 {HOME}/project              | denies, naming "is none of those" | not listed                            |
      | chmod -R 755 /tmp/x                      | is silent                         | the built-in areas stay                |
      | chmod -R 755 {HOME}/shared/.git          | denies, naming "inside a .git"    | never a .git, whatever is allowed     |
      | chmod 777 {HOME}/shared/x                | is silent                         | chmod 777 is judged the same way      |

    @also_guard-worktrees
    Examples:
      | command                                  | verdict                           | note                                  |
      | chmod -R 755 {HOME}/shared/../project    | denies, naming "`..` segment"     |                                       |

  Scenario Outline: a LANGUETTE_PERM_ALLOW that does not parse warns, and blocks only a sweep
    Given LANGUETTE_PERM_ALLOW is "<value>"
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | value                | command                  | verdict                                         |
      | shared               | ls                       | warns about "LANGUETTE_PERM_ALLOW is malformed" |
      | shared               | chmod -R 755 /tmp/x      | denies, naming "LANGUETTE_PERM_ALLOW is malformed" |
      | shared               | chmod +x run.sh          | warns about "is not an absolute path"           |
      | /srv/a::/srv/b       | chmod -R 755 /tmp/x      | denies, naming "an empty entry"                 |
      | /srv/a b             | chmod -R 755 /tmp/x      | denies, naming "unsupported character"          |
      | /srv/*               | chmod -R 755 /tmp/x      | denies, naming "unsupported character"          |
      | /srv/../etc          | chmod -R 755 /tmp/x      | denies, naming ". or .. segment"                |
      | /                    | chmod -R 755 /tmp/x      | denies, naming "is / or $HOME"                  |
      | {HOME}               | chmod -R 755 /tmp/x      | denies, naming "is / or $HOME"                  |
      | {HOME}/shared        | ls                       | is silent                                       |

  Scenario Outline: a LANGUETTE_PERM_ALLOW root that is a symlink to $HOME or / does not parse
    Given the symlink "{TMP}/link" to "<target>"
    And LANGUETTE_PERM_ALLOW is "{TMP}/link"
    When the agent runs `chmod -R 755 proj/x`
    Then the guard denies, naming "LANGUETTE_PERM_ALLOW"

    Examples:
      | target |
      | {HOME} |
      | /      |
