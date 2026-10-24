@python
Feature: guard-host-availability
  The commands that take the machine down are denied: shutdown, reboot, halt,
  poweroff, the fork-bomb shape, and a systemctl verb that takes the host down
  or stops a service the user's session runs on: ssh, login, dbus, the network
  or the display manager. No agent area makes them safe. Any other service is
  the agent's to stop.

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

  Scenario Outline: taking the host down, or a service the session runs on, with systemctl is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                  | naming                         | note                                  |
      | systemctl reboot                         | systemctl reboot               | the host itself                       |
      | systemctl poweroff                       | systemctl poweroff             | the host itself                       |
      | /usr/bin/systemctl halt                  | systemctl halt                 | by path                               |
      | systemctl isolate rescue.target          | systemctl isolate              | stops every unit the target lacks     |
      | systemctl rescue                         | systemctl rescue               |                                       |
      | systemctl stop sshd                      | systemctl stop sshd            |                                       |
      | sudo systemctl restart ssh.service       | systemctl restart ssh.service  | behind sudo                           |
      | sudo -n systemctl restart sshd           | systemctl restart sshd         | behind sudo with an option            |
      | systemctl stop nginx NetworkManager      | systemctl stop NetworkManager  | among several units                   |
      | systemctl kill systemd-logind            | systemctl kill systemd-logind  |                                       |
      | systemctl try-restart gdm                | systemctl try-restart gdm      | a restart by another name             |
      | systemctl disable --now dbus             | systemctl disable dbus         | disable that also stops               |
      | echo done; systemctl stop sshd           | systemctl stop sshd            | after a ;                             |
      | sh -c "systemctl stop display-manager"   | systemctl stop display-manager | nested text                           |
      | systemctl --root /x reboot               | systemctl reboot               | an option's value before the verb     |
      | systemctl --job-mode replace stop sshd   | systemctl stop sshd            | an option's value before the verb     |
      | systemctl -T reboot                      | systemctl reboot               | a flag that takes no value            |
      | systemctl --what status reboot           | systemctl reboot               | an unknown option before a read verb  |
      | systemctl --root -M stop sshd            | systemctl stop sshd            | -M as an option's value, not a host   |
      | systemctl -p --user stop sshd            | systemctl stop sshd            | --user as an option's value           |
      | systemctl stop 'ssh*'                    | systemctl stop ssh*            | a glob may match a session service    |
      | systemctl restart networking             | systemctl restart networking   | Debian's network service              |
      | systemctl stop sshd.socket               | systemctl stop sshd.socket     | another unit type                     |
      | systemctl stop user@1000.service         | systemctl stop user@1000.service | the user's whole session            |
      | systemctl stop session-3.scope           | systemctl stop session-3.scope | a login session                       |
      | systemctl isolate graphical.target       | systemctl isolate              |                                       |
      | service ssh stop                         | service ssh stop               | the SysV form                         |
      | sudo service networking restart          | service networking restart     | the SysV form behind sudo             |
      | service sshd force-reload                | service sshd force-reload      | every verb in the set                 |
      | service dbus try-restart                 | service dbus try-restart       | every verb in the set                 |
      | service ssh --full-restart               | service ssh --full-restart     | the verb is an option                 |
      | service -v ssh stop                      | service ssh stop               | an option before the unit             |
      | service --full-restart ssh               | service ssh --full-restart     | the verb before the unit              |
      | invoke-rc.d ssh stop                     | invoke-rc.d ssh stop           | the Debian wrapper                    |
      | sudo invoke-rc.d networking restart      | invoke-rc.d networking restart | the Debian wrapper behind sudo        |
      | rc-service sshd restart                  | rc-service sshd restart        | the OpenRC form                       |
      | rc-service -v dbus stop                  | rc-service dbus stop           | the OpenRC form with an option        |
      | /etc/init.d/ssh stop                     | /etc/init.d/ssh stop           | the init script itself                |
      | sudo /etc/init.d/networking restart      | /etc/init.d/networking restart | the init script behind sudo           |
      | /etc/rc.d/init.d/sshd restart            | /etc/rc.d/init.d/sshd restart  | the RHEL init script path             |

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
      | systemctl stop nginx                             | not a service the session runs on              |
      | systemctl restart myapp.service                  | not a service the session runs on              |
      | service nginx stop                               | not a service the session runs on              |
      | service ssh status                               | a verb outside the set on a core unit          |
      | invoke-rc.d nginx stop                           | not a service the session runs on              |
      | rc-service nginx restart                         | not a service the session runs on              |
      | /etc/init.d/nginx stop                           | not a service the session runs on              |
      | /etc/init.d/ssh status                           | a verb outside the set on a core unit          |
      | /etc/rc.d/init.d/nginx stop                      | not a service the session runs on              |
      | systemctl disable sshd                           | disable without --now stops nothing            |
