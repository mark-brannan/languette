Feature: scan
  `languette scan` lets a hook outside languette read a command the way the
  guards do: the command on stdin, one JSON document out, its "segments"
  those of the command and of every nested text it runs, each word a
  {"text", "quoted"} pair ("quoted" a quoted word holding whitespace, its
  raw text). The output is experimental: it may change in any release while
  "languette_scan" is a v0 version. Each scenario runs it as such a hook
  would, `python3 -I` on the plugin's `languette/__main__.py`, from a
  directory outside this repo, and compares the JSON it prints.

  Scenario: every segment, nested texts after the command's own
    When `languette scan` reads `cd pkg && sh -c 'npm publish --tag next'`
    Then it prints:
      """
      {"languette_scan": "v0.1-alpha", "segments": [
        {"nested": false, "words": [{"text": "cd", "quoted": false}, {"text": "pkg", "quoted": false}]},
        {"nested": false, "words": [{"text": "sh", "quoted": false}, {"text": "-c", "quoted": false}, {"text": "npm publish --tag next", "quoted": true}]},
        {"nested": true, "words": [{"text": "npm", "quoted": false}, {"text": "publish", "quoted": false}, {"text": "--tag", "quoted": false}, {"text": "next", "quoted": false}]}
      ]}
      """

  Scenario: --command keeps the segments a command leads, from its command word on
    When `languette scan --command '(^|/)(gh|git)$'` reads `cd x && FOO=1 /usr/bin/git push origin HEAD; gh pr view 5 -R o/r | head`
    Then it prints:
      """
      {"languette_scan": "v0.1-alpha", "segments": [
        {"nested": false, "words": [{"text": "/usr/bin/git", "quoted": false}, {"text": "push", "quoted": false}, {"text": "origin", "quoted": false}, {"text": "HEAD", "quoted": false}]},
        {"nested": false, "words": [{"text": "gh", "quoted": false}, {"text": "pr", "quoted": false}, {"text": "view", "quoted": false}, {"text": "5", "quoted": false}, {"text": "-R", "quoted": false}, {"text": "o/r", "quoted": false}]}
      ]}
      """

  Scenario: a quoted word holding whitespace is one quoted word, its raw text
    When `languette scan --command '^gh$'` reads `gh pr comment 7 --body "fixed in the latest push"`
    Then it prints:
      """
      {"languette_scan": "v0.1-alpha", "segments": [
        {"nested": false, "words": [{"text": "gh", "quoted": false}, {"text": "pr", "quoted": false}, {"text": "comment", "quoted": false}, {"text": "7", "quoted": false}, {"text": "--body", "quoted": false}, {"text": "fixed in the latest push", "quoted": true}]}
      ]}
      """

  Scenario: a command named in prose is not run
    When `languette scan --command '(^|/)npm$'` reads `git commit -m "say why npm publish is wrapped"; echo npm publish`
    Then it prints no segments

  Scenario: a heredoc body is not run
    When `languette scan --command '(^|/)npm$'` reads:
      """
      cat <<EOF > notes.md
      then run npm publish
      EOF
      """
    Then it prints no segments

  Scenario: a command the scanner will not read is an exit 1, never a partial reading
    When `languette scan` reads a command one byte over the length limit
    Then it prints nothing and exits 1, naming "over the limit"
