@python
Feature: guard-protected-services
  A systemctl stop, restart, kill or disable --now of a service the user's
  machine depends on is denied. The protected_services setting names them;
  unset, they are the services a session reaches the machine through: ssh, the
  network and the display manager. A user who means to stop one of those sets
  a list without it. Any other service is the agent's to stop.

  Scenario Outline: with the setting unset, ssh, the network and the display manager are protected
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                  | naming                         | note                       |
      | systemctl stop sshd                      | systemctl stop sshd            |                            |
      | sudo systemctl restart ssh.service       | systemctl restart ssh.service  | behind sudo                |
      | systemctl stop nginx NetworkManager      | systemctl stop NetworkManager  | among several units        |
      | systemctl try-restart gdm                | systemctl try-restart gdm      | a restart by another name  |
      | systemctl disable --now sshd             | systemctl disable sshd         | disable that also stops    |
      | sh -c "systemctl stop display-manager"   | systemctl stop display-manager | nested text                |
      | systemctl stop sshd.socket               | systemctl stop sshd.socket     | another unit type          |
      | systemctl stop getty@tty1.service        | systemctl stop getty@tty1.service | an instance             |
      | systemctl stop 'ssh*'                    | systemctl stop ssh*            | a glob may match one       |

  Scenario Outline: a service named in protected_services is denied, in any of its unit forms
    Given CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "<setting>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                      | setting                   | note                       |
      | systemctl stop postgresql                    | postgresql                |                            |
      | systemctl stop postgresql.service            | postgresql                |                            |
      | systemctl stop postgresql                    | nginx, postgresql.service |                            |
      | systemctl restart postgresql@16-main.service | postgresql@*              |                            |
      | systemctl stop postgresql@16-main            | postgresql                | an instance of it          |
      | systemctl stop postgresql.socket             | postgresql                | its socket                 |
      | systemctl stop wg-quick@wg0                  | wg-quick@wg0              | one instance, named        |

  Scenario Outline: without a match, a stop is the agent's
    Given CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "<setting>"
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                         | setting      | note                                       |
      | systemctl stop postgresql       |              | unset: the defaults hold, and it is not one |
      | systemctl stop nginx            | postgresql   |                                            |
      | systemctl status postgresql     | postgresql   | a read, not a stop                         |
      | systemctl restart sshd          | postgresql   | a set list replaces the defaults           |
      | systemctl stop wg-quick@wg1     | wg-quick@wg0 | another instance                           |
      | systemctl --user stop postgresql | postgresql  | the user's own manager                     |
      | echo systemctl stop postgresql  | postgresql   | prose that names a command is not it       |
      | systemctl reboot                | postgresql   | guard-host-availability's to judge         |
