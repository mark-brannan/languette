@python
Feature: guard-unparsable
  A Bash command the parser refuses is denied, whole, naming shfmt's line:col
  and what it found, and saying nothing ran. The other guards skip such a
  command rather than deny it again. Without shfmt, a lower rung reads it:
<<<<<<< HEAD
  tree-sitter-bash, else `bash -n`, else the awk lexer, which refuses only a
  quote that never closes, so the line:col deny rows run on the shfmt rung only.
=======
  `bash -n`, else the awk lexer, which refuses only a quote that never
  closes, so the line:col deny rows run on the shfmt rung only.
>>>>>>> origin/main

  Rows marked "seen" are anonymized from a replay of 101,671 commands that
  agents ran (October 2026). 32 did not parse, about 1 in 3,000, and the awk
  rung let every one through. Each would have failed, run in part, or run text
  meant as prose.

  Scenario Outline: typical agent commands parse and pass
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                  | note                                                                                     |
      | python3 -c "import json; print(json.dumps({1: 2}))"      | Python braces and parens in a dq string                                                  |
      | python3 -c 'print("a;b" if x else (1, 2))'               | Python with its own quotes inside sq                                                     |
      | node -e 'console.log([1,2].map(x => x*2))'               | an arrow function's > inside sq                                                          |
      | node -e "process.exit(+(1 < 2))"                         | a < inside dq                                                                            |
      | sqlite3 db.sqlite "SELECT count(*) FROM t WHERE x > 3;"  | SQL's * and ; inside dq                                                                  |
      | sqlite3 -json db.sqlite 'select * from t where n = "a";' | SQL's dq inside sq                                                                       |
      | jq -r '.items[] \| select(.n > 1) \| .name' f.json       | jq's pipes inside sq                                                                     |
      | jq -n --arg x "a b" '{x: $x}'                            | jq's $x inside sq                                                                        |
      | git commit -m "quote <<EOF in prose"                     | a heredoc opener quoted in a message                                                     |
      | git commit -m "docs: the \"<<'EOF'\" opener"             | an escaped, quoted heredoc opener                                                        |
      | sh -c "if then fi"                                       | known gap: nested text shfmt refuses goes to the awk rung (#62's pencil)                 |
      | git commit -m "docs: `pgrep -f` matches its own parent"  | known gap, seen: backticks that parse still run, here pgrep, and drop out of the message |

  @shfmt_only
  Scenario Outline: a command that does not parse is denied, naming the parser's position
    When the agent runs `<command>`
    Then the guard denies, naming "<position>"

    Examples:
      | command                                                            | position | note                                                                                      |
      | echo "unclosed                                                     | 1:6      | an unclosed double quote                                                                  |
      | echo 'unclosed                                                     | 1:6      | an unclosed single quote                                                                  |
      | git commit -m "half a message                                      | 1:15     | an unclosed commit message                                                                |
      | if true; then echo x                                               | 1:1      | an if without its fi                                                                      |
      | echo $(date                                                        | 1:6      | an unclosed command substitution                                                          |
      | echo --- t3 (untracked files) ---                                  | 1:13     | seen 12 times: parens in an echo label; bash ran the lines before it and dropped the rest |
      | git commit -m "fix: the `\|\| echo 99` fallback hid the exit code" | 1:26     | seen: backticks run as a command; the pushed message lost the words                       |
      | grep -rn "plugins/${plugin.id}" src                                | 1:21     | seen: bad substitution; the search never ran                                              |
      | grep -n "fence ```" notes.md                                       | 1:19     | seen: a Markdown fence opens a backtick that never closes                                 |
      | python3 -c "print(f'${total:>8}')"                                 | 1:29     | seen: an f-string format spec read as a shell parameter                                   |
      | echo $((echo hi) )                                                 | 1:14     | stricter than bash, never seen: bash runs it; write $( (                                  |

  @shfmt_only
  Scenario: two heredocs opened on one line with one body is denied
    # Seen twice. Bash only warns: the second heredoc swallows every line
    # after the first body, so the fallback writes the wrong text and the
    # tail never runs.
    When the agent runs:
      """
      cat > a.md <<'EOF' 2>/dev/null || cat > b.md <<'EOF'
      note
      EOF
      tail a.md
      """
    Then the guard denies, naming "1:46: unclosed here-document"

  @shfmt_only
  Scenario: a heredoc with no closing line is denied, though bash would run it
    # Stricter than bash, never seen alone: bash warns and reads the body to
    # the end of the command.
    When the agent runs:
      """
      cat <<'EOF'
      body, no closing line
      """
    Then the guard denies, naming "1:5: unclosed here-document"

  @python_only
  Scenario Outline: on the awk rung alone, a quote that never closes is denied
    When the agent runs `<command>`
    Then the guard denies, naming "<found>"

    Examples:
      | command                       | found                                  |
      | echo "unclosed                | awk: the " opened at `"unclosed`       |
      | git commit -m 'half; rm -rf x | awk: the ' opened at `'half; rm -rf x` |

  @shfmt_only
  Scenario: a substitution in a heredoc with no closing line is denied
    When the agent runs:
      """
      cat <<EOF
      $(rm -rf examples)
      """
    Then the guard denies, naming "1:5: unclosed here-document"

  @shfmt_only
  Scenario: an escaped ; before # in a backtick substitution in a heredoc is denied
    # Stricter than bash, never seen: bash reads `echo \;#'` as echo ; and a
    # comment, shfmt reads the ' as opening a quote.
    When the agent runs:
      """
      cat <<EOF
      `echo \;#'`
      EOF
      rm -rf examples
      """
    Then the guard denies, naming "2:10: reached EOF without closing quote"
