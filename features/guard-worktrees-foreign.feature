@python @shell
Feature: guard-worktrees
  Opt-in: the plugin option guard_worktrees turns this guard on (see
  wiring.feature). A session may not reach into a linked git worktree that is
  not its own, in any command or file edit: that directory belongs to a
  session that may be archived under it. Every scenario runs against a
  throwaway repository with real linked worktrees, because the guard asks git
  what a path is and nothing is assumed from the name.

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
  # TMPDIR, then the state-dir fallback; claim-stamp.sh from CLAIM_STAMP_BIN.
  Scenario: the deny names the recipe, with the scratchpad from CLAUDE_CODE_TMPDIR
    Given the session is "aaaaaaaa-1111-4222-8333-444444444444"
    And the directory "{TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad"
    And CLAUDE_CODE_TMPDIR is "{TMP}/scratch/claude-tmpdir"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard denies, naming "git --git-dir={TMP}/repo/.git worktree add {TMP}/scratch/claude-tmpdir/claude-1000/proj/aaaaaaaa-1111-4222-8333-444444444444/scratchpad/<name>"

  Scenario: with no claim-stamp.sh at all, the deny is the strict one
    Given CLAIM_STAMP_BIN is "/nonexistent/claim-stamp.sh"
    When the agent runs `git -C {TMP}/repo/.claude/worktrees/theirs status`
    Then the guard denies

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
      | {TMP}/repo/.claude/worktrees       | git commit -m "cd theirs"     |
