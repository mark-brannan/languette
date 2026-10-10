@python
Feature: guard-bypass-ruleset
  An agent runs on the user's credentials, so it can use the user's bypass
  of a branch's rules. A push that lands on the default branch, when GitHub
  says that branch requires a pull request, is denied, and so is
  `gh pr merge --admin`. When GitHub can't answer, the guard asks. gh is a
  stub throughout: unless told otherwise it answers that main on o/r has a
  pull_request rule. The clone's origin is github.com/o/r and its
  origin/HEAD is main; the checked-out branch tracks its own name.

  Background:
    Given the stub "gh" is first on PATH, for a Python guard
    And a clone of "https://github.com/o/r.git" at "{TMP}/r" on branch "claude/topic"
    And the working directory is "{TMP}/r"

  Scenario Outline: a push that lands on a PR-only main is denied
    When the agent runs `<command>`
    Then the guard denies, naming "requires a pull request"

    Examples:
      | command                                       | note                               |
      | git push origin main                          | by name                            |
      | git push origin HEAD:main                     | a refspec                          |
      | git push origin claude/topic:refs/heads/main  | a qualified destination            |
      | git push --all origin                         | every branch, main among them      |
      | git push git@github.com:o/r.git main          | a URL in place of the remote       |
      | cd {TMP}/r && git push origin main            | after a cd                         |
      | git -C {TMP}/r push origin main               | through -C                         |
      | sh -c 'git push origin main'                  | nested in sh -c                    |
      | git pu''sh origin main                        | a subcommand split by quotes       |
      | git pu"sh" origin main                        | a subcommand split by double quotes |
      | git push --al origin                          | an abbreviated --all               |
      | git push --mir origin                         | an abbreviated --mirror            |
      | git push --branch origin                      | an abbreviated --branches          |
      | git push -on origin main                      | -o with an attached value that holds an n |
      | git push origin main && git push origin "$x"  | a clear push, then an unreadable one |
      | git push -n --no-dry-run origin main          | the last of -n and --no-dry-run wins |
      | git push https://GitHub.com/o/r main          | the host in another case           |
      | git push ssh://git@github.com:22/o/r.git main | a URL with a port                  |
      | (cd {TMP}/r && git push origin main)          | a cd inside the push's own subshell |

    @also_guard-git-work-loss
    Examples:
      | command                                       | note                               |
      | git push -u origin +HEAD:main                 | a forced refspec                   |

    @also_guard-bypass-hooks
    Examples:
      | command                                       | note                               |
      | echo ok; git push origin --no-verify main     | after a separator, with a flag     |

  Scenario Outline: main and master are watched even after the agent moves the remote's HEAD
    Given the remote HEAD of "{TMP}/r" points at "zzz"
    When the agent runs `<command>`
    Then the guard denies, naming "requires a pull request"

    Examples:
      | command               |
      | git push origin main  |
      | git push --all origin |

  Scenario: an admin merge is denied without asking GitHub
    When the agent runs `gh pr merge 5 --squash --admin`
    Then the guard denies, naming "--admin"
    And the stub "gh" was not called

  Scenario: an admin merge is denied even when a later push can't be read
    When the agent runs `gh pr merge 5 --admin; git push origin "$b"`
    Then the guard denies, naming "--admin"

  Scenario Outline: what lands elsewhere, or not at all, is not this guard's
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                   | note                                      |
      | git push origin claude/topic              | a branch                                  |
      | git push -u origin HEAD                   | HEAD is the branch                        |
      | git push                                  | the branch's own push destination         |
      | git push origin v1:refs/tags/v1           | a tag                                     |
      | git push --tags origin                    | tags only                                 |
      | git push --dry-run origin main            | a dry run pushes nothing                  |
      | git push -n origin main                   | the short dry run                         |
      | git push origin --delete claude/topic     | a deletion, other guards' to judge        |
      | git push git@gitlab.com:o/r.git main      | not on github.com                         |
      | echo git push origin main                 | text, not a push                          |
      | gh pr merge 5 --squash --auto             | a merge that waits for the rules          |
      | gh api repos/$R/pulls/5                   | a run-time path under a literal api       |
      | gh pr checks 5 -R $R                      | a run-time repo beside a literal pr       |
      | gh issue $verb 5                          | a run-time word under issue, not pr       |
      | gh -R o/r api repos/$R/pulls/5            | a literal repo before a literal api       |

    @also_guard-github-issues
    Examples:
      | command                                   | note                                      |
      | gh api -X POST repos/o/r/issues           | a method value is not a subcommand        |

  Scenario Outline: a variable set to a literal earlier in the line is read as that literal
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                  | verdict                                   | note                                  |
      | B=claude/x && git push -q origin HEAD:$B                 | is silent                                 | set, then &&                          |
      | B=claude/x; git push origin "HEAD:$B"                    | is silent                                 | set, then ;                           |
      | export B=claude/x; git push origin HEAD:${B}             | is silent                                 | exported, read in braces              |
      | B=main; git push origin HEAD:$B                          | denies, naming "requires a pull request"  | main through a variable               |
      | B=claude/x; B=$(gh pr view 32 --json headRefName -q .headRefName); git push origin HEAD:$B | asks | set again at run time |
      | (B=claude/x); git push origin HEAD:$B                    | asks                                      | set in a subshell                     |
      | B=claude/x \| cat; git push origin HEAD:$B               | asks                                      | set in a pipeline                     |
      | false && B=claude/x; git push origin HEAD:$B             | asks                                      | the set may not run                   |
      | B=claude/x git push origin HEAD:$B                       | asks                                      | a prefix set, read before it applies  |
      | B=claude/x; eval "$c"; git push origin HEAD:$B           | asks                                      | eval may set it again                 |
      | B=claude/x; git push origin HEAD:$B$C                    | asks                                      | a second run-time part                |
      | B=claude/x; git push origin HEAD:$'B'                    | asks                                      | ANSI quoting, not a variable          |
      | B=--all; git push origin $B                              | asks                                      | an option, not a refspec              |
      | B=--mirror && git push origin $B                         | asks                                      | the same, --mirror                    |
      | B=claude/x:main; git push origin $B                      | denies, naming "requires a pull request"  | a whole refspec, landing on main      |
      | B=claude/x\ HEAD:main; git push origin HEAD:$B           | asks                                      | splits into a second refspec, on main |
      | B=claude/x\ main && git push origin $B                   | asks                                      | the same, a bare second branch        |

    @also_guard-git-work-loss
    Examples:
      | command                                                  | verdict                                   | note                                  |
      | B=main && git push -u origin +HEAD:"$B"                  | denies, naming "requires a pull request"  | the same, forced                      |

  Scenario: a variable set on an earlier line is read as that literal
    When the agent runs:
      """
      B=main
      git push origin HEAD:$B
      """
    Then the guard denies, naming "requires a pull request"

  Scenario Outline: on main itself, the branch's own push lands on main
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And the working directory is "{TMP}/m"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                |
      | git push               |
      | git push origin HEAD   |
      | git push origin        |

  Scenario Outline: an admin merge through a run-time subcommand is denied
    When the agent runs `<command>`
    Then the guard denies, naming "--admin"

    Examples:
      | command                      |
      | gh pr $m 5 --admin           |
      | p=pr; gh $p merge 5 --admin  |

  Scenario: an admin merge with a split flag is denied
    When the agent runs `gh pr merge 5 --adm''in`
    Then the guard denies, naming "--admin"

  @also_guard-worktrees
  Scenario: a remote URL that climbs out of the slug is not a repository
    When the agent runs `git push https://github.com/../x main`
    Then the guard is silent

  Scenario Outline: GitHub's answer decides
    Given GH_RULES is "<rules>"
    And GH_PROTECTION is "<protection>"
    When the agent runs `git push origin main`
    Then the guard <verdict>

    Examples:
      | rules   | protection | verdict   | note                                            |
      | pr      |            | denies    | a ruleset with a pull_request rule              |
      | none    | reviews    | denies    | classic protection with required reviews        |
      | none    |            | is silent | no rule requires a pull request                 |
      | upgrade |            | is silent | a free private repo can carry no rules          |

  Scenario: GitHub not answering asks the user
    Given GH_FAIL is "1"
    When the agent runs `git push origin main`
    Then the guard asks

  Scenario Outline: a destination the hook can't read asks
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                           | note                                  |
      | git push origin "$b"              | a variable refspec                    |
      | git push origin HEAD:$target      | a variable destination                |
      | GIT_DIR=/x git push origin main   | another repository, unfound           |
      | p=push; git $p origin main        | a subcommand built at run time        |
      | git push "$BASE/repo" main        | a remote built at run time            |
      | git -c alias.p=push p origin main | an alias that makes a push            |
      | git -calias.p=push p origin main  | the same, -c attached                 |
      | git --config-env=alias.p=V p origin main | the same, --config-env attached |
      | git -c url.https://github.com/o/r.insteadOf=foo push foo main | a URL rewrite |
      | gh pr merge 5 "$flags"            | a flag built at run time              |
      | gh $p merge 5                     | a gh subcommand built at run time     |
      | gh pr $v 5                        | a pr subcommand built at run time     |
      | gh -R o/r $p merge 5              | a run-time group behind a repo flag   |
      | gh --repo o/r pr $v 5             | a run-time verb behind a repo flag    |
      | gh -R $R api x                    | a run-time repo value may split into a group |
      | export GIT_DIR=/x; git push origin main | another repository, exported       |

  Scenario Outline: a cd the shell may undo before the push asks
    Given a clone of "https://gitlab.com/o/r.git" at "{TMP}/g" on branch "main"
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                                   | note                              |
      | { cd {TMP}/g; }; git push origin main     | a group                           |
      | cd {TMP}/g \| cat; git push origin main   | a pipeline runs the cd in a subshell |
      | cd {TMP}/g \|\| exit 1; git push origin main | the cd may have failed        |
      | pushd {TMP}/g; popd; git push origin main | a popd                            |

  Scenario: a subshell's cd ends with it, so the push is read where the line started
    Given a clone of "https://gitlab.com/o/r.git" at "{TMP}/g" on branch "main"
    When the agent runs `(cd {TMP}/g && true); git push origin main`
    Then the guard denies, naming "requires a pull request"

  # The next scenarios start on main in {TMP}/m and move to claude/topic in {TMP}/repo,
  # so each verdict says where the push was read: silent in {TMP}/repo, a deny in
  # {TMP}/m, an ask when the directory was lost.

  Scenario Outline: a push after a cd the shell keeps is read in the cd's directory
    Given HOME is "{TMP}"
    And a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command | note |
      | cd ~/repo && git commit -qm msg && git pull -q --rebase --autostash && git push -q origin HEAD && echo pushed | a ~/ path |
      | cd ~/repo && git fetch -q origin main && git rebase origin/main \| tail -1 && git push -qu origin HEAD 2>&1 \| tail -1 | a ~/ path, then a pipe that is not the cd's |
      | S={TMP}; git -C $S/repo add f && git -C $S/repo commit -qm msg && git -C $S/repo push -q -u origin HEAD 2>&1\|tail -2 | -C through a variable set to a literal |
      | cd {TMP}/repo && git fetch -q origin main && git rebase origin/main 2>&1\|tail -1; git push -q -u origin HEAD 2>&1\|tail -2; git log --oneline -1 | a pipe that is not the cd's, then ; |
      | cd {TMP}/repo && git add f && git commit -qm msg && git fetch -q origin main && git rebase -q origin/main && git push -q --force-with-lease 2>&1\|tail -1; git push -q --force-with-lease 2>&1\|tail -1 | no refspec, so @{push}, twice |

  Scenario: a push after a cd across lines, past a heredoc and a pipe, is read in the cd's directory
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs:
      """
      cd {TMP}/repo && python3 - <<'EOF'
      print(1)
      EOF
      python3 t.py 2>&1 | tail -2
      git add f && git commit -qm msg && git fetch -q origin main && git rebase origin/main 2>&1 | tail -1 && git push -q -u origin HEAD 2>&1 | tail -1
      """
    Then the guard is silent

  Scenario: a cd after a command in its and-or list holds for the rest of that list
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `git status && cd {TMP}/repo && git push origin HEAD`
    Then the guard is silent

  Scenario: a bare ~ is HOME
    Given HOME is "{TMP}/repo"
    And a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `cd ~ && git push origin HEAD`
    Then the guard is silent

  Scenario Outline: a cd the shell undoes, or a directory it can't read, never lends the push its branch
    Given HOME is "{TMP}"
    And a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                                                 | note                                     |
      | { cd {TMP}/repo; git status; } && git push origin HEAD  | the cd's group closes                    |
      | cd {TMP}/repo \| cat; git push origin HEAD              | the cd is in the pipeline                |
      | cd {TMP}/repo & git push origin HEAD                    | the cd is backgrounded                   |
      | cd {TMP}/repo && git status & git push origin HEAD      | the cd's and-or list is backgrounded     |
      | cd {TMP}/rep* && git push origin HEAD                   | a glob                                   |
      | cd ~other/repo && git push origin HEAD                  | another user's home                      |
      | cd '~/repo' && git push origin HEAD                     | a quoted ~ is a directory named ~        |
      | echo ~/repo; cd "~/repo"; git push origin HEAD          | the cd's own ~ is quoted, the echo's not |
      | cd \\~/repo && git push origin HEAD                     | an escaped ~ is a directory named ~      |
      | test -d {TMP}/x && cd {TMP}/repo; git push origin HEAD  | the test may skip the cd                 |
      | git status \|\| cd {TMP}/repo && git push origin HEAD   | the push runs when the cd was skipped    |
      | cd {TMP}/nope \|\| cd {TMP}/repo; git push origin HEAD  | the second cd may not run                |

  # The next rows start on claude/topic in {TMP}/repo and cd to main in {TMP}/m, so a cd the
  # guard misses reads silent.

  Scenario Outline: a cd behind a shell keyword moves the commands after it in its body
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/repo"
    When the agent runs `<command>`
    Then the guard denies, naming "requires a pull request"

    Examples:
      | command                                                   | note                     |
      | if true; then cd {TMP}/m; git push origin HEAD; fi        | after then               |
      | if false; then :; else cd {TMP}/m && git push origin HEAD; fi | after else           |
      | ! cd {TMP}/m; git push origin HEAD                        | after !, which only negates the status |
      | if cd {TMP}/m; then git push origin HEAD; fi              | the if's own condition   |

  Scenario Outline: past fi, done or esac, a cd inside an if, a loop or a case leaves the directory unknown
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/repo"
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                                                   | note                                  |
      | if true; then cd {TMP}/m; fi; git push origin HEAD        | the then branch may not have run      |
      | for d in {TMP}/m; do cd $d; done; git push origin HEAD    | the loop may run the cd any number of times |
      | while true; do cd {TMP}/m; break; done; git push origin HEAD | a while loop                       |
      | for d in a b; do git push origin HEAD; cd {TMP}/m; done   | a later pass runs the push after the cd |
      | case x in x) cd {TMP}/m;; esac; git push origin HEAD      | a case arm that ran                   |
      | case x in y) cd {TMP}/m;; esac; git push origin HEAD      | a case arm that did not run           |
      | case x in x) cd {TMP}/m; git push origin HEAD;; esac      | a push in the arm itself              |

  Scenario Outline: a cd in a then branch never lends its directory to the else or elif after it
    Given a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                                                              | note                              |
      | if false; then cd {TMP}/repo; else git push origin HEAD; fi         | the else runs where the if began  |
      | if false; then cd {TMP}/repo; elif true; then git push origin HEAD; fi | so does an elif                 |

  Scenario: a subshell's cd never lends the push its branch
    Given HOME is "{TMP}"
    And a clone of "https://github.com/o/r.git" at "{TMP}/m" on branch "main"
    And a clone of "https://github.com/o/r.git" at "{TMP}/repo" on branch "claude/topic"
    And the working directory is "{TMP}/m"
    When the agent runs `(cd {TMP}/repo && git status) && git push origin HEAD`
    Then the guard denies, naming "requires a pull request"

  Scenario: the answer is cached
    When the agent runs `git push origin main`
    And the agent runs it again
    Then the guard denies
    And the stub "gh" was called 1 times
