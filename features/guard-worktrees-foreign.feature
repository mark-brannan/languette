@python
Feature: guard-worktrees
  Opt-in: the plugin option guard_worktrees turns this guard on (see
  wiring.feature). A session may not reach into a linked git worktree that is
  not its own, in any command or file edit: that directory belongs to a
  session that may be archived under it. Every scenario runs against a
  throwaway repository with real linked worktrees, because the guard asks git
  what a path is and nothing is assumed from the name.

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
