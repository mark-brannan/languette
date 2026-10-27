@python
Feature: guard-bypass-labels
  A label that waives a CI gate is the user's to apply unless the
  bypass_labels option names it. The option is comma-separated and empty by
  default, so by default the guard allows every command; the scenarios
  below, unless one says otherwise, run with it set to waive-review (the review
  gate) and skip-gate (the CI gate). A named label is matched
  case-insensitively, as GitHub matches label names, and denied in every
  repo, public or private. Three routes reach a label: gh's flags (also
  stored by gh alias), gh api, and an MCP tool's labels field. The gh is
  found through wrappers, sh -c, eval, a pipe into a shell and a heredoc
  fed to a shell, which is code; a heredoc fed to anything else is text. A
  label named in text is not a label applied. The option is a list of names,
  matched literally, never a pattern.

  Background:
    Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "waive-review,skip-gate"

  Rule: a bypass label applied through gh's flags is denied

    Scenario Outline: gh pr and gh issue, create and edit
      When the agent runs `<command>`
      Then the guard denies, naming "<label>"

      Examples:
        | command                                               | label          |
        | gh pr edit 12 --add-label waive-review                    | waive-review       |
        | gh pr edit 12 --add-label WAIVE-REVIEW                    | waive-review       |
        | gh pr edit 12 --label skip-gate                  | skip-gate |
        | gh pr edit 12 --add-label=Skip-Gate              | skip-gate |
        | gh pr create -t t -b b --label waive-review               | waive-review       |
        | gh pr create -t t -b b -l skip-gate              | skip-gate |
        | gh pr create -t t -b b -lwaive-review                     | waive-review       |
        | gh pr create -t t -b b -l=waive-review                    | waive-review       |
        | gh pr new -t t -b b --label waive-review                  | waive-review       |
        | gh issue edit 3 --add-label skip-gate            | skip-gate |
        | gh pr edit 12 --add-label "ready,waive-review"            | waive-review       |
        | gh pr edit 12 --add-label "ready, waive-review"           | waive-review       |
        | gh pr edit 12 --body "x" --add-label 'waive-review'       | waive-review       |
        | gh pr edit 12 --add-label ready --add-label waive-review  | waive-review       |

      @also_guard-github-issues
      Examples:
        | command                                               | label          |
        | gh issue create -t t -b b --label=waive-review            | waive-review       |

    Scenario Outline: the reason says whose label it is, public repo or private
      When the agent runs `gh pr edit 4 -R <repo> --add-label <label>`
      Then the guard denies, naming "human's to apply"

      Examples:
        | repo                                | label          |
        | o/r                                 | waive-review       |
        | you/notes                           | Skip-Gate |

    Scenario Outline: the gh is found however it is reached
      When the agent runs `<command>`
      Then the guard denies, naming "waive-review"

      Examples:
        | command                                                      |
        | cd ~/project && gh pr edit 12 --add-label waive-review           |
        | GH_REPO=o/r gh pr edit 12 --add-label waive-review               |
        | timeout 30 gh pr edit 12 --add-label waive-review                |
        | /usr/bin/gh pr edit 12 --add-label waive-review                  |
        | sh -c "gh pr edit 12 --add-label waive-review"                   |
        | eval "gh pr edit 12 --add-label waive-review"                    |
        | env gh pr edit 12 --add-label waive-review                       |
        | command gh pr edit 12 --add-label waive-review                   |
        | exec gh pr edit 12 --add-label waive-review                      |
        | nohup gh pr edit 12 --add-label waive-review &                   |
        | echo "gh pr edit 12 --add-label waive-review" \| sh              |
        | echo 12 \| xargs gh pr edit --add-label waive-review             |
        | echo 12 \| xargs -I{} gh pr edit {} --add-label waive-review     |
        | echo 12 \| xargs -I{} gh pr edit --title -ok {} --add-label waive-review |
        | gh pr edit --add-label waive-review                              |
        | gh pr edit 12 --add-label waive"-review"                         |
        | gh pr edit 12 --add-label 'waive'-review                         |
        | gh pr edit 12 --add-label waive\-review                          |
        | gh pr edit 12 --add-label waive-review 2>/dev/null               |

      @also_guard-bypass-ruleset
      Examples:
        | command                                                      |
        | bash -c 'git push && gh pr edit 12 --add-label waive-review'     |

    Scenario Outline: a heredoc fed to a shell is code
      When the agent runs:
        """
        <shell>
        gh pr edit 12 --add-label waive-review
        EOF
        """
      Then the guard denies, naming "waive-review"

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
        | gh alias set lbl 'pr edit $1 --add-label waive-review'       | waive-review    |
        | gh alias set --shell waive 'gh pr edit "$1" -l WAIVE-REVIEW' | waive-review    |
        | gh alias import aliases.yml                              | aliases.yml |

  Rule: a bypass label applied through gh api is denied

    Scenario Outline: a labels field on a write
      When the agent runs `<command>`
      Then the guard denies, naming "<label>"

      Examples:
        | command                                                                   | label          |
        | gh api repos/o/r/issues/12/labels -f "labels[]=waive-review" | waive-review       |
        | gh api repos/o/r/issues/12/labels -F 'labels[]=Skip-Gate'            | skip-gate |
        | gh api -X PUT repos/o/r/issues/12/labels --field labels[]=waive-review        | waive-review       |
        | gh api --method PATCH repos/o/r/issues/12 -f labels[]=ready -f labels[]=waive-review | waive-review |
        | gh api /repos/o/r/issues/12/labels --raw-field=labels[]=waive-review          | waive-review       |
        | gh api https://api.github.com/repos/o/r/issues/12/labels -flabels[]=waive-review | waive-review    |
        | gh api repos/o/r/issues/12/labels -f labels=waive-review                      | waive-review       |
        | gh api -X POST repos/o/r/issues/12/labels -f labels[]=waive-review            | waive-review       |
        | gh api -X PUT repos/o/r/issues/12/labels -f labels[]="waive-review "          | waive-review       |
        | gh api repos/o/r/issues/12/labels -f=labels[]=waive-review                    | waive-review       |
        | gh api -X=PUT repositories/1/issues/12/labels -f labels[]=waive-review        | waive-review       |

      @also_guard-github-issues
      Examples:
        | command                                                                   | label          |
        | gh api repos/o/r/issues -f title=t -f body=b -f 'labels[]=waive-review'       | waive-review       |

    Scenario: a labels payload in the file --input names is read
      Given a project directory
      And the working directory is "{PROJ}"
      And the file "labels.json" holds:
        """
        {"labels": ["ready", "Waive-Review"]}
        """
      And the file "ready.json" holds:
        """
        ["ready"]
        """
      When the agent runs `gh api repos/o/r/issues/12/labels --input labels.json`
      Then the guard denies, naming "waive-review"
      When the agent runs `gh api repositories/1/issues/12/labels --input labels.json`
      Then the guard denies, naming "waive-review"
      When the agent runs `gh api -X PATCH some/path/the/guard/does/not/know --input labels.json`
      Then the guard denies, naming "waive-review"
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
        | echo '{"labels":["waive-review"]}' > {PROJ}/ready.json && gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json |
        | cp x.json {PROJ}/ready.json; gh api repos/o/r/issues/12/labels --input {PROJ}/ready.json               |
        | sh -c 'echo waive-review > {PROJ}/ready.json && gh api repos/o/r/issues/12/labels -F labels[]=@{PROJ}/ready.json' |
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
      Then the guard denies, naming "skip-gate"

      Examples:
        | method | payload                        |
        |        | {"labels": ["skip-gate"]} |
        | -X PUT | ["ready", "Skip-Gate"]    |

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
        | gh api graphql -f query='mutation { updateLabel(input:{id:"x",name:"waive-review"}) { label { id } } }'        | label IDs   |
        | gh api graphql -F query=@mut.graphql                                                                        | label IDs   |
        | gh api graphql --input mut.json                                                                             | label IDs   |

      @also_guard-review-threads
      Examples:
        | command                                                                                                     | why         |
        | gh api graphql -F query=@missing.graphql                                                                    | missing.graphql |

  Rule: a bypass label applied through an MCP tool's labels field is denied

    Scenario Outline: the labels field of a write
      When the agent calls MCP tool "<tool>" with input `<input>`
      Then the guard denies, naming "<label>"

      Examples:
        | tool                                     | input                                                                           | label          |
        | mcp__github__update_pull_request         | {"owner":"o","repo":"r","pullNumber":12,"labels":["ready","skip-gate"]}    | skip-gate |
        | mcp__github__update_issue                | {"owner":"you","repo":"notes","issue_number":12,"labels":["Waive-Review"]} | waive-review |
        | mcp__gitea__edit_issue                   | {"owner":"o","repo":"r","index":3,"labels":"ready,waive-review"}                    | waive-review       |
        | mcp__github__add_labels                  | {"owner":"o","repo":"r","issue_number":12,"labels":["waive-review"]}                | waive-review       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"labels":[{"name":"waive-review"}]}       | waive-review       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"labels":["Waive-Review "]}               | waive-review       |
        | mcp__github__update_issue                | {"owner":"o","repo":"r","issue_number":12,"label":"waive-review"}                   | waive-review       |
        | mcp__gitlab__update_issue                | {"project_id":"o/r","issue_iid":12,"add_labels":"waive-review"}                     | waive-review       |
        | mcp__some_server__some_tool              | {"labels":["waive-review"]}                                                         | waive-review       |
        | mcp__some_server__some_tool              | {"issue":{"labels":["waive-review"]}}                                               | waive-review       |
        | mcp__some_server__some_tool              | {"ops":[{"add":{"labels":"waive-review"}}]}                                         | waive-review       |
        | mcp__github__add_label                   | {"owner":"o","repo":"r","issue_number":12,"name":"waive-review"}                    | waive-review       |
        | mcp__gitea__addIssueLabels               | {"owner":"o","repo":"r","index":3,"value":["waive-review"]}                         | waive-review       |

      @also_guard-github-issues
      Examples:
        | tool                                     | input                                                                           | label          |
        | mcp__github__issue_write                 | {"method":"create","owner":"o","repo":"r","title":"t","labels":["waive-review"]}    | waive-review       |
        | mcp__plugin_github_github__create_issue  | {"owner":"o","repo":"r","title":"t","labels":["SKIP-GATE"]}                | skip-gate |

    Scenario Outline: a tool reads only when its name leads with a read verb and says no write; an unknown tool writes
      When the agent calls MCP tool "<tool>" with input `{"owner":"o","repo":"r","labels":["waive-review"]}`
      Then the guard <verdict>

      Examples:
        | tool                         | verdict                    |
        | mcp__github__get_issue       | is silent                  |
        | mcp__github__list_issues     | is silent                  |
        | mcp__github__search_issues   | is silent                  |
        | mcp__github__read_issue      | is silent                  |
        | mcp__github__issue_write     | denies, naming "waive-review"  |
        | mcp__github__getting_started | denies, naming "waive-review"  |
        | mcp__github__get_or_add_labels | denies, naming "waive-review" |
        | mcp__x__list_and_label       | denies, naming "waive-review"  |
        | mcp__x__search_then_label    | denies, naming "waive-review"  |
        | mcp__x__labels_get           | denies, naming "waive-review"  |
        | mcp__x__get_issue_modify_labels | denies, naming "waive-review" |
        | mcp__x__list_issue_tag       | denies, naming "waive-review"  |

  Rule: a label the guard cannot read is denied, saying why

    Scenario Outline: a label built at run time
      When the agent runs `<command>`
      Then the guard denies, naming "<why>"

      Examples:
        | command                                                       | why                  |
        | gh pr edit 12 --add-label "$LABEL"                            | built at run time    |
        | gh pr edit 12 --add-label "$(cat label.txt)"                  | built at run time    |
        | gh api repos/o/r/issues/12/labels -f "labels[]=$L"            | built at run time    |
        | gh api repos/o/r/issues/12/labels -F labels[]=@label.txt      | label.txt            |
        | gh api repos/o/r/issues/12/labels --input missing.json        | missing.json         |
        | gh api repos/o/r/issues/12/labels --input -                   | stdin                |

      @also_guard-github-issues
      Examples:
        | command                                                       | why                  |
        | gh issue create -t t -b b -l "$L"                             | built at run time    |

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
      Then the guard denies, naming "waive-review"

      Examples:
        | command                                                     |
        | gh label edit ready --name waive-review                         |
        | gh label edit ready -n WAIVE-REVIEW -R o/r                      |
        | gh label edit ready -n=waive-review                             |
        | gh api -X PATCH repos/o/r/labels/ready -f new_name=waive-review |

  Rule: a label named in text, a read, or another label is not a bypass applied

    Scenario Outline: text, a read, a filter or another label is silent
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                          | note                              |
        | gh pr create -t t -b "needs waive-review; please add it by hand"     | named in a PR body                |
        | gh pr edit 12 --body "waive-review waived by hand" --title t         | named in an edited body           |
        | git commit -m "say why waive-review is needed"                       | named in a commit message         |
        | echo "gh pr edit 12 --add-label waive-review"                        | prose that quotes the command     |
        | gh pr view 12                                                    | a read                            |
        | gh pr view 12 --json labels                                      | a read of the labels              |
        | gh label list                                                    | a read of the labels              |
        | gh label list --search waive-review                                  | a search                          |
        | gh issue list --label waive-review                                   | a filter, not an edit             |
        | gh pr list --label skip-gate                                | a filter, not an edit             |
        | gh search prs --label waive-review                                   | a filter, not an edit             |
        | gh label create waive-review -d "waive the review gate"               | creating it applies it to nothing |
        | gh pr edit 12 --add-label ready                                  | an unrelated label                |
        | gh pr edit 12 --add-label not-waive-review                           | a different name                  |
        | gh pr edit 12 --remove-label waive-review                            | taking a bypass off               |
        | gh label edit waive-review --name waive-review-legacy                    | renaming a bypass away            |
        | gh api repos/o/r/issues/12/labels                                | a read through gh api             |
        | gh api repos/o/r/issues -X GET -f labels=waive-review                | a filter through gh api           |
        | gh api repos/o/r/issues -X get -f labels=waive-review                | the method in any case            |
        | gh api repos/o/r/issues --method=GET -f labels=waive-review          | the method glued on               |
        | gh api repos/o/r/issues/12/labels -f labels[]=@label.txt         | -f never reads a file: a literal  |
        | gh api repos/o/r/issues/12/labels -f 'labels=["waive-review"]'       | a string, not an array: no label  |
        | gh api -X DELETE repos/o/r/issues/12/labels/waive-review             | taking a bypass off               |
        | gh api repos/o/r/labels -f name=waive-review                         | creating it applies it to nothing |
        | gh api graphql -f query='query { repository(owner:"o",name:"r") { labels(first:10) { nodes { name } } } }' | a graphql read |
        | gh api graphql -f query='mutation { createLabel(input:{name:"waive-review",repositoryId:"x",color:"fff"}) { label { id } } }' | creating it through graphql |
        | gh alias set co 'pr checkout $1'                                 | an alias that applies no label    |
        | gh api repos/o/r/issues/12/labels -f labels[]=ready              | an unrelated label through gh api |
        | ls -la                                                           | no gh at all                      |

      @also_guard-signed-comments
      Examples:
        | command                                                          | note                              |
        | gh pr comment 12 -b "this needs the waive-review label"              | named in a comment                |
        | gh api repos/o/r/issues/12/comments -f body="needs waive-review"     | named in a comment through gh api |

      @also_guard-github-issues
      Examples:
        | command                                                          | note                              |
        | gh issue create -t "add skip-gate to the docs" -b b         | named in a title                  |

    Scenario Outline: a label named in a heredoc body is text
      When the agent runs:
        """
        <command> <<EOF
        Needs a human to run gh pr edit --add-label waive-review.
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
        "$(x "gh pr edit 12 --add-label waive-review")"
        PY
        bash t.sh
        """
      Then the guard is silent

    Scenario Outline: a heredoc piped to a non-shell is text though the line runs a shell
      When the agent runs:
        """
        <line>
        gh pr edit 12 --add-label waive-review
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
        | mcp__github__create_pull_request     | {"owner":"o","repo":"r","title":"t","body":"waive waive-review by hand"}  |
        | mcp__github__list_issues             | {"owner":"o","repo":"r","labels":["waive-review"]}                        |
        | mcp__github__search_issues           | {"query":"label:waive-review","labels":["waive-review"]}                      |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labels":[]}                |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labels":null}              |
        | mcp__github__update_issue            | {"owner":"o","repo":"r","issue_number":12,"labelIds":[]}              |
        | mcp__x__update_issue                 | {"owner":"o","repo":"r","issue_number":12,"valid_labels":["ready"]}   |
        | mcp__x__update_issue                 | {"owner":"o","repo":"r","guidelines_labels":["ready"]}                |
        | mcp__github__add_label               | {"owner":"o","repo":"r","issue_number":12,"name":"ready"}             |

      @also_guard-signed-comments
      Examples:
        | tool                                 | input                                                                 |
        | mcp__github__add_issue_comment       | {"owner":"o","repo":"r","issue_number":12,"body":"needs waive-review"}    |

    Scenario: a tool that is neither Bash nor MCP is silent
      When the agent calls tool "Write" with input `{"file_path":"/tmp/x.md","content":"gh pr edit 1 --add-label waive-review"}`
      Then the guard is silent

  Rule: the labels are a setting, matched literally, and an empty one guards none

    Scenario: bypass_labels names the guarded labels
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "skip-e2e, Waive-Review"
      When the agent runs `gh pr edit 12 --add-label SKIP-E2E`
      Then the guard denies, naming "skip-e2e"
      When the agent runs `gh pr edit 12 --add-label waive-review`
      Then the guard denies, naming "waive-review"
      When the agent runs `gh pr edit 12 --add-label skip-gate`
      Then the guard is silent

    Scenario Outline: an empty or blank bypass_labels guards no label
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "<value>"
      When the agent runs `gh pr edit 12 --add-label skip-gate`
      Then the guard is silent

      Examples:
        | value |
        |       |
        | ,     |
        |  , ,  |

    Scenario: an unset bypass_labels guards no label
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is unset
      When the agent runs `gh pr edit 12 --add-label waive-review`
      Then the guard is silent

    Scenario Outline: an empty bypass_labels allows every route
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is ""
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                  |
        | gh pr create -t t -b b --label waive-review                                  |
        | gh api -X POST repos/o/r/issues/12/labels -f labels[]=waive-review           |
        | gh api repos/o/r/issues/12/labels --input /nonexistent/payload.json      |
        | gh api graphql -f query='mutation { addLabelsToLabelable(input:{}) { clientMutationId } }' |
        | gh pr edit 12 --add-label "$L"                                           |

    Scenario Outline: the option is names, never a pattern or code
      Given CLAUDE_PLUGIN_OPTION_BYPASS_LABELS is "<value>"
      When the agent runs `gh pr edit 12 --add-label '<value>'`
      Then the guard denies, naming "<value>"
      When the agent runs `gh pr edit 12 --add-label <other>`
      Then the guard is silent

      Examples:
        | value           | other    |
        | *               | waive-review |
        | .*              | waive-review |
        | a\|b            | a        |
        | a.b             | axb      |
        | $(touch /tmp/x) | x        |
