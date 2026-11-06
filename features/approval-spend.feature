@python @family
Feature: approval spend
  A guard that needs the user's yes only reports it. Languette collects every
  guard's finding, decides, and only when nothing denies the call spends the
  yes, once: one click per command, never two, and no click spent on a command
  another guard denies. Each scenario runs in a fresh git repo, from its top,
  with an empty transcript unless it says otherwise.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"

  Rule: two guards asking about one command spend one click

    Scenario: ask-first and guard-infra ask for the same label
      Given the file ".languette/ask-first.json" holds:
        """
        {"commands": [{"id": "kubectl-delete",
          "match": [{"cmd": "kubectl", "args": ["delete"]}],
          "cost": "deletes cluster objects",
          "approve_label": "Run kubectl delete"}]}
        """
      And the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `kubectl delete pod web`?", "header": "Delete", "multiSelect": false, "options": [{"label": "Run kubectl delete", "description": ""}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `kubectl delete pod web`?\"=\"Run kubectl delete\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `kubectl delete pod web`
      Then the guard is silent
      And the one approval "toolu_A" is spent, on one call
      When the agent runs it again
      Then the guard denies

    Scenario: ask-first and guard-infra ask for two labels, answered in one question
      Given the file ".languette/ask-first.json" holds:
        """
        {"commands": [{"id": "kubectl-delete",
          "match": [{"cmd": "kubectl", "args": ["delete"]}],
          "cost": "deletes cluster objects",
          "approve_label": "Delete pods"}]}
        """
      And the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `kubectl delete pod web`?", "header": "Delete", "multiSelect": false, "options": [{"label": "Delete pods", "description": ""}, {"label": "Skip", "description": ""}]}, {"question": "Really?", "header": "Infra", "multiSelect": false, "options": [{"label": "Run kubectl delete", "description": ""}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "Your questions have been answered. You can now continue with these answers in mind."}]}, "toolUseResult": {"answers": {"Run `kubectl delete pod web`?": "Delete pods", "Really?": "Run kubectl delete"}}}
        """
      When the agent runs `kubectl delete pod web`
      Then the guard is silent
      And the one approval "toolu_A" is spent, on one call
      When the agent runs it again
      Then the guard denies

  Rule: a command another guard denies spends nothing

    Scenario: an approved command chained with one guard-disks denies
      Given the file ".languette/ask-first.json" holds:
        """
        {"commands": [{"id": "e2e",
          "match": [{"cmd": "npm", "args": ["run", "e2e"]}],
          "cost": "> 40 minutes",
          "approve_label": "Run e2e"}]}
        """
      And the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `npm run e2e` (e2e)?", "header": "Walk", "multiSelect": false, "options": [{"label": "Run e2e", "description": "46 min"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `npm run e2e` (e2e)?\"=\"Run e2e\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `npm run e2e && dd if=/dev/zero of=/dev/sda`
      Then the guard denies, naming "guard-disks"
      And no approval is spent
      When the agent runs `npm run e2e`
      Then the guard is silent
      When the agent runs it again
      Then the guard denies

    Scenario: an issue create guard-sudo denies leaves the human turn's door open
      When the human speaks, opening the door
      And the agent runs `sudo gh issue create -t t -b b`
      Then the guard denies, naming "guard-sudo"
      When the agent runs `gh issue create -t t -b b`
      Then the guard is silent
