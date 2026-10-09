@python
Feature: guard-host-availability
  The commands that take the machine down are denied: shutdown, reboot, halt,
  poweroff, the fork-bomb shape, and a systemctl verb that takes the host down
  or stops a unit the host cannot run without: dbus, login, a login session or
  a run-level target. Nobody runs these but to chaos-test the host, and no
  agent area makes them safe. A service the user depends on, such as ssh, is
  guard-protected-services'.

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

  Scenario Outline: taking the host down, or a unit it cannot run without, with systemctl is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                  | naming                         | note                                  |
      | systemctl reboot                         | systemctl reboot               | the host itself                       |
      | systemctl poweroff                       | systemctl poweroff             | the host itself                       |
      | /usr/bin/systemctl halt                  | systemctl halt                 | by path                               |
      | systemctl isolate rescue.target          | systemctl isolate              | stops every unit the target lacks     |
      | systemctl rescue                         | systemctl rescue               |                                       |
      | systemctl stop dbus                      | systemctl stop dbus            |                                       |
      | sudo systemctl restart dbus.service      | systemctl restart dbus.service | behind sudo                           |
      | sudo -n systemctl restart dbus           | systemctl restart dbus         | behind sudo with an option            |
      | systemctl stop nginx systemd-logind      | systemctl stop systemd-logind  | among several units                   |
      | systemctl kill systemd-logind            | systemctl kill systemd-logind  |                                       |
      | systemctl try-restart dbus-broker        | systemctl try-restart dbus-broker | a restart by another name          |
      | systemctl disable --now dbus             | systemctl disable dbus         | disable that also stops               |
      | echo done; systemctl stop dbus           | systemctl stop dbus            | after a ;                             |
      | sh -c "systemctl stop systemd-logind"    | systemctl stop systemd-logind  | nested text                           |
      | systemctl --root /x reboot               | systemctl reboot               | an option's value before the verb     |
      | systemctl --job-mode replace stop dbus   | systemctl stop dbus            | an option's value before the verb     |
      | systemctl -T reboot                      | systemctl reboot               | a flag that takes no value            |
      | systemctl --what status reboot           | systemctl reboot               | an unknown option before a read verb  |
      | systemctl --root -M stop dbus            | systemctl stop dbus            | -M as an option's value, not a host   |
      | systemctl -p --user stop dbus            | systemctl stop dbus            | --user as an option's value           |
      | systemctl stop 'db*'                     | systemctl stop db*             | a glob may match a core unit          |
      | systemctl stop dbus.socket               | systemctl stop dbus.socket     | another unit type                     |
      | systemctl stop user@1000.service         | systemctl stop user@1000.service | the user's whole session            |
      | systemctl stop session-3.scope           | systemctl stop session-3.scope | a login session                       |
      | systemctl stop multi-user.target         | systemctl stop multi-user.target | a run-level target                  |
      | systemctl isolate graphical.target       | systemctl isolate              |                                       |

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
      | echo systemctl reboot                            |                                                |
      | systemctl start nginx                            | starting adds availability                     |
      | systemctl list-units reboot                      | an argument to another verb                    |
      | systemctl -t service status reboot               | an argument to another verb                    |
      | systemctl stop nginx                             | not a unit the host runs on                    |
      | systemctl restart myapp.service                  | not a unit the host runs on                    |
      | systemctl restart sshd                           | guard-protected-services' to judge             |
      | systemctl stop NetworkManager                    | guard-protected-services' to judge             |
      | systemctl disable dbus                           | disable without --now stops nothing            |
