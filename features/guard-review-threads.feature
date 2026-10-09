@python
Feature: guard-review-threads
  A review bot's thread is resolved only on a fix or a record. When a Bash
  call resolves a GitHub review thread (`gh api graphql` with a
  `resolveReviewThread` mutation), the guard reads that thread from GitHub
  and denies unless both hold: the current gh login replied after the
  bot's last comment, and that reply names a commit (7 to 40 hex
  characters) or a link (an `https://` URL, or `owner/repo#n`). A thread
  no bot commented on is not this guard's. A query that opens with `{` or
  `query` is a read, whatever run-time values fill it. A file a `-F` field
  or `--input` names is read, when gh runs alone in the call. A graphql
  query the guard cannot read otherwise (built at run time, a file it
  cannot open, stdin with no heredoc) or a thread it cannot identify is a
  deny that says so; GitHub that cannot be read is an ask, as for the
  other guards that ask GitHub.

  Why. An agent reversed an instruction it had been given; the review bot
  flagged it, and the agent replied that the replacement was intended,
  resolved the thread and moved on (languette#116). Of 585 bot threads
  over 30 days, 21 were resolved with no reply at all and 5 dismissed on
  the agent's own word with nothing behind them; the 29 sound dismissals
  each pointed at a record. So the reply carries the fix commit, or a link
  to the ruling, decision record or issue the dismissal rests on. With
  nothing behind it, the thread stays open for a person.

  gh is a stub throughout: it answers as GH_LOGIN, and each thread a
  scenario sets up is what it answers for that id; any other id is not
  found. A bot is an author GitHub calls a Bot, a login ending in `[bot]`,
  or one of coderabbitai, claude, copilot-pull-request-reviewer and
  github-actions; the gh login's own comments are replies, even when that
  login is a bot. The guard checks that a reply names a record, not that
  the commit exists. Only gh is read: a POST to the GraphQL endpoint by
  another client (curl, a script) is not this guard's.

  Background:
    Given the stub "gh" is first on PATH, for a Python guard
    And GH_LOGIN is "me"

  Scenario Outline: a reply naming the fix or the record lets the thread close
    Given review thread "PRRT_t1" holds:
      | author       | body                                  |
      | coderabbitai | This reverses the earlier instruction. |
      | me           | <reply>                               |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard is silent
    And the stub "gh" was called with "id=PRRT_t1"

    Examples:
      | reply                                                          | note                     |
      | Fixed in 3f2a9c1.                                              | a short sha              |
      | Fixed in 3f2a9c1e0b7d4a6c8e2f1b3d5a7c9e0f2b4d6a8c.              | a full sha               |
      | Kept: https://github.com/o/r/blob/main/docs/decisions.md#scope | a link to a decision     |
      | Out of scope here; tracked in o/r#12.                          | an owner/repo#n issue    |
      | Fixed in 1234567.                                              | a sha may be all digits  |

  Scenario Outline: a reply with nothing behind it is denied
    Given review thread "PRRT_t1" holds:
      | author       | body                                  |
      | coderabbitai | This reverses the earlier instruction. |
      | me           | <reply>                               |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard denies, naming "names no commit and no link"
    And the guard denies, naming "leaves the thread open"

    Examples:
      | reply                               | note                                |
      | The replacement is intended.        | the agent's own word                |
      | Not fixing: see #12.                | a bare #n names no repository       |
      | See http://example.com/ruling.      | not https                           |
      | Fixed in 3f2a9c.                    | six hex characters is too short     |

  Scenario Outline: no reply from this login after the bot's last comment is denied
    Given review thread "PRRT_t1" holds:
      | author       | body                                      |
      | coderabbitai | This reverses the earlier instruction.     |
      | <second>     | <second_body>                             |
      | <third>      | <third_body>                              |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard denies, naming "no reply from me after"

    Examples:
      | second       | second_body       | third        | third_body              | note                                |
      | coderabbitai | Still open.       | coderabbitai | Still open.             | the bot alone                       |
      | me           | Fixed in 3f2a9c1. | coderabbitai | The fix misses a case.  | the bot spoke last                  |
      | someone-else | Fixed in 3f2a9c1. | someone-else | Also o/r#12.            | a reply from another login          |

  Scenario Outline: each kind of bot is recognised
    Given review thread "PRRT_t1" holds:
      | type   | author   | body                |
      | <type> | <author> | Consider a rename.  |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard denies, naming "no reply from me after"

    Examples:
      | type | author                        | note                         |
      | User | coderabbitai                  | named                        |
      | User | claude                        | named                        |
      | User | copilot-pull-request-reviewer | named                        |
      | User | github-actions                | named                        |
      | User | CodeRabbitAI                  | named, in another case       |
      | User | renovate[bot]                 | a login ending in [bot]      |
      | Bot  | some-app                      | an author GitHub calls a Bot |

  Scenario Outline: a thread no bot commented on is not this guard's
    Given review thread "PRRT_t1" holds:
      | author   | body                 |
      | <author> | Please rename this.  |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard is silent

    Examples:
      | author       | note                                 |
      | a-reviewer   | a person                             |
      | me           | the login itself                     |
      |              | a deleted account, which has no login |

  Scenario Outline: each spelling of the resolve is read
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    When the agent runs `<command>`
    Then the guard denies, naming "PRRT_t1"
    And the stub "gh" was called with "id=PRRT_t1"

    Examples:
      | command                                                                                                            | note                          |
      | gh api graphql -F id=PRRT_t1 -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}'   | -F                            |
      | gh api graphql --raw-field id=PRRT_t1 --raw-field query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}' | --raw-field |
      | gh api graphql -f query="mutation { resolveReviewThread(input: {threadId: \"PRRT_t1\"}) { thread { id } } }"       | the id inline                 |
      | sh -c 'gh api graphql -f query="mutation{resolveReviewThread(input:{threadId:\"PRRT_t1\"}){thread{id}}}"'          | nested in sh -c               |
      | echo ok && gh api graphql -f id=PRRT_t1 -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}' | after a separator  |

  Scenario: a resolve fed through --input from a heredoc is read
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    When the agent runs:
      """
      gh api graphql --input - <<'EOF'
      {"query": "mutation { resolveReviewThread(input: {threadId: \"PRRT_t1\"}) { thread { id } } }"}
      EOF
      """
    Then the guard denies, naming "PRRT_t1"

  Scenario: every thread one call resolves is read, and one without a record denies
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
      | me           | Fixed in 3f2a9c1.   |
    And review thread "PRRT_t2" holds:
      | author       | body                |
      | coderabbitai | Consider a test.    |
    When the agent runs `gh api graphql -f query='mutation{a:resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}} b:resolveReviewThread(input:{threadId:"PRRT_t2"}){thread{id}}}'`
    Then the guard denies, naming "PRRT_t2"
    And the stub "gh" was called with "id=PRRT_t1"

  Scenario Outline: a thread the guard cannot identify is denied without asking GitHub
    When the agent runs `<command>`
    Then the guard denies, naming "cannot tell which review thread"
    And the stub "gh" was not called

    Examples:
      | command                                                                                                       | note                    |
      | gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}' -f id="$T" | the id built at run time |
      | gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}'            | no id at all            |
      | gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}' -F id=@ids.txt | the id read from a file |
      | gh api graphql -f query='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}' --field=note=@n.txt | another field from a file |

  Scenario Outline: a bot's own login replying with the fix may resolve its thread
    Given GH_LOGIN is "<viewer>"
    And review thread "PRRT_t1" holds:
      | type | author       | body                |
      | Bot  | coderabbitai | Consider a rename.  |
      | Bot  | <author>     | Fixed in 3f2a9c1.   |
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t1`
    Then the guard is silent

    Examples:
      | viewer         | author        | note                                          |
      | claude         | claude        | the same login                                |
      | gh-agent[bot]  | gh-agent      | an app's token, which GraphQL gives no [bot]  |
      | gh-agent       | gh-agent[bot] | the other way round                           |

  Scenario Outline: a graphql call whose query cannot be read is denied
    When the agent runs `<command>`
    Then the guard denies, naming "cannot tell which review thread"
    And the stub "gh" was not called

    Examples:
      | command                                                                                                      | note                      |
      | echo '{"query":"mutation{resolveReviewThread(input:{threadId:\"PRRT_t1\"}){thread{id}}}"}' \| gh api graphql --input - | piped stdin, no heredoc |
      | Q='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}'; gh api graphql -f query="$Q"       | the query in a variable   |
      | gh api graphql -F query=@m.graphql -f id=PRRT_t1                                                              | the query in a missing file |
      | gh api graphql --input m.json -f id=PRRT_t1                                                                   | the payload in a file     |
      | gh api graphql -F query=@m.graphql -f id="$ID"                                                                | a file, the id run-time   |
      | gh api graphql --input payload.json                                                                           | everything in a file      |
      | gh api graphql -F query=@q.graphql -F owner=o                                                                 | a missing file, whatever it holds |
      | gh api graphql -f query="mutation{addComment(input:{subjectId:\"$S\",body:\"x\"}){clientMutationId}}"    | a mutation built at run time |
      | gh api graphql -f query="query Q{viewer{login}} $M" -f operationName=M                                     | a run-time read that names its operation |
      | gh api graphql -f "$K=mutation{resolveReviewThread(input:{threadId:\"PRRT_t1\"}){thread{id}}}"             | a field name built at run time |
      | gh api graphql --input=m.json -f id=PRRT_t1                                                                   | --input=, a file          |
      | gh api /graphql --input m.json                                                                                | the /graphql path         |
      | gh api https://api.github.com/graphql --input m.json                                                          | the endpoint's full URL   |

  Scenario: a heredoc fed to another command does not make --input FILE readable
    When the agent runs:
      """
      git commit -F - <<'EOF'
      notes
      EOF
      gh api graphql --input m.json -f id=PRRT_t1
      """
    Then the guard denies, naming "cannot tell which review thread"

  Scenario: a heredoc fed to another command does not make piped stdin readable
    When the agent runs:
      """
      git commit -F - <<'EOF'
      notes
      EOF
      echo '{"query":"mutation{resolveReviewThread(input:{threadId:\"PRRT_t1\"}){thread{id}}}"}' | gh api graphql --input -
      """
    Then the guard denies, naming "cannot tell which review thread"

  Scenario: quotes inside the api word do not hide the call
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    When the agent runs `gh a''pi graphql -f id=PRRT_t1 -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}'`
    Then the guard denies, naming "no reply from me after"

  Scenario Outline: the graphql endpoint by its path or its URL is read
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    When the agent runs `gh api <endpoint> -f id=PRRT_t1 -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}'`
    Then the guard denies, naming "no reply from me after"

    Examples:
      | endpoint                              |
      | /graphql                              |
      | https://api.github.com/graphql        |
      | https://ghe.example.com/api/graphql   |

  Scenario: a JSON escape in the --input heredoc does not hide the mutation
    Given review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    When the agent runs:
      """
      gh api graphql --input - <<'EOF'
      {"query": "mutation { resolveReviewThread(input: {threadId: \"PRRT_t1\"}) { thread { id } } }"}
      EOF
      """
    Then the guard denies, naming "no reply from me after"

  Scenario Outline: an endpoint built at run time that could be graphql is denied
    When the agent runs `<command>`
    Then the guard denies, naming "cannot tell which review thread"

    Examples:
      | command                                                                                          |
      | E=graphql; gh api "$E" -f query='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}' |
      | E=graph; gh api "${E}ql" -f id=PRRT_t1                                                           |
      | gh api -X POST "$URL" -f body=x                                                                  |
      | gh api "$BASE/graphql" -f query='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}' |
      | gh api "https://$HOST/api/graphql" -f query='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}' |
      | gh api "${BASE}/v4/graphql" -f id=PRRT_t1                                                        |
      | gh "$S" graphql -f query='mutation{resolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}'  |

  Scenario Outline: a REST path built at run time is not this guard's
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                        |
      | gh api "repos/$R/pulls/5"      |
      | gh api repos/o/r/pulls/$N      |
      | gh api "user/$X"               |

  Scenario: a readable query with a run-time field resolves nothing, and is not this guard's
    When the agent runs `gh api graphql -f query='query($n:Int!){viewer{login}}' -F n="$N"`
    Then the guard is silent
    And the stub "gh" was not called

  Scenario Outline: GitHub that cannot be read is a deny that says so
    Given <setup>
    When the agent runs `gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}' -f id=PRRT_t9`
    Then the guard asks, naming "GitHub could not be read"

    Examples:
      | setup                                  | note                                  |
      | GH_FAIL is "1"                         | gh fails: signed out, offline         |
      | GH_LOGIN is "me"                       | no such thread                        |
      | PATH holds only "sh"                   | no gh at all                          |

  Scenario Outline: what resolves no thread is not this guard's
    When the agent runs `<command>`
    Then the guard is silent
    And the stub "gh" was not called

    Examples:
      | command                                                                                                         | note                          |
      | gh api graphql -f query='mutation{unresolveReviewThread(input:{threadId:"PRRT_t1"}){thread{id}}}'              | reopening a thread            |
      | gh api graphql -f query='query{node(id:"PRRT_t1"){... on PullRequestReviewThread{isResolved}}}'                 | reading a thread              |
      | gh api graphql -f query='mutation{addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:"PRRT_t1",body:"x"}){comment{id}}}' | a reply |
      | echo 'gh api graphql -f query=resolveReviewThread -f id=PRRT_t1'                                                | text, not a call              |
      | git commit -m 'guard resolveReviewThread on PRRT_t1'                                                            | a commit message              |
      | gh api graphql -f query="{repository(owner:\"o\",name:\"$R\"){pullRequest(number:$N){id}}}"               | a read filled at run time     |
      | gh api graphql -f query="query{node(id:\"$T\"){id}}" --jq .data                                            | a named read filled at run time |
      | gh api graphql -f query=@m.graphql -f id=PRRT_t1                                                                | -f sends @m.graphql as text   |
      | gh api graphql -f query='mutation($id:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id,body:$b}){comment{url}}}' -f id=PRRT_t1 -f b='resolveReviewThread is guarded now' | a reply that names the mutation |
      | gh pr view 5                                                                                                    | another gh call               |

  Scenario Outline: a file a field or --input names is read, when gh runs alone
    Given a project directory
    And the working directory is "{PROJ}"
    And review thread "PRRT_t1" holds:
      | author       | body                |
      | coderabbitai | Consider a rename.  |
    And review thread "PRRT_ok" holds:
      | author       | body                |
      | coderabbitai | Consider a test.    |
      | me           | Fixed in 3f2a9c1.   |
    And the file "resolve.graphql" holds:
      """
      mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}}
      """
    And the file "reply.graphql" holds:
      """
      mutation($id:ID!,$b:String!){addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id,body:$b}){comment{url}}}
      """
    And the file "ids.txt" holds:
      """
      PRRT_t1
      """
    And the file "resolve.json" holds:
      """
      {"query": "mutation { resolveReviewThread(input: {threadId: \"PRRT_t1\"}) { thread { id } } }"}
      """
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                                                         | verdict                                          | note                       |
      | gh api graphql -F query=@reply.graphql -f id=PRRT_t1 -F b=@ids.txt                             | is silent                                        | a reply from a file        |
      | gh api graphql -F query=@resolve.graphql -f id=PRRT_t1                                         | denies, naming "no reply from me after"          | a resolve from a file      |
      | gh api graphql --input resolve.json                                                            | denies, naming "no reply from me after"          | a resolve from --input     |
      | gh api graphql -f query='mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{id}}} # PRRT_ok' -F id=@ids.txt | denies, naming "PRRT_t1" | the id from a file, past a decoy |
      | cd sub && gh api graphql -F query=@../resolve.graphql -f id=PRRT_t1                            | denies, naming "cannot tell which review thread" | a cd moves the file        |
      | echo x > resolve.graphql; gh api graphql -F query=@resolve.graphql -f id=PRRT_t1               | denies, naming "cannot tell which review thread" | another command could rewrite it |
      | gh api graphql -F query=@reply.graphql -f id="$T" -F b=@ids.txt                                | is silent                                        | a reply, whatever its id   |
