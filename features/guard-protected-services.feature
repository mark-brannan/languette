@python
Feature: guard-protected-services
  A systemctl stop, restart, kill or disable --now of a service the user's
  machine depends on is denied. The user lists them in protected_services; the
  list starts empty. The services a session runs on, such as ssh, the network
  and the display manager, are guard-host-availability's. Any other service is
  the agent's to stop.

  Scenario Outline: a glob in the unit may match a protected service
    Given CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "postgresql"
    When the agent runs `<command>`
    Then the guard denies

    @also_guard-host-availability
    Examples:
      | command                  | note                |
      | systemctl stop 'post*'   | a glob may match it |

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
      | systemctl stop postgresql       |              | unset: nothing is protected               |
      | systemctl stop nginx            | postgresql   |                                            |
      | systemctl status postgresql     | postgresql   | a read, not a stop                         |
      | systemctl stop wg-quick@wg1     | wg-quick@wg0 | another instance                           |
      | systemctl --user stop postgresql | postgresql  | the user's own manager                     |
      | echo systemctl stop postgresql  | postgresql   | prose that names a command is not it       |

    @also_guard-host-availability
    Examples:
      | command                         | setting      | note                                       |
      | systemctl restart sshd          | postgresql   | guard-host-availability's to judge         |
      | systemctl reboot                | postgresql   | guard-host-availability's to judge         |
      | systemctl stop 'post*'          |              | unset: a glob matches nothing to protect   |
