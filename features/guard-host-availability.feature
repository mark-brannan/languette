@python
Feature: guard-host-availability
  The commands that take the machine down are denied: shutdown, reboot, halt,
  poweroff, the fork-bomb shape, and a systemctl verb that stops a host service
  or the host itself. No agent area makes them safe.

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

  Scenario Outline: stopping or restarting a host service is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                  | naming                  | note                                  |
      | systemctl stop nginx                     | systemctl stop          |                                       |
      | sudo systemctl stop nginx.service        | systemctl stop          | behind sudo                           |
      | systemctl restart sshd                   | systemctl restart       |                                       |
      | /usr/bin/systemctl restart docker        | systemctl restart       | by path                               |
      | systemctl --now stop nginx               | systemctl stop          | an option before the verb             |
      | sudo -n systemctl restart sshd           | systemctl restart       | behind sudo with an option            |
      | echo done; systemctl stop nginx          | systemctl stop          | after a ;                             |
      | sh -c "systemctl stop nginx"             | systemctl stop          | nested text                           |
      | systemctl stop a b                       | systemctl stop          | several units                         |
      | systemctl --root /x stop nginx           | systemctl stop          | an option's value before the verb     |
      | systemctl --kill-whom main stop nginx    | systemctl stop          | an option's value before the verb     |
      | systemctl --job-mode replace stop nginx  | systemctl stop          | an option's value before the verb     |
      | systemctl -T stop nginx                  | systemctl stop          | a flag that takes no value            |
      | systemctl --what status stop nginx       | systemctl stop          | an unknown option before a read verb  |
      | systemctl try-restart nginx              | systemctl try-restart   | a restart by another name             |
      | systemctl kill nginx                     | systemctl kill          |                                       |
      | systemctl reboot                         | systemctl reboot        | the host itself                       |
      | systemctl poweroff                       | systemctl poweroff      | the host itself                       |
      | systemctl isolate rescue.target          | systemctl isolate       | stops every unit the target lacks     |

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

  Scenario Outline: prose that names a power command, a read-only or user-level systemctl, and a function that does not fork itself, pass
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
      | systemctl status nginx                           | a read, not a stop                             |
      | systemctl restart --user foo                     | the user's own manager, not the host           |
      | systemctl --user stop foo                        | the user's own manager, not the host           |
      | echo systemctl stop nginx                        | prose that names a command is not it           |
      | git commit -m "systemctl restart sshd"           |                                                |
      | systemctl start nginx                            | starting adds availability                     |
      | systemctl list-units stop                        | an argument to another verb                    |
      | systemctl -t service status restart              | an argument to another verb                    |
