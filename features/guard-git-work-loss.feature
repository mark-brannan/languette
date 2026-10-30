@python
Feature: guard-git-work-loss
  The git commands that throw work away are denied, or asked about, wherever in
  the command they hide; prose that names them is not them.

  Why. These are the git moves that have bitten users, or sit in the same
  class, and that an agent session never has a good reason to make. Blanket
  staging (`git add -A`, `--all`, `.`, `-u` with no path, `git commit -a`)
  stages the home directory where the worktree is $HOME, and elsewhere sweeps
  in a parallel session's files. The stash stack is shared across worktrees,
  so a pop, a bare drop or a clear can take another session's entry; apply
  and drop by sha pass. Force push is bare `--force`, `-f` or a `+refspec`
  anywhere, `--force-with-lease` to main or master (asks), or deleting main;
  rebasing a session branch, with `--force-with-lease` to that branch, is the
  one legitimate force. `git checkout .`, `git restore .` and `git clean -f`
  throw away uncommitted work, as `reset --hard` does, and `branch -D` throws
  away unmerged work (`-d` refuses; use that). On a clean working tree the
  discards (checkout, restore, clean, `reset --hard`) have nothing to lose and
  pass. A git wrapper such as `yadm` or `vcsh` is treated as `git`. `stow --adopt` asks:
  it moves each conflicting file from the target directory into the package,
  overwriting the repo's copy, which survives only if committed. `stow -D` and
  `-R` alone only remove or replace links and pass; so does a dry run (`-n`).
  Stow need not be installed: the command is recognised by its shape, `--adopt`
  being any prefix of it (`--ado`), wherever it stands among the package names.

  Each rule has its own switch, the plugin options
  guard_git_work_loss_blanket_staging, _stash, _force_push, _discard,
  _branch_delete and _adopt; a rule is skipped only when its option is exactly `false`.
  The whole-guard option guard_git_work_loss=false skips all six. git takes
  any unambiguous prefix of a long option (`--har` is `--hard`), so the guard
  does too.

  This is a gate, so it fails closed: an unreadable payload or a command that
  does not parse is a deny. Heredoc bodies are dropped (a doc that mentions
  `git add -A` is not a git command); quotes are removed and escapes applied,
  so `\git` and `'git'` are git; and git counts as the command wherever it
  stands in a segment (after sudo, env, VAR=x, timeout, xargs, `do`, `then`)
  with git's global options skipped. The body of a quoted string with
  whitespace (`sh -c '...'`, `eval "..."`) is scanned as well, there by
  command position only, so a commit message that mentions a flag
  mid-sentence does not trip it.

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
      | git add -u --chmod +x                   | denies    | +x is --chmod's value, not a path |
      | git add -u --chm +x                     | denies    | the same, a unique prefix         |
      | git add -u --chmod=+x                   | denies    | the same, glued                   |
      | git add --renormalize                   | denies    | it implies -u                     |
      | git add --frobnicate src/               | denies    | an option the guard does not know |
      | git add -uz src/                        | denies    | the same, in a cluster            |
      | git add --ign src/                      | denies    | an ambiguous prefix               |
      | yadm add -A                             | denies    |                                   |
      | vcsh dots add -A                        | denies    | vcsh names its repository first   |
      | cd foo && git add -A && git commit -m x | denies    | in a chain                        |
      | git -C /some/dir add -A                 | denies    | git -C                            |
      | git commit -a -m "x"                    | denies    |                                   |
      | git commit -am "x"                      | denies    | commit -a is add -u in disguise   |
      | git commit --all -m x                   | denies    |                                   |
      | git add hooks/foo.sh README.md          | is silent | staging by path                   |
      | git add -u src/                         | is silent | with a path                       |
      | git add -u --chmod +x src/              | is silent | a path beside --chmod's value     |
      | git add --chmod=+x hooks/foo.sh         | is silent | chmod by path                     |
      | git add -p foo                          | is silent |                                   |
      | git add -h                              | is silent | usage stages nothing              |
      | git add --help                          | is silent | the manual stages nothing         |
      | git add -A --help                       | is silent | help wins over -A                 |
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

  Scenario Outline: a force push is denied, a lease to main asks, a lease to any other branch passes
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                           | verdict   | note                     |
      | git push --force origin foo                                       | denies    | bare force push          |
      | git push -f origin foo                                            | denies    |                          |
      | git push -fu origin foo                                           | denies    |                          |
      | git push origin +foo                                              | denies    | a + refspec forces       |
      | git push --force-with-lease origin claude/foo                     | is silent | the one legitimate force |
      | git push --force-with-lease origin HEAD:claude/foo                | is silent | HEAD:branch              |
      | git push --force-with-lease origin main:backup                    | is silent | from main, to a branch   |
      | git push -u origin claude/foo                                     | is silent |                          |
      | git push --force-with-lease --force-if-includes origin claude/foo | is silent |                          |

    @also_guard-bypass-ruleset
    Examples:
      | command                                                           | verdict   | note                     |
      | git push --force-with-lease origin main                           | asks      | force to main            |
      | git push --force-with-lease origin HEAD:main                      | asks      | HEAD:main is main        |
      | git push --force-with-lease origin foo:refs/heads/main            | asks      | refs/heads/main is main  |
      | git push --force-with-lease=master origin master                  | asks      | master is main too       |
      | git push origin HEAD:main                                         | is silent | not a force              |
      | git push --force-with-lease origin main && git reset --hard       | denies    | an ask does not hide a later deny |
      | git reset --hard && git push --force-with-lease origin main       | denies    | a deny before an ask still denies |
      | git push --force-with-lease origin +main                          | denies    | +refspec is a force       |
      | git push --force-with-lease --force origin main                   | denies    | a bare --force beside the lease |

    @also_guard-git-stacked-base
    Examples:
      | command                                                           | verdict   | note                     |
      | git push --force-with-lease origin :main                          | denies    | deleting main, lease or not |
      | git push --force-with-lease --delete origin main                  | denies    | deleting main, lease or not |

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

  # Nothing to discard on a clean tree. Asked of git in the directory the
  # session runs in, so a cd, -C, --git-dir, --work-tree or GIT_DIR in the
  # command leaves the deny standing: there the guard cannot say which tree.
  Scenario Outline: discarding is allowed when the working tree is clean
    Given a git repository at "{TMP}/clean"
    And the working directory is "{TMP}/clean"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command           | note                                   |
      | git checkout .    |                                        |
      | git checkout -- . |                                        |
      | git restore .     |                                        |
      | git clean -fd     |                                        |
      | git reset --hard  | HEAD, so no commit is dropped          |
      | sh -c 'git checkout .'   | sh's own -c is not a git option |
      | bash -c "git restore ."  | sh's own -c is not a git option |
      | env LC_ALL=C git checkout .     | env with plain assignments is no wrapper |
      | LC_ALL=C git restore .          | an assignment is no wrapper     |

  Scenario Outline: discarding is still denied when the tree is clean but the target is not known
    Given a git repository at "{TMP}/clean"
    And the working directory is "{TMP}/clean"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                          | note                                  |
      | git reset --hard HEAD~1          | drops a commit                        |
      | git -C {TMP}/clean checkout .    | -C names the tree; not looked at      |
      | cd {TMP}/clean && git restore .  | a cd moves the tree                   |
      | git clean -fdx                   | ignored files are not in the status   |
      | env --chdir={TMP}/clean git checkout . | a wrapper's chdir moves the tree |
      | git -c core.worktree={TMP}/clean checkout . | -c can re-aim the work tree |
      | sh -c 'git -c core.worktree={TMP}/clean checkout .' | git's -c, inside the quoted script |
      | sh -c 'git -C {TMP}/clean checkout .' | git's -C, inside the quoted script |
      | GIT_CONFIG_COUNT=0 git checkout .      | config from the environment      |
      | touch x && git clean -fd         | an earlier segment can dirty the tree |
      | echo x > f && git checkout -- .  | a redirect can dirty the tree         |
      | git apply p && git checkout .    | the patch is the work being discarded |
      | git merge --squash b && git reset --hard | the staged result would go    |
      | git clean -fd -e '!*'            | a negated exclude un-ignores files    |
      | git clean -fd --exclude='!*'     | a negated exclude un-ignores files    |
      | git clean -fde '!*'              | e in a short cluster                  |
      | ssh host git reset --hard        | a remote wrapper runs git elsewhere   |
      | docker exec c git reset --hard   | a remote wrapper runs git elsewhere   |
      | kubectl exec p -- git reset --hard | a remote wrapper runs git elsewhere |
      | nsenter --wd=/tmp git reset --hard | a wrapper's chdir moves the tree    |
      | bwrap --chdir /tmp git reset --hard | a wrapper's chdir moves the tree   |
      | chroot /tmp git reset --hard     | a wrapper's root moves the tree       |
      | watch -n 60 git reset --hard     | a repeat runs after the status read   |
      | systemd-run --user --on-active=1h git reset --hard | a delay runs after the status read |

    @also_guard-sudo
    Examples:
      | command                          | note                                  |
      | sudo -D {TMP}/clean git checkout .     | a wrapper's chdir moves the tree |

  Scenario Outline: discarding is denied when the working tree has changes
    Given a git repository at "{TMP}/dirty"
    And the file "{TMP}/dirty/notes.txt" holds:
      """
      work in progress
      """
    And the working directory is "{TMP}/dirty"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command           |
      | git checkout .    |
      | git restore .     |
      | git clean -fd     |
      | git reset --hard  |

  # `git status` leaves out a file marked assume-unchanged or skip-worktree, so a tree
  # can read clean while a discard still throws away that file's edits.
  Scenario Outline: discarding is denied when a hidden edit sits behind a clean status
    Given a git repository at "{TMP}/flagged"
    And the tracked file "{TMP}/flagged/notes.txt" is edited and marked <flag>
    And the working directory is "{TMP}/flagged"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | flag             | command           |
      | assume-unchanged | git checkout .    |
      | assume-unchanged | git restore .     |
      | assume-unchanged | git reset --hard  |
      | skip-worktree    | git checkout .    |
      | skip-worktree    | git reset --hard  |

  Scenario: a flagged file elsewhere in the tree still denies a discard of the whole tree
    Given a git repository at "{TMP}/flagged"
    And the tracked file "{TMP}/flagged/a/notes.txt" is edited and marked assume-unchanged
    And the directory "{TMP}/flagged/b"
    And the working directory is "{TMP}/flagged/b"
    When the agent runs `git checkout :/`
    Then the guard denies

  Scenario: a tracked file with no flag does not stop a clean-tree discard
    Given a git repository at "{TMP}/tracked"
    And the tracked file "{TMP}/tracked/notes.txt" is committed
    And the working directory is "{TMP}/tracked"
    When the agent runs `git checkout .`
    Then the guard is silent

  Scenario: a repo setting that hides untracked files does not make the tree clean
    Given a git repository at "{TMP}/hidden"
    And the file "{TMP}/hidden/notes.txt" holds:
      """
      work in progress
      """
    And the file "{TMP}/hidden/.git/config" holds:
      """
      [core]
      	repositoryformatversion = 0
      [status]
      	showUntrackedFiles = no
      """
    And the working directory is "{TMP}/hidden"
    When the agent runs `git clean -fd`
    Then the guard denies

  Scenario: discarding is denied in a directory that is not a git repository
    Given the directory "{TMP}/plain"
    And the working directory is "{TMP}/plain"
    When the agent runs `git checkout .`
    Then the guard denies

  Scenario Outline: stow --adopt asks; stow without it, or only deleting, does not
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                               | verdict   | note                                         |
      | stow --adopt zsh                      | asks      | adopt before the package                     |
      | stow zsh --adopt                      | asks      | adopt after the package                      |
      | stow zsh --adopt vim                  | asks      | adopt between packages                       |
      | stow --ado zsh                        | asks      | a unique prefix                              |
      | stow -d dotfiles -t ~ --adopt zsh     | asks      | with options that take a value               |
      | stow -vS --adopt zsh                  | asks      | a bundled cluster                            |
      | stow --dir=dotfiles --adopt zsh       | asks      | a glued value                                |
      | stow -R --adopt zsh                   | asks      | a restow stows again, adopting               |
      | stow -D a -S b --adopt                | asks      | b is stowed                                  |
      | sh -c 'stow --adopt zsh'              | asks      | in a shell body                              |
      | stow --adopt -- zsh                   | asks      | packages after --                            |
      | stow zsh                              | is silent | no adopt                                     |
      | stow -D zsh                           | is silent | only removes links                           |
      | stow -R zsh                           | is silent | only replaces links                          |
      | stow -D --adopt zsh                   | is silent | nothing is stowed                            |
      | stow --adopt -D zsh vim               | is silent | the same, adopt first                        |
      | stow --delete --adopt zsh             | is silent | the same, long                               |
      | stow -n --adopt zsh                   | is silent | a dry run                                    |
      | stow --simulate --adopt zsh           | is silent | a dry run                                    |
      | stow --adopt --help                   | is silent | usage                                        |
      | stow -d --adopt                       | is silent | --adopt is -d's value, not the option        |
      | stow -d --adopt zsh                   | is silent | the same, with a package: no adopt           |
      | echo stow --adopt zsh                 | is silent | prose                                        |
      | grep stow --adopt notes.txt           | is silent | a search names stow, it does not run it      |
      | man stow --adopt zsh                  | asks      | man is not prose (its pager runs a command)  |
      | stow -t adopt zsh                     | is silent | adopt as a value, not the option             |
      | git commit -m 'stow --adopt zsh'      | is silent | a commit message                             |

    @also_guard-sudo
    Examples:
      | command                               | verdict   | note                                         |
      | sudo /usr/bin/stow --adopt zsh        | asks      | behind a wrapper, by path                    |

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
      | GIT_DIR=x git add -A                | denies    | an assignment prefix               |
      | timeout 30 git push -f origin foo   | denies    | a wrapper with an argument         |
      | /usr/bin/git add -A                 | denies    | a full path                        |
      | git stash drop stash@{3}            | is silent | by ref                             |
      | git stash drop abc123               | is silent | by sha                             |

    @also_guard-sudo
    Examples:
      | command                             | verdict   | note                               |
      | sudo git add -A                     | denies    | git reached through a wrapper      |

    @also_guard-git-stacked-base
    Examples:
      | command                             | verdict   | note                               |
      | git push --delete origin main       | denies    |                                    |
      | git push -d origin main             | denies    |                                    |
      | git push origin :main               | denies    |                                    |
      | git push --delete origin claude/foo | is silent | deleting a branch that is not main |
      | git push origin :claude/foo         | is silent | the same, by refspec               |

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
      - git push --force is bad
      EOF
      """
    Then the guard is silent

  @also_guard-bypass-ruleset
  Scenario: a backtick code span in an unquoted heredoc body is run by the shell
    When the agent runs:
      """
      cat > doc.md <<EOF
      - `git push --force` is bad
      EOF
      """
    Then the guard denies, naming "git push --force"

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
      | git commit -m "hooks: block git add -A everywhere" | is silent | prose in a commit message       |
      | git commit -m "block git add -A everywhere"        | is silent | prose in a commit message       |
      | echo "never run git add -A"                        | is silent | echo prints                     |
      | git commit -m "it's done" && echo "don't"          | is silent | apostrophes in prose            |
      | git-lfs install                                    | is silent | git-lfs is not git              |

    @also_guard-sudo
    Examples:
      | command                                            | verdict   | note                            |
      | sudo apt-get install -y git                        | is silent | git as an argument              |

    @also_guard-bypass-ruleset
    Examples:
      | command                                            | verdict   | note                            |
      | git push --force-w origin main                     | asks      | the same, to main               |

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


  Scenario Outline: a rule's own setting, off, lets its command through
    Given <setting> is "false"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | setting                                              | command                     |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_BLANKET_STAGING | git add -A                  |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_STASH           | git stash pop               |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_FORCE_PUSH      | git push --force origin foo |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_DISCARD         | git reset --hard            |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_BRANCH_DELETE   | git branch -D foo           |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_ADOPT           | stow --adopt zsh            |

  @awk_only
  Scenario Outline: a rule's own setting, on, denies its command
    Given <setting> is "true"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | setting                                              | command                     |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_STASH           | git stash pop               |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_FORCE_PUSH      | git push --force origin foo |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_DISCARD         | git reset --hard            |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_BRANCH_DELETE   | git branch -D foo           |

  Scenario Outline: a rule's own setting, on, asks for what it asks about
    Given <setting> is "true"
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | setting                                              | command                     |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_ADOPT           | stow --adopt zsh            |

  Scenario Outline: turning one rule off leaves the others denying
    Given CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_BLANKET_STAGING is "false"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                     |
      | git stash pop               |
      | git push --force origin foo |
      | git reset --hard            |
      | git branch -D foo           |

  Scenario: a setting that is not exactly false leaves the rule on
    Given CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_BLANKET_STAGING is "no"
    When the agent runs `git add -A`
    Then the guard denies

  Scenario Outline: one rule off still judges the other rules in the same line
    Given <setting> is "false"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | setting                                         | command                                       |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_STASH      | git stash pop; git push --force origin foo    |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_STASH      | git push --force origin foo && git stash pop  |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_DISCARD    | git reset --hard && git branch -D foo         |
      | CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_FORCE_PUSH | bash -c 'git push --force origin foo; git add -A' |

  # A global option's separate value is not the subcommand: --config-env and
  # --attr-source take one as -c and -C do.
  Scenario Outline: a global option with a separate value does not hide the subcommand
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                      | note                          |
      | git --config-env a=B reset --hard            | --config-env, separate        |
      | git --attr-source HEAD reset --hard          | --attr-source, separate       |
      | git --config-env a=B add -A                  | the same, another rule        |
      | git --attr-source HEAD push --force origin x | the same, another rule        |
      | git --config-env=a=B reset --hard            | attached, which already held  |

  # Two relaxations hold only where an agent works: a linked worktree, or the
  # session's scratchpad. $HOME and a repo's main checkout are where the user
  # works, and there both stay denied. Each is asked of git in the directory the
  # session runs in, so a cd or -C in the command leaves the deny standing.
  Rule: where an agent works, `git add -A <paths>` stages by path

    Background:
      Given a clone of "https://example.com/r.git" at "{TMP}/repo" on branch "main"
      And a linked worktree "{TMP}/repo/.claude/worktrees/feat" of the repository at "{TMP}/repo"

    Scenario Outline: -A with paths passes in a linked worktree
      Given the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                   | note                        |
        | git add -A src/x.py docs/                 | paths name what is staged   |
        | git add -A -- src/x.py                    | after --                    |
        | git add -A src/x.py && git commit -m y    | then a commit               |
        | git add --all src/x.py 2>&1               | a redirect is not a path    |
        | git add -A --chmod +x src/x.py            | --chmod's value is not a path |
        | git add -A --chm=+x src/x.py              | a prefix, glued             |
        | git add -AU 3 src/x.py                    | -U takes the next word      |
        | git add -A --pathspec-file-nul src/x.py   | a flag with no value        |
        | git add -fA src/x.py                      | -A inside a cluster         |
        | git add -A --end-of-options src/x.py      | ends the options            |
        | git add -A --no-chmod +x                  | a negated option takes no value, so +x is a path |
        | git add --no-all src/x.py                 | not -A                      |
        | git add --ignore-removal src/x.py         | not -A                      |

    Scenario Outline: -A stays denied in a linked worktree when it is blanket or its place is not known
      Given the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                                    | note                              |
        | git add -A                                                 | bare -A is blanket                |
        | git add -A .                                               | the whole tree                    |
        | git add -A --pathspec-from-file=list                       | the paths are in a file           |
        | git add -A --pathspec-from-file list                       | the same, a separate value        |
        | git add -A --pathspec-from list                            | the same, a prefix                |
        | git add -A --chmod +x                                      | +x is --chmod's value, not a path |
        | git add -A --chm +x                                        | the same, a unique prefix         |
        | git add -A --chmod=+x                                      | the same, glued                   |
        | git add -AU 3                                              | 3 is -U's value                   |
        | git add -A --unified 3                                     | the same, long                    |
        | git add -A --inter-hunk-context 3                          | another value option              |
        | git add -A --frobnicate src/x.py                           | an option the guard does not know |
        | git add -A --ign src/x.py                                  | an ambiguous prefix               |
        | git add -fA                                                | -A inside a cluster, no path      |
        | git add -A --end-of-options                                | nothing after the options         |
        | git add --no-ignore-removal                                | git reads it as -A                |
        | git -C {TMP}/repo add -A src/x.py                          | -C names another tree             |
        | cd {TMP}/repo && git add -A src/x.py                       | a cd moves the tree               |
        | git add -A src/x.py && git commit -am y                    | the commit is blanket             |

    Scenario Outline: -A with a path that reaches the whole tree is denied as blanket in a linked worktree
      Given the directory "{TMP}/repo/.claude/worktrees/feat/src/sub"
      And the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies, naming "`git add -A` is blocked: stage by path"

      Examples:
        | cwd                                           | command                                            | note                          |
        | {TMP}/repo/.claude/worktrees/feat/src         | git add -A ..                                      | up to the toplevel            |
        | {TMP}/repo/.claude/worktrees/feat/src         | git add -A ../                                     | the same, a slash             |
        | {TMP}/repo/.claude/worktrees/feat/src/sub     | git add -A ../..                                   | two up                        |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A .//                                     | the toplevel, spelled long    |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A {TMP}/repo/.claude/worktrees/feat       | the toplevel's absolute path  |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A src/x.py {TMP}/repo                     | one path above the toplevel   |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A ':(top)'                                | magic: the toplevel           |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A ':/*'                                   | magic: everything from the top |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A ':!src/x.py'                            | an exclusion: all but one     |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A ':(exclude)src/x.py'                    | the same, long form           |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A '*.py'                                  | a glob over the tree          |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A $PWD                                    | a variable the shell expands  |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A "$(pwd)"                                | a command substitution        |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A ~                                       | a tilde                       |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A {src,..}                                | a brace expansion             |
        | {TMP}/repo/.claude/worktrees/feat             | git add -A src/{x.py,}                             | a brace, one empty            |

    Scenario: -A with a path through a symlink is denied when git's lexical reading leaves the tree
      Given the directory "{TMP}/repo/.claude/worktrees/feat/src/sub/deep"
      And the symlink "{TMP}/repo/.claude/worktrees/feat/lnk" to "{TMP}/repo/.claude/worktrees/feat/src/sub/deep"
      And the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `git add -A lnk/../..`
      Then the guard denies, naming "`git add -A` is blocked: stage by path"

    Scenario: -A with a path in a subdirectory passes when it stays below the toplevel
      Given the directory "{TMP}/repo/.claude/worktrees/feat/src/sub"
      And the working directory is "{TMP}/repo/.claude/worktrees/feat/src/sub"
      When the agent runs `git add -A .. x.py`
      Then the guard is silent

    Scenario: -A with paths is denied in a repo's main checkout
      Given the working directory is "{TMP}/repo"
      When the agent runs `git add -A src/x.py`
      Then the guard denies, naming "`git add <paths>` stages the same changes"

    Scenario: -A with paths is denied where $HOME is the linked worktree
      Given a linked worktree "{TMP}/home" of the repository at "{TMP}/repo"
      And HOME is "{TMP}/home"
      And the working directory is "{TMP}/home"
      When the agent runs `git add -A src/x.py`
      Then the guard denies

    Scenario: -A with paths passes in a repo in the session's scratchpad
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
      And a git repository at "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/r"
      And the working directory is "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/r"
      When the agent runs `git add -A src/x.py`
      Then the guard is silent

    Scenario: -A with paths is denied in another session's scratchpad repo
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
      And the directory "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
      And a git repository at "{TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/r"
      And the working directory is "{TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/r"
      When the agent runs `git add -A src/x.py`
      Then the guard denies

  # The rebase case: a branch's worktree reset to its own remote head. "Own" is
  # origin/<the branch checked out>, read from git; a branch whose upstream is
  # set to another name is not resetting to its own. The tree must be clean, as
  # for a bare discard, and the reset must run on its own.
  Rule: where an agent works, `git reset --hard origin/<current branch>` passes on a clean tree

    Background:
      Given a clone of "https://example.com/r.git" at "{TMP}/repo" on branch "main"
      And a linked worktree "{TMP}/repo/.claude/worktrees/feat" of the repository at "{TMP}/repo"
      And the remote HEAD of "{TMP}/repo" points at "feat"

    Scenario Outline: a reset to the branch's own remote passes in a clean linked worktree
      Given the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                            | note                    |
        | git reset --hard origin/feat       | no upstream set         |
        | git reset -q --hard origin/feat    | -q beside it            |
        | git reset --hard origin/feat -q    | -q after                |

    Scenario: a reset to the branch's own remote passes when the branch tracks it
      Given the branch "feat" of "{TMP}/repo" tracks "origin/feat"
      And the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `git reset --hard origin/feat`
      Then the guard is silent

    Scenario Outline: a reset to a ref stays denied in a clean linked worktree when it is not the branch's own
      Given the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                         | note                                  |
        | git reset --hard origin/main                    | another branch's remote               |
        | git reset --hard origin/feat~1                  | not the remote head itself            |
        | git reset --hard origin/feat && git log -1      | a second git: not on its own          |
        | cd {TMP}/repo/.claude/worktrees/feat && git reset --hard origin/feat | a cd moves the tree |
        | git -C {TMP}/repo reset --hard origin/feat      | -C names another tree                 |
        | git reset --hard --recurse-submodules origin/feat | an option the guard does not weigh  |

    Scenario: a reset to the branch's own remote is denied when the branch tracks another name
      Given the branch "feat" of "{TMP}/repo" tracks "origin/main"
      And the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `git reset --hard origin/feat`
      Then the guard denies

    Scenario: a reset to the branch's own remote is denied on a dirty tree
      Given the file "{TMP}/repo/.claude/worktrees/feat/notes.txt" holds:
        """
        work in progress
        """
      And the working directory is "{TMP}/repo/.claude/worktrees/feat"
      When the agent runs `git reset --hard origin/feat`
      Then the guard denies, naming "on a clean tree"

    Scenario: a reset to the branch's own remote is denied in a repo's main checkout
      Given a clone of "https://example.com/r.git" at "{TMP}/main" on branch "feat"
      And the working directory is "{TMP}/main"
      When the agent runs `git reset --hard origin/feat`
      Then the guard denies

    Scenario: a reset to the branch's own remote is denied where $HOME is the linked worktree
      Given a linked worktree "{TMP}/home" of the repository at "{TMP}/repo"
      And the remote HEAD of "{TMP}/repo" points at "home"
      And HOME is "{TMP}/home"
      And the working directory is "{TMP}/home"
      When the agent runs `git reset --hard origin/home`
      Then the guard denies

    Scenario: a reset to the branch's own remote passes in a repo in the session's scratchpad
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
      And a clone of "https://example.com/r.git" at "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/r" on branch "feat"
      And the working directory is "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/r"
      When the agent runs `git reset --hard origin/feat`
      Then the guard is silent

  Scenario: a command that is not a string is judged as the JSON text it prints as
    When the payload is:
      """
      {"tool_name": "Bash", "tool_input": {"command": ["git add -A"]}}
      """
    Then the guard denies
