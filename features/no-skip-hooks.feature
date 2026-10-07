@python
Feature: no-skip-hooks
  A git hook that blocks a commit or push is telling the agent something, and
  skipping the repo's hooks is the user's call, never the agent's. So
  `git commit --no-verify`, `git commit -n` and `git push --no-verify` are
  denied, and run only after the user answered an AskUserQuestion with the
  label "Skip hooks once". One answer allows one run. On push, -n is
  --dry-run, not a way to skip hooks, and passes. yadm counts as git. Each
  scenario runs in a fresh git repo with CLAUDE_PROJECT_DIR set to it and an
  empty transcript, unless it says otherwise.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"

  Scenario: the reason says whose call it is, what to do instead, and how to ask
    When the agent runs `git push --no-verify`
    Then the guard denies, naming "skips this repo's hooks"
    And the guard denies, naming "AskUserQuestion"
    And the guard denies, naming "Skip hooks once"
    And the guard denies, naming "fix what the blocking hook reported"

  Scenario Outline: skipping the hooks is denied however it is spelled
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                      | note                                  |
      | git push --no-verify                         | the plain case                        |
      | git push origin main --no-verify             | flag after the refspec                |
      | git push --no-verify origin main             | flag before the remote                |
      | git push --no-veri                           | an unambiguous prefix                 |
      | git commit --no-verify -m x                  | commit                                |
      | git commit -m x --no-verify                  | flag after the message                |
      | git commit -n -m x                           | -n is --no-verify on commit           |
      | git commit -nm x                             | -n in a cluster                       |
      | git commit -anm x                            | -n in a longer cluster                |
      | git commit -m "a b" --no-verify              | a quoted message before the flag      |
      | git -C /tmp/repo commit -n -m x              | global option with a value            |
      | git -c user.name=x push --no-verify          | global -c                             |
      | git --git-dir=/x/.git push --no-verify       | global option with an attached value  |
      | git --config-env core.hooksPath=X commit --no-verify | global option with a separate value |
      | git --attr-source HEAD commit -n -m x        | global option with a separate value   |
      | yadm commit -n -m x                          | yadm is git                           |
      | yadm push --no-verify                        | yadm is git                           |
      | /usr/bin/git push --no-verify                | git by path                           |
      | sh -c 'git push --no-verify'                 | sh -c nests                           |
      | bash -c "git commit -n -m x"                 | bash -c nests                         |
      | env X=1 git push --no-verify                 | env prefix                            |
      | X=1 git push --no-verify                     | assignment prefix                     |
      | timeout 5m git push --no-verify              | timeout wrapper                       |
      | sudo git commit -n -m x                      | sudo                                  |
      | sh -c 'env X=1 git push --no-verify'         | wrapper inside sh -c                  |
      | git add f && git commit -n -m x              | later in a chain                      |
      | cd /tmp; git push --no-verify                | later in a ; chain                    |
      | echo git push --no-verify \| sh              | echo into a shell                     |

  Scenario Outline: other git commands, and text that merely names the flag, are not skipping hooks
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                             | note                                |
      | git push -n                                         | -n is --dry-run on push             |
      | git push -n origin main                             | --dry-run                           |
      | git push --dry-run                                  | spelled out                         |
      | git push origin main                                | an ordinary push                    |
      | git push -o --no-verify                             | --no-verify is the push option      |
      | git commit -m "never use --no-verify"               | a message that names the flag       |
      | git commit -m '--no-verify'                         | a message that is the flag          |
      | git commit -m -n                                    | a message that is -n                |
      | git commit -m x -m "and git push --no-verify"       | a second message                    |
      | git commit -am "git commit -n"                      | message in a cluster                |
      | git commit -F msg.txt                               | message from a file                 |
      | git commit --message=--no-verify                    | attached message                    |
      | git commit --amend --no-edit                        | --no-edit is not --no-verify        |
      | git commit -s -m x                                  | other short flags                   |
      | git log --no-verify                                 | not commit or push                  |
      | git status -n                                       | not commit or push                  |
      | echo git push --no-verify                           | echo with no shell                  |
      | grep -rn 'git commit -n' docs                       | grep prose                          |
      | cat hooks/pre-push                                  | cat reads a hook                    |
      | sh -c 'git commit -m "no --no-verify here"'         | a message inside sh -c              |
      | npm run lint --no-verify                            | not git                             |

  Scenario: a heredoc commit message that names the flag is text
    When the agent runs:
      """
      git commit -F - <<'EOF'
      Do not push with --no-verify; git commit -n skips hooks.
      EOF
      """
    Then the guard is silent

  Scenario: a command substitution heredoc message that names the flag is text
    When the agent runs:
      """
      git commit -m "$(cat <<'EOF'
      docs: explain git push --no-verify
      EOF
      )"
      """
    Then the guard is silent

  Rule: an approval allows one run

    Scenario: approved once
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push --no-verify`
      Then the guard is silent

    Scenario: approved for push, used on commit -n
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git commit -n -m x`
      Then the guard is silent

    Scenario: approved, then spent on the first call
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push --no-verify`
      And the agent runs it again
      Then the guard denies, naming "0 unspent"

    Scenario: already spent
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      And the approvals already spent are:
        """
        toolu_A
        """
      When the agent runs `git push --no-verify`
      Then the guard denies

    Scenario: second approval after the first is spent
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_B", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      And the approvals already spent are:
        """
        toolu_A
        """
      When the agent runs `git push --no-verify`
      Then the guard is silent

    Scenario: user chose another option
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Fix it\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push --no-verify`
      Then the guard denies

    Scenario: label not exact
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once later\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push --no-verify`
      Then the guard denies

    Scenario: a dry run needs no approval and spends none
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push -n`
      And the agent runs `git push --no-verify`
      Then the guard is silent

    Scenario: ask-first's own label approves nothing here
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Run e2e\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `git push --no-verify`
      Then the guard denies

    Scenario Outline: one approval covers one run
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `<command>`
      Then the guard <verdict>

      Examples:
        | command                                  | verdict                       |
        | git commit -n -m x && git push --no-verify | denies, naming "2 times"      |
        | git push --no-verify; git push --no-verify | denies                        |
        | git commit -n -m x && git push           | is silent                     |
        | sh -c "git push --no-verify"             | is silent                     |

    Scenario Outline: two runs with two approvals
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_B", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                    |
        | git commit -n -m x && git push --no-verify |

    Scenario Outline: a run inside a loop or xargs is denied whatever was approved
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_B", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `git push --no-verify`?", "header": "Hooks", "multiSelect": false, "options": [{"label": "Skip hooks once", "description": "skip once"}, {"label": "Fix it", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "User has answered your questions: \"Run `git push --no-verify`?\"=\"Skip hooks once\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `<command>`
      Then the guard denies, naming "loop"

      Examples:
        | command                                                      |
        | for r in a b; do git push --no-verify $r; done              |
        | echo a b \| xargs -n1 git push --no-verify                   |
        | while true; do git commit -n -m x; done                      |

    Scenario Outline: with the transcript missing, only a skipped hook is denied
      Given the transcript is missing
      When the agent runs `<command>`
      Then the guard <verdict>

      Examples:
        | command              | verdict                                       |
        | git push --no-verify | denies, naming "cannot read the session transcript" |
        | git push             | is silent                                     |
