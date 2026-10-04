@python
Feature: no-bypass-labels
  A label that waives a CI gate is a human's to apply, never a session's: a
  gate whose bypass the gated party can apply to its own PR is not a gate.
  The labels are the bypass_labels option, comma-separated, by default
  churn-ok (the churn gate) and mixed-loops-ok (the mixed-loops gate). They
  are matched case-insensitively, as GitHub matches label names, and denied
  in every repo, public or private. Three routes reach a label: gh's flags,
  gh api, and an MCP tool's labels field. A label named in text is not a
  label applied.

  Rule: a bypass label applied through gh's flags is denied

    Scenario Outline: gh pr and gh issue, create and edit
      When the agent runs `<command>`
      Then the guard denies, naming "<label>"

      Examples:
        | command                                               | label          |
        | gh pr edit 12 --add-label churn-ok                    | churn-ok       |
        | gh pr edit 12 --add-label CHURN-OK                    | churn-ok       |
        | gh pr edit 12 --label mixed-loops-ok                  | mixed-loops-ok |
        | gh pr edit 12 --add-label=Mixed-Loops-OK              | mixed-loops-ok |
        | gh pr create -t t -b b --label churn-ok               | churn-ok       |
        | gh pr create -t t -b b -l mixed-loops-ok              | mixed-loops-ok |
        | gh pr create -t t -b b -lchurn-ok                     | churn-ok       |
        | gh pr new -t t -b b --label churn-ok                  | churn-ok       |
        | gh issue create -t t -b b --label=churn-ok            | churn-ok       |
        | gh issue edit 3 --add-label mixed-loops-ok            | mixed-loops-ok |
        | gh pr edit 12 --add-label "ready,churn-ok"            | churn-ok       |
        | gh pr edit 12 --add-label "ready, churn-ok"           | churn-ok       |
        | gh pr edit 12 --body "x" --add-label 'churn-ok'       | churn-ok       |
        | gh pr edit 12 --add-label ready --add-label churn-ok  | churn-ok       |

    Scenario Outline: the reason says whose label it is, public repo or private
      When the agent runs `gh pr edit 4 -R <repo> --add-label <label>`
      Then the guard denies, naming "human's to apply"

      Examples:
        | repo                                | label          |
        | o/r                                 | churn-ok       |
        | mark-brannan/claude_prompts_scratch | Mixed-Loops-OK |

    Scenario Outline: the gh is found however it is reached
      When the agent runs `<command>`
      Then the guard denies, naming "churn-ok"

      Examples:
        | command                                                      |
        | cd ~/project && gh pr edit 12 --add-label churn-ok           |
        | GH_REPO=o/r gh pr edit 12 --add-label churn-ok               |
        | timeout 30 gh pr edit 12 --add-label churn-ok                |
        | /usr/bin/gh pr edit 12 --add-label churn-ok                  |
        | sh -c "gh pr edit 12 --add-label churn-ok"                   |
        | bash -c 'git push && gh pr edit 12 --add-label churn-ok'     |

  Rule: a bypass label applied through gh api is denied

    Scenario Outline: a labels field on a write
      When the agent runs `<command>`
      Then the guard denies, naming "<label>"

      Examples:
        | command                                                                   | label          |
        | gh api repos/mark-brannan/dotfiles/issues/12/labels -f "labels[]=churn-ok" | churn-ok       |
        | gh api repos/o/r/issues/12/labels -F 'labels[]=Mixed-Loops-OK'            | mixed-loops-ok |
        | gh api -X PUT repos/o/r/issues/12/labels --field labels[]=churn-ok        | churn-ok       |
        | gh api --method PATCH repos/o/r/issues/12 -f labels[]=ready -f labels[]=churn-ok | churn-ok |
        | gh api repos/o/r/issues -f title=t -f body=b -f 'labels[]=churn-ok'       | churn-ok       |
        | gh api /repos/o/r/issues/12/labels --raw-field=labels[]=churn-ok          | churn-ok       |
        | gh api https://api.github.com/repos/o/r/issues/12/labels -flabels[]=churn-ok | churn-ok    |

    Scenario: a labels payload in the file --input names is read
      Given a project directory
      And the working directory is "{PROJ}"
      And the file "labels.json" holds:
        """
        {"labels": ["ready", "Churn-OK"]}
        """
      And the file "ready.json" holds:
        """
        ["ready"]
        """
      When the agent runs `gh api repos/o/r/issues/12/labels --input labels.json`
      Then the guard denies, naming "churn-ok"
      When the agent runs `gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json`
      Then the guard is silent

    Scenario: a labels payload in a heredoc fed to --input - is read
      When the agent runs:
        """
        gh api repos/o/r/issues/12/labels --input - <<'EOF'
        {"labels": ["mixed-loops-ok"]}
        EOF
        """
      Then the guard denies, naming "mixed-loops-ok"

  Rule: a bypass label applied through an MCP tool's labels field is denied

    Scenario Outline: the labels field of a write
      When the agent calls MCP tool "<tool>" with input `<input>`
      Then the guard denies, naming "<label>"

      Examples:
        | tool                                     | input                                                                           | label          |
        | mcp__github__update_pull_request         | {"owner":"o","repo":"r","pullNumber":12,"labels":["ready","mixed-loops-ok"]}    | mixed-loops-ok |
        | mcp__github__update_issue                | {"owner":"mark-brannan","repo":"claude_prompts_scratch","issue_number":12,"labels":["Churn-OK"]} | churn-ok |
        | mcp__github__issue_write                 | {"method":"create","owner":"o","repo":"r","title":"t","labels":["churn-ok"]}    | churn-ok       |
        | mcp__plugin_github_github__create_issue  | {"owner":"o","repo":"r","title":"t","labels":["MIXED-LOOPS-OK"]}                | mixed-loops-ok |
        | mcp__gitea__edit_issue                   | {"owner":"o","repo":"r","index":3,"labels":"ready,churn-ok"}                    | churn-ok       |

  Rule: a label the guard cannot read is denied, saying why

    Scenario Outline: a label built at run time
      When the agent runs `<command>`
      Then the guard denies, naming "<why>"

      Examples:
        | command                                                       | why                  |
        | gh pr edit 12 --add-label "$LABEL"                            | built at run time    |
        | gh pr edit 12 --add-label "$(cat label.txt)"                  | built at run time    |
        | gh issue create -t t -b b -l "$L"                             | built at run time    |
        | gh api repos/o/r/issues/12/labels -f "labels[]=$L"            | built at run time    |
        | gh api repos/o/r/issues/12/labels -F labels[]=@label.txt      | label.txt            |
        | gh api repos/o/r/issues/12/labels --input missing.json        | missing.json         |
        | gh api repos/o/r/issues/12/labels --input -                   | stdin                |
        | gh api graphql -f query='mutation { addLabelsToLabelable(input:{labelableId:"x",labelIds:["y"]}) { clientMutationId } }' | label IDs |

    Scenario Outline: an MCP labels field that is not a list of names
      When the agent calls MCP tool "mcp__github__update_issue" with input `<input>`
      Then the guard denies, naming "labels"

      Examples:
        | input                                                        |
        | {"owner":"o","repo":"r","issue_number":12,"labels":5}        |
        | {"owner":"o","repo":"r","issue_number":12,"labels":[{"x":1}]} |

  Rule: renaming a label into a bypass label is applying it

    Scenario Outline: every issue and PR that carries the old name gets the bypass
      When the agent runs `<command>`
      Then the guard denies, naming "churn-ok"

      Examples:
        | command                                                     |
        | gh label edit ready --name churn-ok                         |
        | gh label edit ready -n CHURN-OK -R o/r                      |
        | gh api -X PATCH repos/o/r/labels/ready -f new_name=churn-ok |

  Rule: a label named in text, a read, or another label is not a bypass applied

    Scenario Outline: the guard is silent
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                          | note                              |
        | gh pr comment 12 -b "this needs the churn-ok label"              | named in a comment                |
        | gh pr create -t t -b "needs churn-ok; please add it by hand"     | named in a PR body                |
        | gh pr edit 12 --body "churn-ok waived by hand" --title t         | named in an edited body           |
        | gh issue create -t "add mixed-loops-ok to the docs" -b b         | named in a title                  |
        | git commit -m "say why churn-ok is needed"                       | named in a commit message         |
        | echo "gh pr edit 12 --add-label churn-ok"                        | prose that quotes the command     |
        | gh pr view 12                                                    | a read                            |
        | gh pr view 12 --json labels                                      | a read of the labels              |
        | gh label list                                                    | a read of the labels              |
        | gh label list --search churn-ok                                  | a search                          |
        | gh issue list --label churn-ok                                   | a filter, not an edit             |
        | gh pr list --label mixed-loops-ok                                | a filter, not an edit             |
        | gh search prs --label churn-ok                                   | a filter, not an edit             |
        | gh label create churn-ok -d "waive the churn gate"               | creating it applies it to nothing |
        | gh pr edit 12 --add-label ready                                  | an unrelated label                |
        | gh pr edit 12 --add-label not-churn-ok                           | a different name                  |
        | gh pr edit 12 --remove-label churn-ok                            | taking a bypass off               |
        | gh label edit churn-ok --name churn-ok-legacy                    | renaming a bypass away            |
        | gh api repos/o/r/issues/12/labels                                | a read through gh api             |
        | gh api repos/o/r/issues -X GET -f labels=churn-ok                | a filter through gh api           |
        | gh api repos/o/r/issues/12/labels -f labels[]=ready              | an unrelated label through gh api |
        | gh api repos/o/r/issues/12/comments -f body="needs churn-ok"     | named in a comment through gh api |
        | ls -la                                                           | no gh at all                      |

    Scenario: a label named in a heredoc body is text
      When the agent runs:
        """
        gh pr create -t t -F - <<'EOF'
        Needs a human to run gh pr edit --add-label churn-ok.
        EOF
        """
      Then the guard is silent

    Scenario Outline: an MCP call that applies no bypass label
      When the agent calls MCP tool "<tool>" with input `<input>`
      Then the guard is silent

      Examples:
        | tool                                 | input                                                                 |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labels":["ready"]}         |
        | mcp__github__add_issue_comment       | {"owner":"o","repo":"r","issue_number":12,"body":"needs churn-ok"}    |
        | mcp__github__create_pull_request     | {"owner":"o","repo":"r","title":"t","body":"waive churn-ok by hand"}  |
        | mcp__github__list_issues             | {"owner":"o","repo":"r","labels":["churn-ok"]}                        |
        | mcp__github__search_issues           | {"query":"label:churn-ok","labels":["churn-ok"]}                      |

    Scenario: a tool that is neither Bash nor MCP is silent
      When the agent calls tool "Write" with input `{"file_path":"/tmp/x.md","content":"gh pr edit 1 --add-label churn-ok"}`
      Then the guard is silent

  Rule: the labels are a setting, and an empty one is the default

    Scenario: bypass_labels replaces the default list
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "skip-e2e, Churn-OK"
      When the agent runs `gh pr edit 12 --add-label SKIP-E2E`
      Then the guard denies, naming "skip-e2e"
      When the agent runs `gh pr edit 12 --add-label churn-ok`
      Then the guard denies, naming "churn-ok"
      When the agent runs `gh pr edit 12 --add-label mixed-loops-ok`
      Then the guard is silent

    Scenario Outline: an empty or blank bypass_labels is the default, never no labels at all
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "<value>"
      When the agent runs `gh pr edit 12 --add-label mixed-loops-ok`
      Then the guard denies, naming "mixed-loops-ok"

      Examples:
        | value |
        |       |
        | ,     |
        |  , ,  |
