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
