@python
Feature: no-bypass-labels
  A label that waives a CI gate is a human's to apply, never a session's: a
  gate whose bypass the gated party can apply to its own PR is not a gate.
  The labels are the bypass_labels option, comma-separated, by default
  churn-ok (the churn gate) and mixed-loops-ok (the mixed-loops gate). They
  are matched case-insensitively, as GitHub matches label names, and denied
  in every repo, public or private. Three routes reach a label: gh's flags
  (also stored by gh alias), gh api, and an MCP tool's labels field. The gh
  is found through wrappers, sh -c, eval, a pipe into a shell and a heredoc
  fed to a shell, which is code; a heredoc fed to anything else is text. A
  label named in text is not a label applied. The option is a list of names,
  matched literally, never a pattern.

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
        | gh pr create -t t -b b -l=churn-ok                    | churn-ok       |
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
        | eval "gh pr edit 12 --add-label churn-ok"                    |
        | env gh pr edit 12 --add-label churn-ok                       |
        | command gh pr edit 12 --add-label churn-ok                   |
        | exec gh pr edit 12 --add-label churn-ok                      |
        | nohup gh pr edit 12 --add-label churn-ok &                   |
        | echo "gh pr edit 12 --add-label churn-ok" \| sh              |
        | echo 12 \| xargs gh pr edit --add-label churn-ok             |
        | gh pr edit --add-label churn-ok                              |
        | gh pr edit 12 --add-label churn"-ok"                         |
        | gh pr edit 12 --add-label 'churn'-ok                         |
        | gh pr edit 12 --add-label churn\-ok                          |
        | gh pr edit 12 --add-label churn-ok 2>/dev/null               |

    Scenario Outline: a heredoc fed to a shell is code
      When the agent runs:
        """
        <shell>
        gh pr edit 12 --add-label churn-ok
        EOF
        """
      Then the guard denies, naming "churn-ok"

      Examples:
        | shell                 |
        | bash <<'EOF'          |
        | sh <<EOF              |
        | cat <<EOF \| sh       |
        | cat <<'EOF' \|& bash  |
        | cat <<EOF \| tee l \| sh |
        | (cat <<EOF) \| sh     |

    Scenario: a heredoc fed to a shell and built at run time cannot be read
      When the agent runs:
        """
        bash <<EOF
        gh pr edit 12 --add-label $L
        EOF
        """
      Then the guard denies, naming "built at run time"

  Rule: an alias that stores a bypass label is applying it, later

    Scenario Outline: gh alias set and import
      When the agent runs `<command>`
      Then the guard denies, naming "<why>"

      Examples:
        | command                                                  | why         |
        | gh alias set lbl 'pr edit $1 --add-label churn-ok'       | churn-ok    |
        | gh alias set --shell waive 'gh pr edit "$1" -l CHURN-OK' | churn-ok    |
        | gh alias import aliases.yml                              | aliases.yml |

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
        | gh api repos/o/r/issues/12/labels -f labels=churn-ok                      | churn-ok       |
        | gh api -X POST repos/o/r/issues/12/labels -f labels[]=churn-ok            | churn-ok       |
        | gh api -X PUT repos/o/r/issues/12/labels -f labels[]="churn-ok "          | churn-ok       |
        | gh api repos/o/r/issues/12/labels -f=labels[]=churn-ok                    | churn-ok       |
        | gh api -X=PUT repositories/1/issues/12/labels -f labels[]=churn-ok        | churn-ok       |

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
      When the agent runs `gh api repositories/1/issues/12/labels --input labels.json`
      Then the guard denies, naming "churn-ok"
      When the agent runs `gh api -X PATCH some/path/the/guard/does/not/know --input labels.json`
      Then the guard denies, naming "churn-ok"
      When the agent runs `gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json`
      Then the guard is silent

    Scenario Outline: a file another command in the call could rewrite first is not read
      Given a project directory
      And the working directory is "{PROJ}"
      And the file "ready.json" holds:
        """
        ["ready"]
        """
      When the agent runs `<command>`
      Then the guard denies, naming "rewrite"

      Examples:
        | command                                                                                                 |
        | echo '{"labels":["churn-ok"]}' > {PROJ}/ready.json && gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json |
        | cp x.json {PROJ}/ready.json; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json               |
        | sh -c 'echo churn-ok > {PROJ}/ready.json && gh api repos/o/r/issues/12/labels -F labels[]=@{PROJ}/ready.json' |
        | sh -c "$(cat /tmp/w.sh)"; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json                   |
        | bash /tmp/w.sh 'cd /tmp'; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json                   |
        | sh -e /tmp/w.sh -c 'cd /tmp'; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json               |
        | source 'cd /tmp'; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json                           |
        | eval 'cd /tmp' "$W"; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json                        |
        | pushd /tmp > {PROJ}/ready.json; gh api repos/o/r/issues/12/labels -F labels[]=@{PROJ}/ready.json       |
        | gh api repos/o/r/contents/p.json -H 'Accept: application/vnd.github.raw' > {PROJ}/ready.json && gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json |
        | gh release download v1 -p p.json -O {PROJ}/ready.json; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json |

    Scenario Outline: a shell running only quoted text leaves the file readable
      Given a project directory
      And the working directory is "{PROJ}"
      And the file "ready.json" holds:
        """
        ["ready"]
        """
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                                  |
        | bash -lc 'cd /tmp' x; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json        |
        | sh -o pipefail -c 'cd /tmp'; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json |
        | eval 'cd /tmp'; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json              |

    Scenario Outline: a file that is not a regular file is not read
      When the agent runs `gh api repos/o/r/issues/12/labels --input <path>`
      Then the guard denies, naming "<why>"

      Examples:
        | path       | why                   |
        | /dev/zero  | not a regular file    |
        | /tmp       | not a regular file    |

    Scenario Outline: a labels payload in a heredoc fed to --input - is read
      When the agent runs:
        """
        gh api <method> repos/o/r/issues/12/labels --input - <<'EOF'
        <payload>
        EOF
        """
      Then the guard denies, naming "mixed-loops-ok"

      Examples:
        | method | payload                        |
        |        | {"labels": ["mixed-loops-ok"]} |
        | -X PUT | ["ready", "Mixed-Loops-OK"]    |

    Scenario: a heredoc payload built at run time cannot be read
      When the agent runs:
        """
        gh api repos/o/r/issues/12/labels --input - <<EOF
        {"labels": ["$L"]}
        EOF
        """
      Then the guard denies, naming "built at run time"

    Scenario Outline: a graphql mutation that applies or renames labels by ID
      Given a project directory
      And the working directory is "{PROJ}"
      And the file "mut.graphql" holds:
        """
        mutation { addLabelsToLabelable(input:{labelableId:"x",labelIds:["y"]}) { clientMutationId } }
        """
      And the file "mut.json" holds:
        """
        {"query": "mutation($ids:[ID!]!) { addLabelsToLabelable(input:{labelableId:\"x\",labelIds:$ids}) { clientMutationId } }", "variables": {"ids": ["y"]}}
        """
      When the agent runs `<command>`
      Then the guard denies, naming "<why>"

      Examples:
        | command                                                                                                     | why         |
        | gh api graphql -f query='mutation { addLabelsToLabelable(input:{labelableId:"x",labelIds:["y"]}) { clientMutationId } }' | label IDs |
        | gh api graphql -f query='mutation($ids:[ID!]!) { addLabelsToLabelable(input:{labelableId:"x",labelIds:$ids}) { clientMutationId } }' -f ids=y | label IDs |
        | gh api graphql -f query='mutation { updateLabel(input:{id:"x",name:"churn-ok"}) { label { id } } }'        | label IDs   |
        | gh api graphql -F query=@mut.graphql                                                                        | label IDs   |
        | gh api graphql --input mut.json                                                                             | label IDs   |
        | gh api graphql -F query=@missing.graphql                                                                    | missing.graphql |

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
        | mcp__github__add_labels                  | {"owner":"o","repo":"r","issue_number":12,"labels":["churn-ok"]}                | churn-ok       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"labels":[{"name":"churn-ok"}]}       | churn-ok       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"labels":["Churn-OK "]}               | churn-ok       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"label":"churn-ok"}                   | churn-ok       |
        | mcp__gitlab__update_issue                | {"project_id":"o/r","issue_iid":12,"add_labels":"churn-ok"}                     | churn-ok       |
        | mcp__some_server__some_tool              | {"labels":["churn-ok"]}                                                         | churn-ok       |
        | mcp__some_server__some_tool              | {"issue":{"labels":["churn-ok"]}}                                               | churn-ok       |
        | mcp__some_server__some_tool              | {"ops":[{"add":{"labels":"churn-ok"}}]}                                         | churn-ok       |
        | mcp__github__add_label                   | {"owner":"o","repo":"r","issue_number":12,"name":"churn-ok"}                    | churn-ok       |
        | mcp__gitea__addIssueLabels               | {"owner":"o","repo":"r","index":3,"value":["churn-ok"]}                         | churn-ok       |

    Scenario Outline: a tool reads only when its name leads with a read verb and says no write; an unknown tool writes
      When the agent calls MCP tool "<tool>" with input `{"owner":"o","repo":"r","labels":["churn-ok"]}`
      Then the guard <verdict>

      Examples:
        | tool                         | verdict                    |
        | mcp__github__get_issue       | is silent                  |
        | mcp__github__list_issues     | is silent                  |
        | mcp__github__search_issues   | is silent                  |
        | mcp__github__read_issue      | is silent                  |
        | mcp__github__issue_write     | denies, naming "churn-ok"  |
        | mcp__github__getting_started | denies, naming "churn-ok"  |
        | mcp__github__get_or_add_labels | denies, naming "churn-ok" |
        | mcp__x__list_and_label       | denies, naming "churn-ok"  |
        | mcp__x__search_then_label    | denies, naming "churn-ok"  |
        | mcp__x__labels_get           | denies, naming "churn-ok"  |
        | mcp__x__get_issue_modify_labels | denies, naming "churn-ok" |
        | mcp__x__list_issue_tag       | denies, naming "churn-ok"  |

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

    Scenario Outline: an MCP labels field that is not a list of names
      When the agent calls MCP tool "mcp__github__update_issue" with input `<input>`
      Then the guard denies, naming "<why>"

      Examples:
        | input                                                        | why      |
        | {"owner":"o","repo":"r","issue_number":12,"labels":5}        | labels   |
        | {"owner":"o","repo":"r","issue_number":12,"labels":[{"x":1}]} | labels   |
        | {"owner":"o","repo":"r","issue_number":12,"labels":[7]}      | labels   |
        | {"owner":"o","repo":"r","issue_number":12,"labelIds":["x"]}  | labelIds |
        | {"owner":"o","repo":"r","issue_number":12,"label_ids":[7]}   | by ID    |

  Rule: renaming a label into a bypass label is applying it

    Scenario Outline: every issue and PR that carries the old name gets the bypass
      When the agent runs `<command>`
      Then the guard denies, naming "churn-ok"

      Examples:
        | command                                                     |
        | gh label edit ready --name churn-ok                         |
        | gh label edit ready -n CHURN-OK -R o/r                      |
        | gh label edit ready -n=churn-ok                             |
        | gh api -X PATCH repos/o/r/labels/ready -f new_name=churn-ok |

  Rule: a label named in text, a read, or another label is not a bypass applied

    Scenario Outline: text, a read, a filter or another label is silent
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
        | gh api repos/o/r/issues -X get -f labels=churn-ok                | the method in any case            |
        | gh api repos/o/r/issues --method=GET -f labels=churn-ok          | the method glued on               |
        | gh api repos/o/r/issues/12/labels -f labels[]=@label.txt         | -f never reads a file: a literal  |
        | gh api repos/o/r/issues/12/labels -f 'labels=["churn-ok"]'       | a string, not an array: no label  |
        | gh api -X DELETE repos/o/r/issues/12/labels/churn-ok             | taking a bypass off               |
        | gh api repos/o/r/labels -f name=churn-ok                         | creating it applies it to nothing |
        | gh api graphql -f query='query { repository(owner:"o",name:"r") { labels(first:10) { nodes { name } } } }' | a graphql read |
        | gh api graphql -f query='mutation { createLabel(input:{name:"churn-ok",repositoryId:"x",color:"fff"}) { label { id } } }' | creating it through graphql |
        | gh alias set co 'pr checkout $1'                                 | an alias that applies no label    |
        | gh api repos/o/r/issues/12/labels -f labels[]=ready              | an unrelated label through gh api |
        | gh api repos/o/r/issues/12/comments -f body="needs churn-ok"     | named in a comment through gh api |
        | ls -la                                                           | no gh at all                      |

    Scenario Outline: a label named in a heredoc body is text
      When the agent runs:
        """
        <command> <<EOF
        Needs a human to run gh pr edit --add-label churn-ok.
        EOF
        """
      Then the guard is silent

      Examples:
        | command                   |
        | gh pr create -t t -F -    |
        | cat > NOTES.md            |
        | python3 -                 |

    Scenario: a heredoc fed to a non-shell is text though another line runs a shell
      When the agent runs:
        """
        python3 - <<'PY'
        "$(x "gh pr edit 12 --add-label churn-ok")"
        PY
        bash t.sh
        """
      Then the guard is silent

    Scenario Outline: a heredoc piped to a non-shell is text though the line runs a shell
      When the agent runs:
        """
        <line>
        gh pr edit 12 --add-label churn-ok
        EOF
        """
      Then the guard is silent

      Examples:
        | line                          |
        | cat <<EOF \| grep gh          |
        | cat <<EOF; echo hi \| sh      |
        | cat <<EOF \|\| sh             |
        | sh -c true \| cat <<EOF       |

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
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labels":[]}                |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labels":null}              |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labelIds":[]}              |
        | mcp__x__update_issue                 | {"owner":"o","repo":"r","issue_number":12,"valid_labels":["ready"]}   |
        | mcp__x__update_issue                 | {"owner":"o","repo":"r","guidelines_labels":["ready"]}                |
        | mcp__github__add_label               | {"owner":"o","repo":"r","issue_number":12,"name":"ready"}             |

    Scenario: a tool that is neither Bash nor MCP is silent
      When the agent calls tool "Write" with input `{"file_path":"/tmp/x.md","content":"gh pr edit 1 --add-label churn-ok"}`
      Then the guard is silent

  Rule: the labels are a setting, matched literally, and an empty one is the default

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

    Scenario: an unset bypass_labels is the default
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is unset
      When the agent runs `gh pr edit 12 --add-label churn-ok`
      Then the guard denies, naming "churn-ok"

    Scenario Outline: the option is names, never a pattern or code
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "<value>"
      When the agent runs `gh pr edit 12 --add-label '<value>'`
      Then the guard denies, naming "<value>"
      When the agent runs `gh pr edit 12 --add-label <other>`
      Then the guard is silent

      Examples:
        | value           | other    |
        | *               | churn-ok |
        | .*              | churn-ok |
        | a\|b            | a        |
        | a.b             | axb      |
        | $(touch /tmp/x) | x        |
