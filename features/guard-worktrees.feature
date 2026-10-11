@python
Feature: guard-worktrees
  Opt-in: the plugin option guard_worktrees turns this guard on (see
  wiring.feature). It keeps a session's git work out of two places that are
  not its own, one Rule below for each, each with its own fixture: a $HOME
  that is itself a worktree, and a linked worktree that belongs to another
  session. Which worktrees count as a session's own is decided by a record
  the guard keeps per session.

  A branch switch in $HOME. For a $HOME that is itself a worktree (yadm, a
  bare-repo setup), a checkout or switch there changes the branch every
  shell and session on the machine sees. Every scenario in that Rule runs
  against a fake $HOME that holds a real .git, so the verdict does not
  depend on the machine's own.

  Why. A session that checks a branch out in a $HOME that is itself a
  worktree leaves it checked out for every shell and session on the machine
  until someone checks the old branch back out. Branch work belongs in a
  worktree. Editing files in $HOME is not touched: the guard fires only on a
  `checkout` or `switch`.

  `yadm` and `git` are not symmetric. yadm hardcodes `--work-tree=$HOME` into
  every invocation, so `yadm checkout <branch>` is dangerous from any
  directory, a worktree under $HOME included; any `yadm checkout` or `switch`
  that is not a file-restore is a hit, cwd ignored. Plain git touches $HOME's
  worktree only if the repo it discovers from the cwd (or a `-C`, `--git-dir`
  or `--work-tree` target, flag or inline `GIT_DIR=`/`GIT_WORK_TREE=`)
  resolves to $HOME. That is checked by asking git, not by testing whether
  the path sits textually under $HOME: a nested repo under $HOME stops git's
  upward search at its own `.git`, so a prefix check would wrongly deny it.
  `switch` has no file-restore form, so it denies unconditionally.
  `checkout`'s file-restore forms (`checkout -- <file>`, `checkout <ref> --
  <file>`) stay allowed; `-b` and `-B` count as a branch switch; `checkout .`
  is denied too, since it is no pathspec-restore the guard can single out.

  `checkout` or `switch` is looked for anywhere after the git or yadm command
  word, and `-C`, `--git-dir` and `--work-tree` anywhere in the segment, so
  an unparsed leading option can never push the subcommand out of reach. The
  cost is a false deny on a bare word "checkout" passed as a value to another
  flag, never a false allow; likewise a quoted path value the shell would not
  expand is read as if unquoted, which only ever adds denials. The command
  can move git before it runs (a `cd` or `pushd`, an exported `GIT_DIR`,
  chained `-C`s, which are cumulative as git applies them); each is followed,
  and a `--git-dir` counts when it is $HOME's repo or any repo whose work tree
  is $HOME. It is a gate: a checkout or switch whose directory cannot be
  resolved (a variable, `cd -`, a stale session cwd) is a deny.

  Another session's worktree. A session may not reach into a linked git
  worktree that is not its own, in any command or file edit: that directory
  belongs to a session that may be archived under it. Every scenario in that
  Rule runs against a throwaway repository with real linked worktrees,
  because the guard asks git what a path is and nothing is assumed from the
  name.

  Why (the scar, 2026-09). A session was handed nothing but "continue
  <issue> see <PR>". It found the branch already checked out in a sibling
  worktree, decided that working there with `git -C <that path>` was the
  clean move, and did. When the session that owned that worktree was
  archived, correctly by its own git state, the directory went away under the
  second session mid-turn; it survived only because its commit was already
  pushed. The mistake was treating another session's working directory as a
  place to work. A hand-off carries a branch, an issue and a PR, not a
  directory; everything a leaving session wants handed over is on the remote,
  and reaching into their worktree to get more is racing a process that is
  still running.

  So any path inside a linked worktree other than this session's own is
  refused, in any command, read or write. The alternatives are all local.
  To inspect a branch, `git log|diff|show <branch>` and `git show
  <branch>:<path>`: every worktree of a repo shares its objects and refs. To
  work on a branch, make your own worktree under the scratchpad (or
  EnterWorktree(name=...) in this repo) and `git merge --ff-only <branch>`
  inside it; recovery advice used to say `git checkout <branch>`, which the
  auto-mode classifier denies outright as irreversible local destruction even
  on a clean tree (dotfiles#233). If `--ff-only` fails the histories have
  diverged: report it and stop. Worktree hygiene is the user's, not a
  session's. `EnterWorktree(path=...)` is refused outright: the tool enters
  an existing worktree with no ownership check, and every legitimate use is
  reachable via `name=...` plus a fast-forward merge.

  What counts as foreign: git is asked, nothing is assumed from the path. A
  candidate resolves to a toplevel (`rev-parse --show-toplevel`) that differs
  from this session's own and is a linked worktree (its `.git` is a file, not
  a directory). The second test keeps `~/dotfiles`, $HOME and every other
  clone allowed: those are main worktrees, no session's private space.
  Sibling worktrees sit inside the repo root by path
  (`<repo>/.claude/worktrees/<name>`), so a textual "under my toplevel"
  shortcut would wrongly allow exactly the case this exists for; every
  candidate is asked. One exception, measured not assumed (2026-09-30, 187
  denials over 584 sessions, 25 of them this case): a worktree the session
  created under its own scratchpad. A linked worktree whose canonical
  toplevel has a whole path component equal to the payload's session_id is
  this session's own, wherever the scratchpad lives. No session id means
  nothing newly allowed; a bare `/tmp` never qualifies.

  "This session's own" is sticky (dotfiles#455). The cwd's toplevel alone
  moved: one `cd` into the state repo and the session's own linked worktree
  was foreign, the `cd` back denied, its uncommitted work stranded. So each
  session (and each subagent, keyed on the payload's agent_id) keeps a record
  of its own linked toplevels in a per-session file under TMPDIR, named
  `languette-guard-worktrees.<session>[.<agent>]` and apart from the claude
  plugin's copy: the arrival a call leaves is consumed exactly once, so with
  one shared file whichever copy ran first would spend it and the other would
  deny the session's new worktree. Own is the cwd's toplevel now plus every
  recorded one. A toplevel is recorded only when reached by a route the guard
  vouches for: the first call of the session; the call after
  EnterWorktree(name=...); or a `cd` the guard allowed into a path that did
  not exist yet when checked (`git worktree add X && cd X`). A cwd reached
  any other way (`cd "$VAR"`) is own while the shell stands in it and is
  never recorded, so an unchecked route cannot be laundered into a lasting
  allow. Each record line carries the inode of the worktree's `.git` file, so
  a worktree removed and re-created at that path by someone else is not
  inherited. A record not owned by this user, or a symlink, is ignored; any
  failure to read or write it leaves the rule exactly as strict as the cwd
  alone.

  A `cd` target is checked whatever its spelling, since a chain of one-name
  `cd <name>` once reached any sibling; within one command the scanner
  follows `cd`, and words resolve against where the shell will be and against
  the payload cwd too (the over-approximation, since a subshell's `cd` does
  not outlive it). The word after `-C` is a path whatever its spelling. Prose
  is not a command: a path mentioned inside a quoted string with whitespace
  stays one unresolvable word, and the scanner queues such a string for a
  nested scan only when its segment could execute it, so a commit message or
  card that names a worktree path passes. Known gap, deliberate: redirection
  targets are not words, so `cmd > /other/worktree/file` is not seen; the
  ordinary routes (a cd, a `-C`, an Edit, a `sed -i`, a `cp`) are all words.
  This is a gate: an unreadable payload is a deny.

  What is own, scenario by scenario. The second Rule also runs the
  session-ownership sequences (a record kept per session and per subagent, a
  scratchpad named by the session id), the other spellings of reaching in,
  and the deny's advice: which worktrees a session counts as its own, and
  what the deny tells it to do instead.

  Rule: a branch switch in a $HOME that is itself a worktree is denied

    Background:
      Given HOME is "{TMP}"
      And a git repository at "{TMP}"
      And the directory "{TMP}/subdir"
      And a git repository at "{TMP}/.claude/worktrees/fake-task"
      And a project directory

    Scenario Outline: a branch switch in $HOME is denied
      Given the working directory is "{TMP}"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                          |
        | yadm checkout some-branch                        |
        | git checkout some-branch                         |
        | yadm checkout -b new-branch                      |
        | yadm checkout -B new-branch                      |
        | echo hi && yadm checkout some-branch             |
        | git switch some-branch                           |
        | git switch -c new-branch                         |
        | git switch some-branch --                        |
        | git checkout some-branch --                      |
        | yadm checkout some-branch --                     |
        | yadm checkout some-branch && ls --               |
        | yadm checkout some-branch # --                   |
        | /usr/bin/yadm checkout some-branch               |
        | ./yadm checkout some-branch                      |
        | /usr/bin/git checkout some-branch                |
        | yadm     checkout    some-branch                 |
        | yadm checkout .                                  |

    # yadm hardcodes --work-tree=$HOME into every invocation, so where it is
    # run from does not matter.
    Scenario Outline: yadm ignores the working directory, so it is denied anywhere
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | cwd    | command                          |
        | {PROJ} | yadm checkout some-branch        |
        | /tmp   | yadm checkout some-branch        |
        | {PROJ} | yadm switch some-branch          |
        | /tmp   | sh -c 'yadm checkout some-branch' |
        | /nonexistent | yadm checkout some-branch  |

    Scenario Outline: plain git reaches $HOME's worktree only if git resolves there
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | cwd         | command                                                         |
        | {TMP}/subdir | git checkout some-branch                                       |
        | {PROJ}      | git -C "$HOME" switch some-branch                                |
        | {PROJ}      | git -C "$HOME" checkout some-branch                              |
        | {PROJ}      | git -C $HOME checkout some-branch                                |
        | {PROJ}      | git -C ~ checkout some-branch                                    |
        | {PROJ}      | git -C {TMP} checkout some-branch                                |
        | /tmp        | git --work-tree={TMP} checkout some-branch                       |
        | /tmp        | git --git-dir={TMP}/.git --work-tree={TMP} checkout some-branch  |
        | /tmp        | git --work-tree {TMP} checkout some-branch                       |
        | /tmp        | git --git-dir {TMP}/.git --work-tree {TMP} checkout some-branch  |
        | /tmp        | GIT_DIR={TMP}/.git GIT_WORK_TREE={TMP} git checkout some-branch  |
        | /tmp        | GIT_WORK_TREE={TMP} git checkout some-branch                     |
        | /tmp        | git --namespace=foo --work-tree={TMP} checkout some-branch       |

    # The command can move where git runs before it gets there.
    Scenario Outline: a cd, a chained -C or an exported GIT_DIR that lands in $HOME is denied
      Given the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                                                    |
        | cd ~ && git checkout some-branch                                           |
        | cd {TMP}; git switch some-branch                                           |
        | pushd {TMP}/subdir && git checkout some-branch                             |
        | cd && git checkout some-branch                                             |
        | export GIT_DIR={TMP}/.git; git checkout some-branch                        |
        | git -C {TMP}/.claude/worktrees/fake-task -C ../../.. checkout some-branch  |

    # yadm keeps its repo outside $HOME, with core.worktree pointing back at it.
    Scenario: --git-dir to a repo whose work tree is $HOME is denied
      Given a yadm-style repository at "{TMP}/.local/share/yadm/repo.git" whose work tree is "{TMP}"
      And the working directory is "/tmp"
      When the agent runs `git --git-dir={TMP}/.local/share/yadm/repo.git checkout some-branch`
      Then the guard denies

    # Fails closed: where the guard can't tell which directory git runs in,
    # it denies rather than guess.
    Scenario Outline: a directory the guard can't resolve is denied
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | cwd          | command                                     |
        | /nonexistent | git checkout some-branch                    |
        | {PROJ}       | cd "$SOMEWHERE" && git checkout some-branch |
        | {PROJ}       | cd - && git checkout some-branch            |
        | {PROJ}       | git -C "$SOMEWHERE" -C sub checkout x       |
        | {PROJ}       | cd "$X" && cd sub && git checkout some-branch |

    # A --git-dir or --work-tree that does not resolve pins nothing: it could
    # name $HOME's repo or work tree, so it is a deny like any other directory
    # the guard can't resolve.
    Scenario Outline: a --git-dir or --work-tree that can't be resolved is denied
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | cwd          | command                                                     |
        | {PROJ}       | git --git-dir="$X" checkout some-branch                     |
        | {PROJ}       | git --work-tree="$X" checkout some-branch                   |
        | {PROJ}       | git --work-tree=/nonexistent checkout some-branch           |
        | {PROJ}       | git --git-dir={PROJ}/.git --work-tree="$X" checkout some-branch |
        | {PROJ}       | git --git-dir=nope/.git checkout some-branch                |
        | /nonexistent | git --git-dir=rel/.git checkout some-branch                 |

    # Git is how every answer here is found: without it nothing resolves to
    # $HOME, so the guard denies instead of reading that as "elsewhere".
    Scenario Outline: with no git on PATH a checkout or switch is denied
      Given PATH holds only "sh"
      And CLAUDE_PLUGIN_OPTION_GUARD_WORKTREES_FOREIGN is "false"
      And the working directory is "{PROJ}"
      When the agent runs `<command>`
      Then the guard denies, naming "git is missing"

      Examples:
        | command                          |
        | git checkout some-branch         |
        | git switch some-branch           |
        | git -C {PROJ} checkout -b probe  |

    # A cd replaces the directory git is judged from. The scanner drops
    # subshell parentheses, so the last row is a known false allow; see
    # docs/agent_decisions.md.
    Scenario Outline: a cd away from $HOME is judged from where it lands
      Given the working directory is "{TMP}"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                     |
        | cd {PROJ} && git checkout some-branch                       |
        | cd {TMP}/.claude/worktrees/fake-task && git switch some-branch |
        | (cd {PROJ}); git checkout some-branch                       |

    # A file restore leaves the branch alone. `switch` has no such form.
    Scenario Outline: a file restore is allowed even in $HOME
      Given the working directory is "{TMP}"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                     |
        | yadm checkout -- .npmrc                     |
        | yadm checkout main -- .npmrc                |
        | yadm checkout -- .npmrc && ls               |

    Scenario Outline: git outside $HOME, and nothing pointing back at it, is allowed
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | cwd                           | command                                              |
        | {PROJ}                        | git checkout some-branch                             |
        | {PROJ}                        | git switch some-branch                               |
        | {PROJ}                        | git -C {PROJ} checkout some-branch                   |
        | /tmp                          | git --git-dir={PROJ}/.git checkout some-branch       |
        | /tmp                          | GIT_DIR={PROJ}/.git git checkout some-branch         |
        | {TMP}/.claude/worktrees/fake-task | git checkout some-branch                         |
        | /tmp                          | cd {TMP}/.claude/worktrees/fake-task && git checkout some-branch |
        | /tmp                          | cd {PROJ} && git checkout some-branch                |
        | {PROJ}                        | git -C {TMP}/.claude/worktrees/fake-task checkout -b probe |

    # -C already says where the command runs, so a session that happens to sit
    # in $HOME is not judged for a checkout in an unrelated repo.
    Scenario Outline: -C to an unrelated repo is allowed even when the session sits in $HOME
      Given the working directory is "{TMP}"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                 |
        | git -C {PROJ} checkout -b probe         |
        | git -C {PROJ} switch some-branch        |

    Scenario Outline: a command that is not a checkout is allowed
      Given the working directory is "{TMP}"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                  |
        | yadm status                              |
        | echo 'yadm checkout some-branch'         |
        | git status                               |

  Rule: a session may not reach into a linked worktree that is not its own

    Background:
      Given a git repository at "{TMP}/repo"
      And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
      And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
      And the directory "{TMP}/repo/.claude/worktrees/theirs/sub"
      And a git repository at "{TMP}/other-clone"
      And the working directory is "{TMP}/repo/.claude/worktrees/mine"

    Scenario Outline: reaching into another worktree is denied
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                              |
        | git -C {TMP}/repo/.claude/worktrees/theirs status    |
        | git -C {TMP}/repo/.claude/worktrees/theirs/sub log   |
        | git -C ../theirs status                              |
        | cd {TMP}/repo/.claude/worktrees/theirs && ls         |
        | git --work-tree={TMP}/repo/.claude/worktrees/theirs status |
        | cat {TMP}/repo/.claude/worktrees/theirs/sub/f.txt    |
        | sh -c "cd {TMP}/repo/.claude/worktrees/theirs && ls" |

    Scenario: a .. after a directory that does not exist cannot be resolved, so it is denied
      When the agent runs `cd {TMP}/repo/.claude/worktrees/nope/../theirs && ls`
      Then the guard denies, naming "does not exist"
      When the agent calls tool "Write" with input `{"file_path": "{TMP}/repo/.claude/worktrees/nope/../theirs/f.txt", "content": "x"}`
      Then the guard denies, naming "does not exist"

    Scenario Outline: what is not a private working directory is allowed
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                      |
        | git -C {TMP}/repo status                                     |
        | git -C {TMP}/other-clone status                              |
        | git -C {TMP}/repo/.claude/worktrees/mine status              |
        | git show theirs:sub/f.txt                                    |
        | git log origin/main                                          |
        | ls {TMP}/repo/.claude/worktrees/                             |

    Scenario: a file edit into another worktree is denied, into one's own is not
      When the agent calls tool "Edit" with input `{"file_path": "{TMP}/repo/.claude/worktrees/theirs/sub/f.txt"}`
      Then the guard denies
      When the agent calls tool "Edit" with input `{"file_path": "{TMP}/repo/.claude/worktrees/mine/f.txt"}`
      Then the guard is silent

    Scenario: EnterWorktree by path is denied whatever it names, by name is not
      When the agent calls tool "EnterWorktree" with input `{"path": "{TMP}/repo/.claude/worktrees/mine"}`
      Then the guard denies
      When the agent calls tool "EnterWorktree" with input `{"name": "fresh"}`
      Then the guard is silent

    Scenario: a worktree under the session's own scratchpad is its own
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      When the agent runs `git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status`
      Then the guard is silent

    Scenario: another session's scratchpad worktree is denied
      Given a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      When the agent runs `git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/wt status`
      Then the guard denies

    # Couplings are optional: the scratchpad comes from CLAUDE_CODE_TMPDIR, then
    # TMPDIR, then the state-dir fallback.
    Scenario: the deny names the recipe, with the scratchpad from CLAUDE_CODE_TMPDIR
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And the directory "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
      And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies, naming "git --git-dir={TMP}/repo/.git worktree add {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/<name>"

    # dotfiles#455: a session that ran one cd into another repo was denied every
    # call naming its own worktree, even the cd back.
    Scenario: a cd elsewhere does not lock the session out of its own worktree
      Given the session is "s455"
      When the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
      Then the guard is silent
      When the agent runs `cd {TMP}/repo/.claude/worktrees/mine`
      Then the guard is silent

    Scenario: after that cd, a sibling is still foreign
      Given the session is "s455"
      When the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies

    # dotfiles#455, second half: a cd of one path component was never checked,
    # so a chain of them reached any sibling unseen.
    Scenario Outline: a one-component cd is checked like any other
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | cwd                                | command                                    |
        | {TMP}/repo/.claude/worktrees       | cd theirs                                  |
        | {TMP}/repo/.claude/worktrees       | pushd theirs                               |
        | {TMP}/repo/.claude/worktrees       | git -C theirs status                       |
        | {TMP}/repo                         | cd .claude && cd worktrees && cd theirs    |
        | {TMP}/repo/.claude/worktrees/mine  | cd .. && cat theirs/sub/f.txt              |

    Scenario Outline: a one-component cd that stays out of other worktrees is allowed
      Given the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | cwd                                | command                       |
        | {TMP}/repo                         | cd .claude                    |
        | {TMP}/repo/.claude/worktrees/mine  | cd                            |
        | {TMP}/repo/.claude/worktrees/mine  | cd mine                       |
        | {TMP}/repo/.claude/worktrees       | git commit -m "cd theirs"     |

    # The gate fails closed on what it needs to judge by: the payload's cwd and
    # a $HOME that resolves.
    Scenario: a payload with no working directory is denied
      When the payload is:
        """
        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "s1"}
        """
      Then the guard denies, naming "no working directory"

    Scenario Outline: a $HOME that does not resolve is denied
      Given HOME is "<home>"
      When the agent runs `ls`
      Then the guard denies, naming "$HOME does not resolve"

      Examples:
        | home         |
        | /nonexistent |
        |              |

    # --- other ways of reaching in ------------------------------------------------

    Scenario Outline: other ways of reaching into another worktree are denied
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                                           |
        | GIT_WORK_TREE={TMP}/repo/.claude/worktrees/theirs git status      |
        | sed -i s/a/b/ {TMP}/repo/.claude/worktrees/theirs/sub/f.txt       |
        | echo hi \| tee {TMP}/repo/.claude/worktrees/theirs/sub/new.txt    |
        | git worktree remove {TMP}/repo/.claude/worktrees/theirs           |

    Scenario Outline: the verdict does not depend on where the shell stands
      Given the working directory is "<cwd>"
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies

      Examples:
        | cwd                |
        | {TMP}/repo         |
        | {TMP}/other-clone  |
        | /tmp               |

    Scenario: a path holding a control character still gives a deny
      Given the directory "{TMP}/repo/.claude/worktrees/theirs/tab	dir"
      When the agent runs `ls '{TMP}/repo/.claude/worktrees/theirs/tab	dir'`
      Then the guard denies

    Scenario Outline: a file tool into another worktree is denied, into one's own is not
      When the agent calls tool "<tool>" with input `{"file_path": "{TMP}/repo/.claude/worktrees/theirs/sub/f.txt"}`
      Then the guard denies
      When the agent calls tool "<tool>" with input `{"file_path": "{TMP}/repo/.claude/worktrees/mine/f.txt"}`
      Then the guard is silent

      Examples:
        | tool      |
        | Write     |
        | MultiEdit |

    Scenario: NotebookEdit into another worktree is denied
      When the agent calls tool "NotebookEdit" with input `{"notebook_path": "{TMP}/repo/.claude/worktrees/theirs/sub/nb.ipynb"}`
      Then the guard denies

    Scenario: a tool this guard does not gate is not judged
      When the agent calls tool "Read" with input `{"file_path": "{TMP}/repo/.claude/worktrees/theirs/sub/f.txt"}`
      Then the guard is silent

    Scenario Outline: a one-component cd is checked whatever its flavour
      Given the working directory is "{TMP}/repo/.claude/worktrees"
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                  |
        | cd -P theirs && ls       |
        | sh -c "cd theirs && ls"  |

    # --- the deny's advice --------------------------------------------------------

    Scenario: EnterWorktree by path is refused with a fast-forward as the way to work on a branch
      When the agent calls tool "EnterWorktree" with input `{"path": "{TMP}/repo/.claude/worktrees/theirs"}`
      Then the guard denies, naming "git merge --ff-only <branch>"
      And the guard denies, not naming "git checkout <branch>"

    Scenario: a deny advises the fast-forward, and says why a self-made worktree is foreign
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies, naming "git merge --ff-only theirs"
      And the guard denies, naming "yours only when the command that creates it also"

    Scenario: an unreadable payload is a deny
      When the payload is:
        """
        not json at all
        """
      Then the guard denies

    # --- allowed: no private working directory named -----------------------------

    Scenario Outline: what names no other worktree is allowed
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                 |
        | git log main..theirs                                    |
        | git status --porcelain                                  |
        | cat README.md                                           |
        | cat {TMP}/repo/.claude/worktrees/mine/nothing-here.txt  |
        | git -C "$SOME_DIR" status                               |
        | ls {TMP}/repo/.claude/worktrees/*/                      |
        | cd {TMP}/other-clone                                    |

    Scenario Outline: prose that mentions another worktree's path is not a command
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                     |
        | git commit -m "worktree {TMP}/repo/.claude/worktrees/theirs is stale"       |
        | gh issue comment 1 -b "old work is in {TMP}/repo/.claude/worktrees/theirs"  |
        | echo "see {TMP}/repo/.claude/worktrees/theirs for the old work"             |

    Scenario: cd - names no path, so it is allowed
      When the agent runs `cd -`
      Then the guard is silent

    # --- a worktree under the session's own scratchpad ---------------------------

    Scenario Outline: the session id in the payload decides which scratchpad worktree is its own
      Given the session is "<session>"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/xaaaaaaaa-1111-4222-8333-444444444444/scratchpad/wtx" of the repository at "{TMP}/repo"
      And the working directory is "<cwd>"
      When the agent runs `<command>`
      Then the guard <verdict>

      Examples:
        | session                              | cwd                               | command                                                                                                         | verdict   |
        | aaaaaaaa-1111-4222-8333-444444444444 | {TMP}/repo/.claude/worktrees/mine | cat {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt/f.txt      | is silent |
        | aaaaaaaa-1111-4222-8333-444444444444 | {TMP}/repo/.claude/worktrees/mine | cd {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt && git log  | is silent |
        | aaaaaaaa-1111-4222-8333-444444444444 | {TMP}/repo                        | git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status  | is silent |
        | bbbbbbbb-1111-4222-8333-444444444444 | {TMP}/repo/.claude/worktrees/mine | git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status  | denies    |
        | aaaaaaaa-1111-4222-8333-444444444444 | {TMP}/repo/.claude/worktrees/mine | git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/xaaaaaaaa-1111-4222-8333-444444444444/scratchpad/wtx status | denies    |
        | aaaaaaaa-1111-4222-8333-444444444444 | {TMP}/repo/.claude/worktrees/mine | git -C {TMP}/repo/.claude/worktrees/theirs status                                                              | denies    |

    Scenario: with no session id in the payload, a scratchpad worktree is foreign
      Given the payload carries no session id
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      When the agent runs `git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status`
      Then the guard denies

    Scenario: TMPDIR naming the scratchpad does not stand in for the session id
      Given the payload carries no session id
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      And TMPDIR is "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
      When the agent runs `git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status`
      Then the guard denies

    Scenario: the id in the payload allows its worktree whatever TMPDIR is
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      And the directory "{TMP}/plain-tmp"
      And TMPDIR is "{TMP}/plain-tmp"
      When the agent runs `git -C {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt status`
      Then the guard is silent

    Scenario Outline: a file tool in a scratchpad worktree follows the session id
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/wtb" of the repository at "{TMP}/repo"
      When the agent calls tool "<tool>" with input `{"file_path": "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt/file.txt"}`
      Then the guard is silent
      When the agent calls tool "<tool>" with input `{"file_path": "{TMP}/scratch/claude-tmpdir/claude-1000/proj/bbbbbbbb-1111-4222-8333-444444444444/scratchpad/wtb/file.txt"}`
      Then the guard denies

      Examples:
        | tool  |
        | Edit  |
        | Write |

    Scenario: EnterWorktree by path is denied even for the session's own scratchpad worktree
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And a linked worktree "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt" of the repository at "{TMP}/repo"
      When the agent calls tool "EnterWorktree" with input `{"path": "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/wt"}`
      Then the guard denies

    # --- the recipe the deny prints ----------------------------------------------

    Scenario: following the printed recipe is allowed
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And the working directory is "/tmp"
      When the agent runs `git --git-dir={TMP}/repo/.git worktree add {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/fresh-wt && cd {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/fresh-wt`
      Then the guard is silent

    Scenario: the recipe for a repository whose git dir is not under its work tree names that git dir
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And the directory "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
      And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
      And the directory "{TMP}/yhome"
      And a yadm-style repository at "{TMP}/yadm/repo.git" whose work tree is "{TMP}/yhome"
      And a linked worktree "{TMP}/ywt/theirs" of the repository at "{TMP}/yadm/repo.git"
      When the agent runs `git -C {TMP}/ywt/theirs status`
      Then the guard denies, naming "git --git-dir={TMP}/yadm/repo.git worktree add {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/<name>"

    Scenario: with no CLAUDE_CODE_TMPDIR the recipe finds the scratchpad under the state directory
      Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
      And HOME is "{TMP}/home"
      And the directory "{TMP}/home/.local/state/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
      And CLAUDE_CODE_TMPDIR is unset
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies, naming "worktree add {TMP}/home/.local/state/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/<name>"

    # --- "own" is sticky: dotfiles#455 ----------------------------------------------

    Scenario: a session that left its worktree may reach back into it by every route
      Given the session is "s1"
      When the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `cd {TMP}/repo/.claude/worktrees/mine`
      Then the guard is silent
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
      Then the guard is silent
      When the agent runs `sed -i s/a/b/ {TMP}/repo/.claude/worktrees/mine/x.txt`
      Then the guard is silent
      When the agent calls tool "Edit" with input `{"file_path": "{TMP}/repo/.claude/worktrees/mine/file.txt"}`
      Then the guard is silent

    Scenario: a one-component cd back home from the worktrees directory is allowed
      Given the session is "s1b"
      When the agent runs `git status`
      And the working directory is "{TMP}/repo/.claude/worktrees"
      And the agent runs `cd mine`
      Then the guard is silent

    Scenario: with no session id nothing is remembered
      Given the payload carries no session id
      When the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
      Then the guard denies

    Scenario: a worktree reached by no vouched route is own only while the shell stands in it
      Given the session is "s2"
      When the agent runs `git status`
      And the working directory is "{TMP}/repo/.claude/worktrees/theirs"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard is silent
      When the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies

    Scenario: a worktree the session adds and enters in one command is recorded
      Given the session is "s3"
      When the agent runs `git status`
      And the agent runs `git worktree add -b new3 {TMP}/repo/.claude/worktrees/new3 && cd {TMP}/repo/.claude/worktrees/new3`
      Then the guard is silent
      Given a linked worktree "{TMP}/repo/.claude/worktrees/new3" of the repository at "{TMP}/repo"
      When the working directory is "{TMP}/repo/.claude/worktrees/new3"
      And the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `cd {TMP}/repo/.claude/worktrees/new3`
      Then the guard is silent
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
      Then the guard is silent

    Scenario: a cd that names a sibling which already existed is not recorded
      Given the session is "s3b"
      When the agent runs `git status`
      And the agent runs `cd {TMP}/repo/.claude/worktrees/theirs`
      Then the guard denies

    Scenario: EnterWorktree by name vouches for the worktree the next call stands in
      Given the session is "s4"
      And a linked worktree "{TMP}/repo/.claude/worktrees/ent4" of the repository at "{TMP}/repo"
      When the agent runs `git status`
      And the agent calls tool "EnterWorktree" with input `{"name": "ent4"}`
      Then the guard is silent
      When the working directory is "{TMP}/repo/.claude/worktrees/ent4"
      And the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/ent4 status`
      Then the guard is silent

    Scenario: without the EnterWorktree the same arrival is not vouched for
      Given the session is "s5"
      And a linked worktree "{TMP}/repo/.claude/worktrees/ent4" of the repository at "{TMP}/repo"
      When the agent runs `git status`
      And the working directory is "{TMP}/repo/.claude/worktrees/ent4"
      And the agent runs `git status`
      Then the guard is silent
      When the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/ent4 status`
      Then the guard denies

    Scenario: a subagent keeps a record of its own, apart from its parent's
      Given the session is "s6"
      When the agent runs `git status`
      And the call comes from subagent "agent-1"
      And the working directory is "{TMP}/repo/.claude/worktrees/theirs"
      And the agent runs `git status`
      And the working directory is "{TMP}/other-clone"
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard is silent
      When the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
      Then the guard denies
      When the call comes from the session itself
      And the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
      Then the guard denies
