@python
Feature: parse-check
  languette/run.py checks a Bash command once, before any guard runs: when
  the parser ladder's top rung refuses the command itself, the hook denies
  with the parser's line:col message. Every guard runs, so a silent row is
  silent to all of them. The awk rung refuses nothing, so the deny rows run
  on the shfmt rung only.

  Scenario Outline: typical agent commands parse and pass
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                    | note                                      |
      | python3 -c "import json; print(json.dumps({1: 2}))"        | Python braces and parens in a dq string   |
      | python3 -c 'print("a;b" if x else (1, 2))'                 | Python with its own quotes inside sq      |
      | node -e 'console.log([1,2].map(x => x*2))'                 | an arrow function's > inside sq           |
      | node -e "process.exit(+(1 < 2))"                           | a < inside dq                             |
      | sqlite3 db.sqlite "SELECT count(*) FROM t WHERE x > 3;"    | SQL's * and ; inside dq                   |
      | sqlite3 -json db.sqlite 'select * from t where n = "a";'   | SQL's dq inside sq                        |
      | jq -r '.items[] \| select(.n > 1) \| .name' f.json         | jq's pipes inside sq                      |
      | jq -n --arg x "a b" '{x: $x}'                              | jq's $x inside sq                         |
      | git commit -m "quote <<EOF in prose"                       | a heredoc opener quoted in a message      |
      | git commit -m "docs: the \"<<'EOF'\" opener"               | an escaped, quoted heredoc opener         |
      | sh -c "if then fi"                                         | known gap: nested text shfmt refuses goes to the awk rung (#62's pencil) |

  @shfmt_only
  Scenario Outline: a command that does not parse is denied, naming the parser's position
    When the agent runs `<command>`
    Then the guard denies, naming "<position>"

    Examples:
      | command                       | position | note                         |
      | echo "unclosed                | 1:6      | an unclosed double quote     |
      | echo 'unclosed                | 1:6      | an unclosed single quote     |
      | git commit -m "half a message | 1:15     | an unclosed commit message   |
      | if true; then echo x          | 1:1      | an if without its fi         |
      | echo $(date                   | 1:6      | an unclosed command substitution |
