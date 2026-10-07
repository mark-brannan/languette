@python @shell
Feature: guard-host-availability
  The commands that take the machine down are denied: shutdown, reboot, halt,
  poweroff and the fork-bomb shape. No agent area makes them safe.

  Scenario Outline: the fork-bomb shape and a power command are denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                         | naming                    | note                                           |
      | :(){ :\|:& };:                  | fork-bomb shape           | the classic                                    |
      | bomb(){ bomb\|bomb& }; bomb     | fork-bomb shape           | any name                                       |
      | f() { f \| f & }; f             | fork-bomb shape           | with whitespace                                |
      | sh -c ':(){ :\|:& };:'          | fork-bomb shape           | nested text                                    |
      | shutdown -h now                 | shutdown                  |                                                |
      | sudo shutdown -r +5             | shutdown                  | behind sudo                                    |
      | /sbin/shutdown now              | shutdown                  | by path                                        |
      | reboot                          | reboot                    |                                                |
      | sudo reboot                     | reboot                    |                                                |
      | sudo -n reboot                  | reboot                    | behind sudo with an option                     |
      | halt                            | halt                      |                                                |
      | poweroff                        | poweroff                  |                                                |
      | sh -c "reboot"                  | reboot                    | nested text                                    |
      | echo done; reboot               | reboot                    | after a ;                                      |

  Scenario: a fork bomb on a later line is still seen
    When the agent runs:
      """
      echo start
      :(){ :|:& };:
      """
    Then the guard denies, naming "fork-bomb shape"

  Scenario: the denial names the safe path
    When the agent runs `reboot`
    Then the guard denies, naming "say what you need and hand them the exact command"

  Scenario Outline: prose that names a power command, and a function that does not fork itself, pass
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                          | note                                           |
      | echo reboot                                      | prose that names a command is not it           |
      | git commit -m "reboot halt shutdown poweroff"    |                                                |
      | grep reboot /var/log/syslog                      |                                                |
      | npm run halt                                     | an argument, not the command                   |
      | man shutdown                                     |                                                |
      | systemctl status reboot.target                   |                                                |
      | f(){ echo hi; }; f                               | a function that does not fork itself           |
      | echo ':(){ :\|:& };:'                            | a quoted mention of the fork bomb              |
      | git commit -m "the bomb :(){ :\|:& };: is denied" |                                               |
