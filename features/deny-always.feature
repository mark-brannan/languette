@python
Feature: deny-always
  A command the repo lists in .languette/deny-always.json is denied every
  time, with the reason the list gives. The list is found as ask-first's is;
  its match entries are written as ask-first's. The guard is a rule set alone
  (languette/rules/deny_always.py), read by languette/engine.py. Each
  scenario runs in a fresh git repo, from its top, with CLAUDE_PROJECT_DIR set
  to it, unless it says otherwise.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"

  Scenario: with no list deny-always is silent
    When the agent runs `psql prod`
    Then the guard is silent

  Scenario Outline: a listed command is denied, naming the rule and its reason
    Given the file ".languette/deny-always.json" holds:
      """
      {"rules": [{"id": "prod-db", "match": [{"cmd": "psql", "args": ["prod"]}],
                  "why": "production is reached through the release job."},
                 {"id": "no-terraform", "match": [{"cmd": "terraform"}], "action": "deny",
                  "why": "this repo's infrastructure is applied by CI"},
                 {"id": "no-ansible", "match": [{"cmd": "ansible-playbook", "at": "command"}],
                  "why": "playbooks run from the ops repo"}]}
      """
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                              | verdict                                                     | note                              |
      | psql prod                            | denies, naming "rule `prod-db`"                             |                                   |
      | psql -h db prod                      | denies, naming "the release job. That is the user's"    | one full stop, not two            |
      | sh -c "psql prod"                    | denies, naming "rule `prod-db`"                             | inside sh -c                      |
      | psql staging                         | is silent                                                   |                                   |
      | terraform plan                       | denies, naming "applied by CI"                              | cmd alone forbids the program     |
      | grep terraform notes.md              | is silent                                                   | prose names it, never runs it     |
      | ansible-playbook site.yml            | denies, naming "rule `no-ansible`"                          |                                   |
      | pip install ansible-playbook         | is silent                                                   | at command: an argument passes    |
      | ls \| xargs ansible-playbook         | denies, naming "rule `no-ansible`"                          | behind a program that runs one    |

  Scenario Outline: a list that does not load denies every command, naming the file and the fault
    Given the file ".languette/deny-always.json" holds:
      """
      <file>
      """
    When the agent runs `ls`
    Then the guard denies, naming "<fault>"

    Examples:
      | file                                                                                          | fault                          |
      | {"rules": [                                                                                   | deny-always.json is invalid: not JSON |
      | {"commands": []}                                                                              | the top level must be          |
      | {"rules": [{"id": "x", "match": [{"cmd": "psql"}]}]}                                          | why must be a non-empty string |
      | {"rules": [{"id": "x", "match": [{"cmd": "psql"}], "why": "w", "action": "ask"}]}             | only adds denies               |
      | {"rules": [{"id": "x", "match": [{"cmd": "psql", "at": "anywhere"}], "why": "w"}]}            | at must be "command"           |
      | {"rules": [{"id": "x", "match": {"cmd": "psql"}, "why": "w"}]}                                | match must be a non-empty list |

  Scenario Outline: the option turns deny-always off
    Given the file ".languette/deny-always.json" holds:
      """
      {"rules": [{"id": "prod-db", "match": [{"cmd": "psql", "args": ["prod"]}], "why": "w"}]}
      """
    And CLAUDE_PLUGIN_OPTION_DENY_ALWAYS is "<value>"
    When the agent runs `psql prod`
    Then the guard <verdict>

    Examples:
      | value | verdict                          |
      | false | is silent                        |
      | true  | denies, naming "rule `prod-db`"  |
