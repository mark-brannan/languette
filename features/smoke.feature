Feature: smoke
  The parser ladder's promise to a user, end to end: if the preferred parser
  is not installed, languette falls back to one you have, a command that does
  not parse is still denied, naming the parser that read it, and `languette
  doctor` says which parser is reading, in its "shell parser" row.

  Each machine is a PATH holding python3 and exactly the tools named, nothing
  else. The hook is require-well-formed's own command string from
  hooks/hooks.json, run under /bin/sh as Claude Code runs it. A pip parser
  comes from a venv named by an environment variable, which CI's smoke job
  builds; unset, its rows skip locally and fail under CI. A pip parser never
  decides (docs/decisions.md, "Parse check"): the awk rung does, and the pip
  parser adds the column.

  A row the ladder cannot keep yet sits under a @known_gap Examples: a strict
  xfail, so CI stays green, goes red the day a fix lands, and the tag comes
  off with the fix.

  Scenario Outline: the doctor's "shell parser" row names the parser that reads
    Given a machine with <machine>
    When the doctor runs on that machine
    Then its "shell parser" row is <mark> matching "<row>"

    Examples:
      | machine                       | mark | row                                                             |
      | shfmt and bash                | ✓    | shfmt \d+\.\d+$                                                 |
      | no shfmt but bash             | !    | no shfmt .* on PATH; bash -n checks the parse instead$          |
      | neither shfmt nor bash        | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ |
      | no shfmt but bashlex          | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ |
      | no shfmt but tree-sitter-bash | !    | no shfmt .* on PATH; the built-in lexer reads commands instead$ |

    @known_gap
    Examples: the doctor does not name a pip parser yet
      | machine                       | mark | row                                                             |
      | no shfmt but bashlex          | !    | the built-in lexer reads commands.*bashlex                      |
      | no shfmt but tree-sitter-bash | !    | the built-in lexer reads commands.*tree-sitter-bash             |

  Scenario Outline: require-well-formed denies an unclosed quote and allows echo ok
    Given a machine with <machine>
    When the agent runs `echo 'unclosed` there
    Then the hook denies, read by <reader>
    When the agent runs `echo ok` there
    Then the hook is silent

    Examples:
      | machine                       | reader                           |
      | shfmt and bash                | shfmt                            |
      | no shfmt but bash             | bash -n                          |
      | neither shfmt nor bash        | awk                              |
      | no shfmt but bashlex          | awk, at 1:15 per bashlex         |
      | no shfmt but tree-sitter-bash | awk, at 1:6 per tree-sitter-bash |
