@python
Feature: guard-worktrees
  Which worktrees a session counts as its own, and what the deny tells it to
  do instead. The rule is stated in guard-worktrees-foreign.feature; these
  scenarios run its session-ownership sequences (a record kept per session
  and per subagent, a scratchpad named by the session id), the other
  spellings of reaching in, and the deny's advice, against a throwaway
  repository with real linked worktrees.

  Background:
    Given a git repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/mine" of the repository at "{TMP}/repo"
    And a linked worktree "{TMP}/repo/.claude/worktrees/theirs" of the repository at "{TMP}/repo"
    And the directory "{TMP}/repo/.claude/worktrees/theirs/sub"
    And a git repository at "{TMP}/other-clone"
    And the working directory is "{TMP}/repo/.claude/worktrees/mine"

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
    And a git repository at "{TMP}/yhome"
    And a linked worktree "{TMP}/ywt/theirs" of the repository at "{TMP}/yhome"
    When the agent runs `git -C {TMP}/ywt/theirs status`
    Then the guard denies, naming "git --git-dir={TMP}/yhome/.git worktree add {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/<name>"

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
    And the working directory is "{TMP}/other-clone"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/mine status`
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
