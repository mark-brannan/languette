@python
Feature: guard-protected-services
  A stop, restart, kill or disable --now of a service the user's machine
  depends on is denied, made with systemctl, the SysV service, invoke-rc.d,
  rc-service or init script, pkill or killall. The user lists them in protected_services; the
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

  Scenario Outline: the same stop made with service, pkill or killall is denied
    Given CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "postgresql"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                         | note                                 |
      | service postgresql stop         |                                      |
      | service postgresql restart      |                                      |
      | sudo service postgresql stop    | behind sudo                          |
      | pkill postgresql                |                                      |
      | pkill -9 postgresql             | a signal flag                        |
      | pkill -f postgresql             | a pattern over command lines         |
      | pkill -f 'postgresql.*16/main'  | a pattern that contains the unit     |
      | pkill -u postgres postgresql    | an option's value is not the pattern |
      | killall postgresql              |                                      |
      | service postgresql try-restart  | systemctl's other stops              |
      | service postgresql --full-restart | a flag that restarts               |
      | pkill -f '[p]ostgresql'         | a regex fails closed                 |
      | pkill 'postgre.ql'              | a regex fails closed                 |
      | killall -9 postgresql           |                                      |
      | killall -s KILL postgresql      |                                      |
      | /usr/bin/pkill -f postgresql    | by path                              |
      | invoke-rc.d postgresql stop     | the Debian wrapper                   |
      | rc-service postgresql stop      | the OpenRC form                      |
      | /etc/init.d/postgresql stop     | the init script itself               |
      | service postgresql force-stop   | a SysV stop                          |
      | pkill -f "postgresql main"      | a quoted pattern with a space        |
      | pkill -f 'postgresql 16'        | a quoted pattern with a space        |
      | pkill -f "postgres -D /var/lib" | a word of the pattern names the unit |
      | pkill -f "bin/postgres -D"      | a part of a path names the unit      |
      | pkill -f "$(cat name)"          | a substitution fails closed          |
      | pkill -f $NAME                  | a variable fails closed              |
      | pkill -f '.*'                   | a regex that matches every name      |
      | pkill -o postgresql             | -o takes no value in pkill           |
      | pkill -c postgresql             | -c takes no value in pkill           |
      | pkill -fu postgres postgresql   | an option's value in a cluster       |
      | pkill -i POSTGRESQL             | case folded                          |
      | killall -I POSTGRESQL           | case folded                          |
      | killall -o 1h postgresql        | -o takes a value in killall          |
      | killall -r '^postgres'          | a regex                              |
      | killall postgres                | a name the unit's name holds         |
      | pkill '^postgres$'              | an anchored pattern                  |
      | pkill -f '^/usr/lib/postgresql' | an anchored path                     |
      | pkill '[^x]ostgresql'           | a negated class                      |
      | pkill -f -- -D.*postgresql      | an operand after -- that looks like an option |

  Scenario Outline: a process pattern that could name a protected service is denied
    Given CLAUDE_PLUGIN_OPTION_PROTECTED_SERVICES is "<setting>"
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command          | setting | note                                   |
      | pkill mysqld     | *sql    | a glob's literal part is in the name   |
      | pkill re         | redis   | a regex that matches part of the name  |

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
      | service nginx stop              | postgresql   | another service                            |
      | service postgresql status       | postgresql   | a read, not a stop                         |
      | service postgresql stop         |              | unset: nothing is protected                |
      | pkill nginx                     | postgresql   |                                            |
      | pkill -f nginx                  | postgresql   |                                            |
      | killall nginx                   | postgresql   |                                            |
      | pkill -u postgres nginx         | postgresql   | a user filter is not the pattern           |
      | killall --user postgres nginx   | postgresql   | a user filter is not the name              |
      | echo pkill postgresql           | postgresql   | prose that names a command is not it       |
      | pkill -f server.js              | postgresql   | a dot in a file name                       |
      | pkill -f app.py                 | postgresql   | a dot in a file name                       |
      | pkill -f /tmp/test.sh           | postgresql   | a path that names no listed unit           |
      | pkill -f "node server.js"       | postgresql   | a quoted pattern that names no listed unit |
      | killall python3.11              | postgresql   | a dot in a process name                    |
      | pkill POSTGRESQL                | postgresql   | case kept without -i                       |
      | killall -i postgresql           | nginx        | -i asks before each kill in killall        |
      | invoke-rc.d nginx stop          | postgresql   | another service                            |
      | /etc/init.d/postgresql status   | postgresql   | a read, not a stop                         |

    @also_guard-host-availability
    Examples:
      | command                         | setting      | note                                       |
      | systemctl restart sshd          | postgresql   | guard-host-availability's to judge         |
      | systemctl reboot                | postgresql   | guard-host-availability's to judge         |
      | systemctl stop 'post*'          |              | unset: a glob matches nothing to protect   |
