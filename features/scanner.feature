@python
Feature: scanner
  What the shared scanner makes of a command: its tokens ("w:" a word, "q:"
  the raw text of a quoted word holding whitespace, ";" a separator), and its
  texts after heredocs are stripped ("0:" the command, "1:" a nested text).

  Scenario Outline: the words a command scans into
    When the scanner reads `<command>`
    Then its tokens are <tokens>

    Examples:
      | command                           | tokens                                                                      | note                                                                             |
      | rm -rf build                      | ["w:rm", "w:-rf", "w:build"]                                                | plain words                                                                      |
      | r\m -rf x                         | ["w:rm", "w:-rf", "w:x"]                                                    | an escaped command word becomes the plain word                                   |
      | \git add -A                       | ["w:git", "w:add", "w:-A"]                                                  | alias-bypass backslash is removed                                                |
      | 'rm' -rf x                        | ["w:rm", "w:-rf", "w:x"]                                                    | a quoted command word is the plain word                                          |
      | rm -rf "$DIR"                     | ["w:rm", "w:-rf", "w:$DIR"]                                                 | a double-quoted word without whitespace stays one word; the hook refuses the $   |
      | rm -rf a\ b                       | ["w:rm", "w:-rf", "w:a b"]                                                  | an escaped space stays inside one word                                           |
      | rm -rf node_modules 2>&1          | ["w:rm", "w:-rf", "w:node_modules"]                                         | a dup redirection and its fd number are dropped                                  |
      | rm -rf x > /dev/null              | ["w:rm", "w:-rf", "w:x"]                                                    | a redirection operand is dropped, so it is never a target                        |
      | echo hi # rm -rf x                | ["w:echo", "w:hi"]                                                          | a comment is dropped to end of line                                              |
      | ls; rm -rf x                      | ["w:ls", ";", "w:rm", "w:-rf", "w:x"]                                       | ; separates                                                                      |
      | cd x && rm -rf y                  | ["w:cd", "w:x", ";", "w:rm", "w:-rf", "w:y"]                                | && is a separator; runs of separators collapse                                   |
      | a \| b                            | ["w:a", ";", "w:b"]                                                         | a pipe is a separator                                                            |
      | { rm -rf x; }                     | ["w:rm", "w:-rf", "w:x", ";"]                                               | a standing-alone brace is a separator                                            |
      | rm -rf dist{,2}                   | ["w:rm", "w:-rf", "w:dist{,2}"]                                             | a glued brace stays in the word, so brace expansion reaches the hook unresolved  |
      | echo ${VAR}                       | ["w:echo", "w:${VAR}"]                                                      | a glued ${...} stays in the word                                                 |
      | find . -name x -exec rm -rf {} \; | ["w:find", "w:.", "w:-name", "w:x", "w:-exec", "w:rm", "w:-rf", ";", "w:;"] | find's {} is a separator; the escaped ; is a plain word                          |
      | xargs -I{} gh pr edit {} --label x | ["w:xargs", "w:-I{}", "w:gh", "w:pr", "w:edit", "w:{}", "w:--label", "w:x"] | a bare {} among words is a word, so the gh segment keeps its flags               |
      | find . -exec sh -c "echo hi" {} \; | ["w:find", "w:.", "w:-exec", "w:sh", "w:-c", "q:echo hi", ";", "w:;"] | a quoted word before find's {} does not hide the -exec, so {} stays a separator |
      | xargs -I{} gh pr edit --title -ok {} --label x | ["w:xargs", "w:-I{}", "w:gh", "w:pr", "w:edit", "w:--title", "w:-ok", "w:{}", "w:--label", "w:x"] | -ok outside a find command is a plain word, so {} stays a word |
      | sh -c "rm -rf build"              | ["w:sh", "w:-c", "q:rm -rf build"]                                          | a quoted string with whitespace is one q word, raw text kept for the nested scan |
      | git commit -m "add -A everything" | ["w:git", "w:commit", "w:-m", "q:add -A everything"]                        | prose in a commit message is one q word                                          |
      | echo 'it is $(x)'                 | ["w:echo", "q:it is $(x)"]                                                  | single quotes are literal                                                        |
      | x=$(git add -A)                   | ["w:x=$", ";", "w:git", "w:add", "w:-A", ";"]                               | parentheses are separators, so a command substitution is scanned as commands     |
      | x=`git push -f origin foo`        | ["w:x=", ";", "w:git", "w:push", "w:-f", "w:origin", "w:foo", ";"]          | backticks are separators                                                         |
      | git push origin --delete "$b"     | ["w:git", "w:push", "w:origin", "w:--delete", "w:$b"]                       | a variable ref stays an unresolvable word                                        |

  Scenario: a line continuation is nothing
    When the scanner reads:
      """
      rm -rf \
      examples
      """
    Then its tokens are ["w:rm", "w:-rf", "w:examples"]

  Scenario: one plain text
    When the scanner reads `rm -rf build`
    Then its texts are ["0:rm -rf build\n"]

  Scenario: a quoted string handed to sh is queued for a nested scan
    When the scanner reads `sh -c 'rm -rf build'`
    Then its texts are ["0:sh -c 'rm -rf build'\n", "1:rm -rf build"]

  Scenario: eval runs its text
    When the scanner reads `eval "git stash pop"`
    Then its texts are ["0:eval \"git stash pop\"\n", "1:git stash pop"]

  Scenario: xargs sh -c runs its text
    When the scanner reads `ls | xargs -I{} sh -c 'rm -rf {}'`
    Then its texts are ["0:ls | xargs -I{} sh -c 'rm -rf {}'\n", "1:rm -rf {}"]

  Scenario: echo prints: its quoted string is prose, not queued
    When the scanner reads `echo "rm -rf x"`
    Then its texts are ["0:echo \"rm -rf x\"\n"]

  Scenario: grep takes a pattern: prose
    When the scanner reads `grep -rn "rm -rf x" .`
    Then its texts are ["0:grep -rn \"rm -rf x\" .\n"]

  Scenario: a commit message is prose
    When the scanner reads `git commit -m "block rm -rf x"`
    Then its texts are ["0:git commit -m \"block rm -rf x\"\n"]

  Scenario: piped into a shell, the prose is executed text
    When the scanner reads `echo "rm -rf x" | sh`
    Then its texts are ["0:echo \"rm -rf x\" | sh\n", "1:rm -rf x"]

  Scenario: an unknown consumer is scanned like an executor
    When the scanner reads `mytool --run "rm -rf x"`
    Then its texts are ["0:mytool --run \"rm -rf x\"\n", "1:rm -rf x"]

  Scenario: heredoc bodies are dropped before scanning
    When the scanner reads:
      """
      cat <<EOF
      never run rm -rf x
      EOF
      """
    Then its texts are ["0:cat  HEREDOC \n"]

  Scenario: an unquoted heredoc keeps its command substitutions, one per line
    When the scanner reads:
      """
      cat <<EOF
      it's $(date +%F) and `id -u`, not \$(whoami)
      EOF
      """
    Then its texts are ["0:cat  HEREDOC \n$(date +%F)\n`id -u`\n"]

  Scenario: a backslash continuation keeps the next line as part of the opener line
    When the scanner reads:
      """
      cat <<EOF; \
      rm -rf x
      EOF
      """
    Then its texts are ["0:cat  HEREDOC ; \\\nrm -rf x\n"]

  Scenario: a quote running past the opener line keeps its lines, and the body starts after its end
    When the scanner reads:
      """
      cat <<EOF; echo "
      text
      "; rm -rf x
      never run
      EOF
      """
    Then its texts are ["0:cat  HEREDOC ; echo \"\ntext\n\"; rm -rf x\n"]

  Scenario: a quote in a comment on the opener line opens nothing, so the body starts on the next line
    When the scanner reads:
      """
      cat <<EOF # it's here
      rm -rf x
      EOF
      """
    Then its texts are ["0:cat  HEREDOC  # it's here\n"]

  Scenario: a substitution running past the opener line keeps its lines, and the body starts after its end
    When the scanner reads:
      """
      cat <<EOF; echo $(
      rm -rf x
      )
      body
      EOF
      """
    Then its texts are ["0:cat  HEREDOC ; echo $(\nrm -rf x\n)\n"]

  Scenario: two openers on one line keep the line and take their bodies in turn
    When the scanner reads:
      """
      cat <<A <<'B' | wc
      $(id -u)
      A
      $(whoami)
      B
      """
    Then its texts are ["0:cat  HEREDOC   HEREDOC  | wc\n$(id -u)\n"]

  Scenario: a heredoc body that mentions a command is not that command
    When the scanner reads:
      """
      git add foo.sh
      git commit -F- <<'EOF'
      never git add -A
      EOF
      """
    Then its texts are ["0:git add foo.sh\ngit commit -F-  HEREDOC \n"]

  Scenario: a \r is a byte in a word, not a line end, in both engines
    When the scanner reads the JSON string "echo a\r\nb"
    Then its tokens are ["w:echo", "w:a\r", ";", "w:b"]
