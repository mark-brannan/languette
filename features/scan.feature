Feature: scan
  `languette scan` lets a hook outside languette read a command the way the
  guards do: the command on stdin, one JSON line out per segment of it and of
  every nested text it runs, each word in the scanner's encoding ("w:" a
  word, "q:" the raw text of a quoted word holding whitespace). Each scenario
  runs it as such a hook would, `python3 -I` on the plugin's
  `languette/__main__.py`, from a directory outside this repo. The output is unstable: it may change
  in any release until its contract is settled.

  Scenario: every segment, nested texts after the command's own
    When `languette scan` reads `cd pkg && sh -c 'npm publish --tag next'`
    Then it prints:
      """
      {"nested": false, "words": ["w:cd", "w:pkg"]}
      {"nested": false, "words": ["w:sh", "w:-c", "q:npm publish --tag next"]}
      {"nested": true, "words": ["w:npm", "w:publish", "w:--tag", "w:next"]}
      """

  Scenario: --command keeps the segments a command leads, from its command word on
    When `languette scan --command '(^|/)(gh|git)$'` reads `cd x && FOO=1 /usr/bin/git push origin HEAD; gh pr view 5 -R o/r | head`
    Then it prints:
      """
      {"nested": false, "words": ["w:/usr/bin/git", "w:push", "w:origin", "w:HEAD"]}
      {"nested": false, "words": ["w:gh", "w:pr", "w:view", "w:5", "w:-R", "w:o/r"]}
      """

  Scenario: a quoted word holding whitespace keeps its raw text
    When `languette scan --command '^gh$'` reads `gh pr comment 7 --body "fixed in the latest push"`
    Then it prints:
      """
      {"nested": false, "words": ["w:gh", "w:pr", "w:comment", "w:7", "w:--body", "q:fixed in the latest push"]}
      """

  Scenario: a command named in prose is not run
    When `languette scan --command '(^|/)npm$'` reads `git commit -m "say why npm publish is wrapped"; echo npm publish`
    Then it prints nothing

  Scenario: a heredoc body is not run
    When `languette scan --command '(^|/)npm$'` reads:
      """
      cat <<EOF > notes.md
      then run npm publish
      EOF
      """
    Then it prints nothing

  Scenario: a command the scanner will not read is an exit 1, never a partial reading
    When `languette scan` reads a command one byte over the length limit
    Then it prints nothing and exits 1, naming "over the limit"
