@shell
Feature: no-git-footguns
  The git commands that throw work away are denied, wherever in the command
  they hide; prose that names them is not them.

  Scenario Outline: blanket staging is denied; staging by path is not
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                 | verdict   | note                              |
      | git add -A                              | denies    | blanket staging                   |
      | git add --all                           | denies    |                                   |
      | git add .                               | denies    | blanket staging, dot              |
      | git add :/                              | denies    |                                   |
      | git add -u                              | denies    | with no path                      |
      | git add -Av                             | denies    | a flag cluster                    |
      | yadm add -A                             | denies    |                                   |
      | cd foo && git add -A && git commit -m x | denies    | in a chain                        |
      | git -C /some/dir add -A                 | denies    | git -C                            |
      | git commit -a -m "x"                    | denies    |                                   |
      | git commit -am "x"                      | denies    | commit -a is add -u in disguise   |
      | git commit --all -m x                   | denies    |                                   |
      | git add hooks/foo.sh README.md          | is silent | staging by path                   |
      | git add -u src/                         | is silent | with a path                       |
      | git add -p foo                          | is silent |                                   |
      | git commit -m "add -A everything"       | is silent |                                   |
      | git commit --amend --no-edit            | is silent |                                   |
      | git commit -m 'block git commit -a'     | is silent | a commit message that mentions -a |
      | git commit -S -m x                      | is silent | -S is not -a                      |

  Scenario Outline: popping, dropping or clearing the shared stash is denied
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                          | verdict   | note                                       |
      | git stash pop                    | denies    | the stash stack is shared across worktrees |
      | git stash pop stash@{2}          | denies    | by ref                                     |
      | git stash push -u -m tag         | is silent |                                            |
      | git stash apply abc123           | is silent | apply by sha                               |
      | git stash list --format="%H %gs" | is silent |                                            |
      | git stash drop stash@{0}         | is silent |                                            |

  Scenario Outline: a force push is denied, unless it is a lease to a branch that is not main
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                           | verdict   | note                     |
      | git push --force origin foo                                       | denies    | bare force push          |
      | git push -f origin foo                                            | denies    |                          |
      | git push -fu origin foo                                           | denies    |                          |
      | git push origin +foo                                              | denies    | a + refspec forces       |
      | git push --force-with-lease origin main                           | denies    | force to main            |
      | git push --force-with-lease origin HEAD:main                      | denies    | HEAD:main is main        |
      | git push --force-with-lease origin foo:refs/heads/main            | denies    | refs/heads/main is main  |
      | git push --force-with-lease=master origin master                  | denies    | master is main too       |
      | git push --force-with-lease origin claude/foo                     | is silent | the one legitimate force |
      | git push --force-with-lease origin HEAD:claude/foo                | is silent | HEAD:branch              |
      | git push --force-with-lease origin main:backup                    | is silent | from main, to a branch   |
      | git push origin HEAD:main                                         | is silent | not a force              |
      | git push -u origin claude/foo                                     | is silent |                          |
      | git push --force-with-lease --force-if-includes origin claude/foo | is silent |                          |

  Scenario Outline: discarding uncommitted work is denied
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                    | verdict   | note                      |
      | git checkout .             | denies    | discards uncommitted work |
      | git checkout -- .          | denies    |                           |
      | git restore .              | denies    |                           |
      | git restore -SW .          | denies    | -W is the worktree        |
      | git clean -f               | denies    |                           |
      | git clean -fdx             | denies    |                           |
      | git clean -fd              | denies    | deletes untracked files   |
      | git checkout main          | is silent | switching branch          |
      | git checkout -b foo        | is silent |                           |
      | git checkout -- src/foo.ts | is silent | one path                  |
      | git restore src/foo.ts     | is silent | one path                  |
      | git restore --staged .     | is silent | unstaging is reversible   |
      | git clean -n               | is silent |                           |
      | git clean -fdn             | is silent |                           |

  Scenario Outline: force-deleting a branch is denied
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                    | verdict   | note                                       |
      | git branch -D foo                          | denies    | throws away unmerged work                  |
      | git branch --delete --force foo            | denies    |                                            |
      | git branch -df foo                         | denies    |                                            |
      | git branch -d foo                          | is silent | -d refuses when there is something to lose |
      | git branch -a                              | is silent | listing                                    |
      | git commit -m "hooks: block git branch -D" | is silent | prose                                      |

  Scenario Outline: git inside a substitution or a group is still git; prose about it is not
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                           | verdict   | note                    |
      | grep -rn "git add -A" .           | is silent | grep's pattern is prose |
      | gitleaks protect --staged         | is silent |                         |
      | x=$(git add -A)                   | denies    | command substitution    |
      | x=$(git checkout .)               | denies    | command substitution    |
      | (git clean -fd)                   | denies    | a subshell              |
      | { git stash pop; }                | denies    | a brace group           |
      | x=`git push -f origin foo`        | denies    | backticks               |
      |                                   | is silent | the empty command       |
      | echo "run git push --force later" | is silent | echo prints             |

  Scenario Outline: bypasses found on a second look
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                             | verdict   | note                               |
      | git add ./                          | denies    |                                    |
      | git add -- '.'                      | denies    | quoted .                           |
      | git add "."                         | denies    | double-quoted .                    |
      | git add '*'                         | denies    | quoted glob                        |
      | git checkout -- './'                | denies    | quoted ./                          |
      | git stash drop                      | denies    | drop with no ref drops the top     |
      | git stash clear                     | denies    |                                    |
      | git push --delete origin main       | denies    |                                    |
      | git push -d origin main             | denies    |                                    |
      | git push origin :main               | denies    |                                    |
      | sudo git add -A                     | denies    | git reached through a wrapper      |
      | GIT_DIR=x git add -A                | denies    | an assignment prefix               |
      | timeout 30 git push -f origin foo   | denies    | a wrapper with an argument         |
      | /usr/bin/git add -A                 | denies    | a full path                        |
      | git push --delete origin claude/foo | is silent | deleting a branch that is not main |
      | git push origin :claude/foo         | is silent | the same, by refspec               |
      | git stash drop stash@{3}            | is silent | by ref                             |
      | git stash drop abc123               | is silent | by sha                             |

  Scenario: a footgun after a heredoc is still run
    When the agent runs:
      """
      cat <<EOF > x
      hi
      EOF
      git add -A
      """
    Then the guard denies

  Scenario Outline: prose that names a footgun is not a footgun
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                       | note          |
      | echo git add -A               | echo prints   |
      | printf "%s\\n" git checkout . | printf prints |

  Scenario: a heredoc body is not run
    When the agent runs:
      """
      cat > doc.md <<'EOF'
      never run git add -A
      EOF
      """
    Then the guard is silent

  Scenario: a heredoc body with an unquoted tag is not run
    When the agent runs:
      """
      cat > doc.md <<EOF
      - `git push --force` is bad
      EOF
      """
    Then the guard is silent

  Scenario: a <<- heredoc body, tab-indented, is not run
    When the agent runs:
      """
      cat <<-EOF
      	git stash pop
      	EOF
      """
    Then the guard is silent

  Scenario: a footgun before a heredoc is still run
    When the agent runs:
      """
      git add -A
      cat <<EOF
      x
      EOF
      """
    Then the guard denies

  Scenario: a footgun before a long heredoc is still run
    When the agent runs:
      """
      git checkout .
      git commit -F- <<'EOF'
      fix a bug in the thing
      second line
      EOF
      """
    Then the guard denies

  Scenario: a clean command before a heredoc that names a footgun
    When the agent runs:
      """
      git add foo.sh
      git commit -F- <<'EOF'
      never git add -A
      EOF
      """
    Then the guard is silent

  Scenario Outline: git reached through another command, an escape or a nested shell is still git
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                            | verdict   | note                            |
      | for d in a b; do git add -A; done                  | denies    | a loop body                     |
      | if true; then git commit -am x; fi                 | denies    | an if body                      |
      | ls \| xargs git add -A                             | denies    |                                 |
      | chronic git push --force origin foo                | denies    | an unknown wrapper              |
      | \git add -A                                        | denies    | an escaped command word         |
      | 'git' add -A                                       | denies    | a quoted command word           |
      | sh -c 'git add -A && git commit -m x'              | denies    | nested text scanned             |
      | eval "git stash pop"                               | denies    | eval runs its text              |
      | git add -A 2>/dev/null                             | denies    | a redirection after it          |
      | sleep 1 & git add -A                               | denies    | after &                         |
      | { git add -A; }                                    | denies    | in a brace group                |
      | git reset --hard HEAD~1                            | denies    | discards uncommitted work       |
      | git re\set --hard                                  | denies    | an escaped subcommand           |
      | cd x && git -C y reset --hard origin/main          | denies    | behind git -C, in a chain       |
      | git reset --soft HEAD~1                            | is silent | reversible                      |
      | git reset --har HEAD~1                             | denies    | an abbreviated long option      |
      | git add --al                                       | denies    | an abbreviated long option      |
      | git clean --forc                                   | denies    | an abbreviated long option      |
      | git clean --forc --dry                             | is silent |                                 |
      | git branch --del --for topic                       | denies    |                                 |
      | git push --force-w origin topic                    | is silent | --force-w is --force-with-lease |
      | git push --force-w origin main                     | denies    | the same, to main               |
      | git commit -m "hooks: block git add -A everywhere" | is silent | prose in a commit message       |
      | git commit -m "block git add -A everywhere"        | is silent | prose in a commit message       |
      | echo "never run git add -A"                        | is silent | echo prints                     |
      | git commit -m "it's done" && echo "don't"          | is silent | apostrophes in prose            |
      | sudo apt-get install -y git                        | is silent | git as an argument              |
      | git-lfs install                                    | is silent | git-lfs is not git              |

  Scenario: reset --hard named in a heredoc is not run
    When the agent runs:
      """
      cat <<'EOF'
      never run git reset --hard
      EOF
      """
    Then the guard is silent

  Scenario: reset --hard after a heredoc is still run
    When the agent runs:
      """
      cat <<EOF
      x
      EOF
      git reset --hard HEAD~1
      """
    Then the guard denies

  Scenario: a comment is not run
    When the agent runs:
      """
      # git add -A is banned
      git status
      """
    Then the guard is silent

  Scenario: add -A in a commit message heredoc is not run
    When the agent runs:
      """
      git commit -F- <<EOF
      block git add -A
      EOF
      """
    Then the guard is silent

  @shell_only
  Scenario: with no jq or awk on PATH the guard denies
    Given PATH holds only "sh cat printf dirname"
    When the agent runs `git add -A`
    Then the guard denies

  Scenario Outline: a rule's own setting, off, lets its command through
    Given <setting> is "false"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | setting                                              | command                     |
      | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_BLANKET_STAGING | git add -A                  |
      | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_STASH           | git stash pop               |
      | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_FORCE_PUSH      | git push --force origin foo |
      | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_DISCARD         | git reset --hard            |
      | CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_BRANCH_DELETE   | git branch -D foo           |

  Scenario Outline: turning one rule off leaves the others denying
    Given CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_BLANKET_STAGING is "false"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                     |
      | git stash pop               |
      | git push --force origin foo |
      | git reset --hard            |
      | git branch -D foo           |

  Scenario: a setting that is not exactly false leaves the rule on
    Given CLAUDE_PLUGIN_OPTION_NO_GIT_FOOTGUNS_BLANKET_STAGING is "no"
    When the agent runs `git add -A`
    Then the guard denies
