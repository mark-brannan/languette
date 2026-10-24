@hook @family
Feature: decision record
  With record_decisions on, every hook call appends one JSON line to
  $XDG_STATE_HOME/languette/decisions.jsonl; off, the default, nothing is
  written. The command is kept with its secrets masked unless
  record_raw_commands is on too. tests/test_record.py checks the rest of
  the record's shape. These rows run through the hooks.json command: in
  process, the record's second reading of the command after the verdict
  trips the pipeline's parsed-once check (tests/pipeline_checks.py).

  Background:
    Given the hook is the hooks.json command for "guard-recursive-delete"
    And XDG_STATE_HOME is "{TMP}/state"

  Scenario Outline: each record option, on and off
    Given CLAUDE_PLUGIN_OPTION_RECORD_DECISIONS is "<record>"
    And CLAUDE_PLUGIN_OPTION_RECORD_RAW_COMMANDS is "<raw>"
    When the agent runs `DB_PASSWORD=<password> ls`
    Then the decision record <kept>

    Examples:
      | record | raw   | password         | kept                                                                                     | note            |
      | false  | true  | Zq9kLm2pQ7rXv4Tn | is empty                                                                                 | gitleaks:allow  |
      | true   | false | Zq9kLm2pQ7rXv4Tn | holds the command `{"text": "DB_PASSWORD=<secret> ls", "masked": 1, "programs": ["ls"]}` | gitleaks:allow  |
      | true   | true  | Zq9kLm2pQ7rXv4Tn | holds the command `{"raw": "DB_PASSWORD=Zq9kLm2pQ7rXv4Tn ls"}`                           | gitleaks:allow  |
