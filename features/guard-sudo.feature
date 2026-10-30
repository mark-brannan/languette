@python
Feature: guard-sudo
  Acting as root is denied: `sudo`, `su`, `doas` and `pkexec`, wherever the
  command runs them. Naming one as another command's argument passes. The
  guard is a rule set alone (languette/rules/guard_sudo.py), read by
  languette/engine.py.

  Scenario Outline: a command run as root is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                                 | naming      | note                                  |
      | sudo apt-get update                     | `sudo`      |                                       |
      | sudo -u postgres psql                   | `sudo`      | an option's value is not the command  |
      | /usr/bin/sudo ls                        | `sudo`      | by its path                           |
      | su -                                    | `su`        |                                       |
      | su -c ls bob                            | `su`        |                                       |
      | doas ls /root                           | `doas`      |                                       |
      | pkexec ls                               | `pkexec`    |                                       |
      | FOO=1 sudo ls                           | `sudo`      | behind an assignment                  |
      | env FOO=1 sudo ls                       | `sudo`      | behind a wrapper                      |
      | nice -n 5 sudo ls                       | `sudo`      | behind a wrapper with a valued option |
      | timeout 5 doas ls                       | `doas`      |                                       |
      | sudo su -                               | `sudo`      |                                       |
      | make && sudo make install               | `sudo`      | the second command of a chain         |
      | printf x \| sudo tee /etc/motd          | `sudo`      | the second command of a pipe          |
      | sh -c "sudo ls"                         | `sudo`      | inside sh -c                          |
      | echo "$(sudo cat /etc/shadow)"          | `sudo`      | inside a command substitution         |

  Scenario: a guard-sudo denial names the safe path
    When the agent runs `sudo ls`
    Then the guard denies, naming "say what you need and hand them the exact command"

  Scenario Outline: naming a root tool without running it passes
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                             | note                                   |
      | apt-get install sudo                | an argument, not the command           |
      | man sudo                            |                                        |
      | which doas                          |                                        |
      | npx cowsay sudo                     | no launcher runs it                    |
      | echo sudo                           |                                        |
      | git commit -m "drop sudo from ci"   |                                        |
      | grep -r pkexec .                    |                                        |
      | ls /etc/sudoers.d                   |                                        |
      | sudoedit-help                       | another program's name                 |
      | ls                                  |                                        |

  Scenario Outline: the option turns guard-sudo off
    Given CLAUDE_PLUGIN_OPTION_GUARD_SUDO is "<value>"
    When the agent runs `sudo ls`
    Then the guard <verdict>

    Examples:
      | value | verdict                    |
      | false | is silent                  |
      | true  | denies, naming "`sudo`"    |
