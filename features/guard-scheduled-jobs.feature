@python
Feature: guard-scheduled-jobs
  `crontab -r`, which deletes the whole crontab with no undo, is denied.
  Listing the crontab and replacing it from a file pass.

  Scenario Outline: crontab -r is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                         | naming                    | note                                           |
      | crontab -r                      | crontab -r                |                                                |
      | crontab -ir                     | crontab -r                | a short cluster holding r                      |
      | sudo crontab -u bob -r          | crontab -r                |                                                |

  Scenario: the denial names the safe path
    When the agent runs `crontab -r`
    Then the guard denies, naming "say what you need and hand them the exact command"

  Scenario Outline: listing, replacing or naming the crontab passes
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                          | note                                           |
      | crontab -l                                       |                                                |
      | crontab jobs.txt                                 | replacing it is not deleting it                |
      | git commit -m "crontab -r"                       |                                                |

  # The rule file: languette/rules/guard-scheduled-jobs.json, shipped with languette
  # and optional. Its rules add to the defaults above; they never remove one.

  Scenario Outline: with no rule file, the defaults decide as before
    Given the rule file of "guard-scheduled-jobs" is absent
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command     | verdict                         |
      | crontab -r  | denies, naming "crontab -r"     |
      | crontab -l  | is silent                       |

  Scenario Outline: a rule in the file adds to the defaults
    Given the rule file of "guard-scheduled-jobs" holds:
      """
      {"rules": [{"id": "atrm-all", "match": {"cmd": "atrm", "args": ["all"]}, "action": "deny",
                  "why": "it deletes every queued job"}]}
      """
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command      | verdict                                        | note                       |
      | atrm all     | denies, naming "deletes every queued job"      | the file's rule            |
      | crontab -r   | denies, naming "crontab -r"                    | the default still holds    |
      | atrm 3       | is silent                                      |                            |

  Scenario Outline: a rule file that does not load denies every command, naming the file and the fault
    Given the rule file of "guard-scheduled-jobs" holds:
      """
      <file>
      """
    When the agent runs `ls`
    Then the guard denies, naming "<fault>"

    Examples:
      | file                                                                                  | fault                                  |
      | {"rules": [                                                                           | guard-scheduled-jobs.json is invalid: not JSON |
      | {"commands": []}                                                                      | the top level must be                  |
      | {"rules": [{"id": "crontab-wipe", "match": {"cmd": "crontab", "flags": ["l"]}, "action": "deny"}]} | it never replaces one     |
      | {"rules": [{"id": "x", "match": {"cmd": "atrm", "args": ["all"]}, "action": "allow"}]} | action must be "deny"                  |
      | {"rules": [{"id": "x", "match": {"cmd": "atrm"}, "action": "deny"}]}                   | would match every atrm                 |
