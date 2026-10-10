Feature: smoke
  The parser ladder's promise to a user, end to end: if the preferred parser
  is not installed, languette falls back to one you have, a command that does
  not parse is still denied, naming the parser that read it, and `languette
  doctor` reads the whole machine: which parser is reading, whether gh is
  signed in, and that the installed hook denies the canary under that PATH.

  Each machine is a PATH holding python3 and exactly the tools named, nothing
  else, plus a HOME where Claude Code lists languette as installed, or not. The hook is require-well-formed's own command string from
  hooks/hooks.json, run under /bin/sh as Claude Code runs it. A pip parser
  comes from a venv named by an environment variable, which CI's smoke job
  builds; unset, its rows skip locally and fail under CI. A pip parser never
  decides (docs/decisions.md, "Parse check"): the awk rung does, and the pip
  parser adds the column.

  A row the ladder cannot keep yet sits under a @known_gap Examples: a strict
  xfail, so CI stays green, goes red the day a fix lands, and the tag comes
  off with the fix.

  Scenario Outline: the doctor on a machine where languette is installed
    Given a machine with <machine>
    And languette is installed as a plugin
    And gh is signed in
    When the doctor runs on that machine
    Then its "Claude Code" row is ✓ matching "plugin cd31356, user scope; \d+ guards on, 0 off"
    And its "gh" row is ✓ matching "^signed in$"
    And its "parse check" row is ✓ matching "^`echo \"unclosed` was denied: <reader>"
    And its "fail-closed" row is ✓ matching "was denied through the hook command as installed"
    And the doctor exits 0
    And its "shell parser" row is <mark> matching "<row>"

    Examples:
      | machine                       | mark | row                                                             | reader  |
      | shfmt and bash                | ✓    | shfmt \d+\.\d+$                                                 | shfmt   |
      | no shfmt but bash             | !    | no shfmt .* on PATH; bash -n checks the parse instead$          | bash -n |
      | neither shfmt nor bash        | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ | awk     |
      | no shfmt but bashlex          | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ | awk     |
      | no shfmt but tree-sitter-bash | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ | awk     |

    @known_gap
    Examples: the doctor does not name a pip parser yet
      | machine                       | mark | row                                                             | reader  |
      | no shfmt but bashlex          | !    | the built-in lexer reads commands.*bashlex                      | awk     |
      | no shfmt but tree-sitter-bash | !    | the built-in lexer reads commands.*tree-sitter-bash             | awk     |

  Scenario Outline: gh changes the doctor's gh row and nothing else
    Given a machine with shfmt and bash
    And languette is installed as a plugin
    And gh is <gh>
    When the doctor runs on that machine
    Then its "gh" row is ! matching "<row>"
    And its "fail-closed" row is ✓ matching "was denied"
    And the doctor exits 0

    Examples:
      | gh            | row                               |
      | signed out    | ^not signed in; the stacked-base  |
      | not installed | ^not installed or not answering;  |

  Scenario: the doctor on a fresh machine, where nothing is installed
    Given a machine with shfmt and bash
    And gh is signed in
    When the doctor runs on that machine
    Then its "Claude Code" row is ✗ matching "^languette is not installed for this directory$"
    And its "fail-closed" row is ✗ matching "^no guard-recursive-delete hook installed"
    And its "shell parser" row is ✓ matching "shfmt"
    And the doctor exits 1

  Scenario Outline: require-well-formed denies an unclosed quote and allows well-formed commands
    Given a machine with <machine>
    When the agent runs `echo 'unclosed` there
    Then the hook denies, read by <reader>
    When the agent runs `echo ok` there
    Then the hook is silent
    When the agent runs `for f in a b; do echo "$f" | grep -q 'a b' && echo $(date); done` there
    Then the hook is silent

    Examples:
      | machine                       | reader                           |
      | shfmt and bash                | shfmt                            |
      | no shfmt but bash             | bash -n                          |
      | neither shfmt nor bash        | awk                              |
      | no shfmt but bashlex          | awk, at 1:15 per bashlex         |
      | no shfmt but tree-sitter-bash | awk, at 1:6 per tree-sitter-bash |
