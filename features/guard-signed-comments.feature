@python
Feature: guard-signed-comments
  A comment an agent posts to GitHub is signed as an agent's. The body's
  first line begins with `🤖 ` and its last non-empty line is the signature,
  `🤖 <model id> · <low|medium|high|-> · <eight lowercase hex>`: the model,
  its effort, and the first eight hex of the session id.

      🤖 Fixed in a03793a: …

      🤖 claude-opus-5-5 · high · 5a74df74

  Why. An agent posts under the user's own GitHub login, so a review bot and
  the next agent read an agent's reply as the user's ruling. Scar: #116,
  where an agent's reply on a review thread was taken as the user's, and a
  reversal of the user's instruction was merged into the PR.

  It fires on Bash `gh pr comment`, `gh issue comment`, `gh pr review` with
  a body, `gh api` writing a body to a path with a `comments` or `reviews`
  segment, and `gh api graphql` whose query adds, edits or submits a comment,
  review or review-thread reply. Editing a PR or issue body is not a comment.
  The body is read where it is written: --body/-b, --body-file/-F, gh api's
  body field (literal or `@file`) or --input JSON, a heredoc in the same
  command, a `$(cat <<EOF)` around one, or a variable this command assigns
  from one. A body built at run time from anything else is denied, as
  guard-private-terms denies it, with the fix in the reason: write it
  literally, in a heredoc or a --body-file.

  Rule: a signed comment posts

    Scenario: a signed comment, quoted on the command line
      When the agent runs:
        """
        gh pr comment 116 -R o/r --body "🤖 Fixed in a03793a: the reply now names its author.

        🤖 claude-opus-5-5 · high · 5a74df74"
        """
      Then the guard is silent

    Scenario: a signed review-thread reply, from a heredoc fed to --input
      When the agent runs:
        """
        gh api repos/o/r/pulls/116/comments/9/replies --input - <<'EOF'
        {"body": "🤖 Not applied: the design doc says otherwise.\n\n🤖 claude-opus-5-5 · high · 5a74df74"}
        EOF
        """
      Then the guard is silent

    Scenario: a signed review through graphql, its body a variable fed from a heredoc
      When the agent runs:
        """
        b=$(cat <<'EOF'
        🤖 One finding, below.

        🤖 claude-sonnet-5 · medium · 0badcafe
        EOF
        )
        gh api graphql -f query='mutation($b:String!){ addPullRequestReview(input:{pullRequestId:"P", body:$b, event:COMMENT}) { clientMutationId } }' -f b="$b"
        """
      Then the guard is silent

    Scenario Outline: the signature line has one shape
      When the agent runs `gh pr comment 1 -b "<body>"`
      Then the guard <verdict>

      Examples:
        | body                                    | verdict                    |
        | 🤖 claude-opus-5-5 · high · 5a74df74    | is silent                  |
        | 🤖 claude-opus-5-5 · low · 5a74df74     | is silent                  |
        | 🤖 some-model · - · 00000000            | is silent                  |
        | 🤖 claude-opus-5-5 · xhigh · 5a74df74   | denies, naming "last line" |
        | 🤖 claude-opus-5-5 · high · 5A74DF74    | denies, naming "last line" |
        | 🤖 claude-opus-5-5 · high · 5a74df7     | denies, naming "last line" |
        | 🤖 claude-opus-5-5 - high - 5a74df74    | denies, naming "last line" |
        | 🤖 · high · 5a74df74                    | denies, naming "last line" |
        | 🤖claude-opus-5-5 · high · 5a74df74     | denies, naming "first line" |

  Rule: an unsigned comment is denied, and the reason shows the signature

    Scenario Outline: every route to a comment is read
      When the agent runs `<command>`
      Then the guard denies, naming "🤖 claude-opus-5-5 · high ·"

      Examples:
        | command                                                                                                                     |
        | gh pr comment 116 -b "Replacement is the intent"                                                                            |
        | gh pr comment 116 --body="Replacement is the intent"                                                                        |
        | gh issue comment 3 --body "🤖 Done"                                                                                         |
        | gh pr review 4 --comment -b "Looks right"                                                                                   |
        | gh pr review 4 --request-changes --body=Nope                                                                                |
        | gh api repos/o/r/pulls/116/comments/9/replies -f body="Replacement is the intent"                                           |
        | gh api repos/o/r/issues/116/comments -F body=Done                                                                           |
        | gh api -X PATCH repos/o/r/issues/comments/5 -f body=Edited                                                                  |
        | gh api repos/o/r/pulls/4/reviews -f event=COMMENT -f body=Done                                                              |
        | gh api repos/o/r/pulls/4/reviews -f event=COMMENT -F 'comments[][path]=a.py' -F 'comments[][body]=Nit'                      |
        | gh api graphql -f query='mutation { addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:"T", body:"Agreed"}) { comment { id } } }' |
        | gh api graphql -f query='mutation($b:String!){ addComment(input:{subjectId:"S", body:$b}) { clientMutationId } }' -f b=Done  |
        | sh -c 'gh pr comment 1 -b "Done"'                                                                                           |
        | cd ~/project && gh pr comment 1 -b Done                                                                                     |

    Scenario Outline: the reason says which line is wrong
      When the agent runs `gh pr comment 1 -b "<body>"`
      Then the guard denies, naming "<line>"

      Examples:
        | body                                         | line       |
        | Replacement is the intent                    | first line |
        | 🤖 Done, no signature                         | last line  |

    Scenario: an unsigned body in a heredoc fed to --body-file is denied
      When the agent runs:
        """
        gh pr comment 116 --body-file - <<'EOF'
        Replacement is the intent.
        EOF
        """
      Then the guard denies, naming "first line"

    Scenario: an unsigned body in a $(cat <<EOF) is denied, a signed one posts
      When the agent runs:
        """
        gh pr comment 1 --body "$(cat <<'EOF'
        Replacement is the intent.
        EOF
        )"
        """
      Then the guard denies, naming "first line"
      When the agent runs:
        """
        gh pr comment 1 --body "$(cat <<'EOF'
        🤖 Fixed.

        🤖 claude-opus-5-5 · high · 5a74df74
        EOF
        )"
        """
      Then the guard is silent

    Scenario: a body file this command writes from a heredoc is judged by that heredoc
      When the agent runs:
        """
        cat > {TMP}/reply.md <<'EOF'
        Replacement is the intent.
        EOF
        gh pr comment 1 --body-file {TMP}/reply.md
        """
      Then the guard denies, naming "first line"

    Scenario: a body file on disk is read, never its path
      Given a project directory
      And the file "signed.md" holds:
        """
        🤖 Fixed in a03793a.

        🤖 claude-opus-5-5 · high · 5a74df74
        """
      And the file "unsigned.md" holds:
        """
        Fixed in a03793a.
        """
      When the agent runs `gh pr comment 1 --body-file {PROJ}/signed.md`
      Then the guard is silent
      When the agent runs `gh api repos/o/r/issues/1/comments -F body=@{PROJ}/signed.md`
      Then the guard is silent
      When the agent runs `gh pr comment 1 -F {PROJ}/unsigned.md`
      Then the guard denies, naming "first line"
      When the agent runs `gh api repos/o/r/issues/1/comments -F body=@{PROJ}/unsigned.md`
      Then the guard denies, naming "first line"

    Scenario: every inline comment of a review in an --input file is judged
      Given a project directory
      And the file "review.json" holds:
        """
        {"event": "COMMENT",
         "body": "🤖 Two notes.\n\n🤖 claude-opus-5-5 · high · 5a74df74",
         "comments": [{"path": "a.py", "line": 3, "body": "Rename this."}]}
        """
      When the agent runs `gh api repos/o/r/pulls/4/reviews --input {PROJ}/review.json`
      Then the guard denies, naming "first line"

  Rule: a body the guard cannot read is denied, with the fix in the reason

    Scenario Outline: built at run time, from stdin, or from a file it cannot read
      When the agent runs `<command>`
      Then the guard denies, naming "heredoc"

      Examples:
        | command                                                        |
        | gh pr comment 1 -b "$(git log -1 --format=%B)"                 |
        | gh pr comment 1 --body "$msg"                                  |
        | gh pr comment 1 --body-file $f                                 |
        | gh pr comment 1 --body-file {HOME}/no-such-reply.md            |
        | echo Done \| gh pr comment 1 -F -                              |
        | gh api repos/o/r/issues/1/comments -f body="$(cat reply.md)"   |
        | gh api graphql -f query='mutation { addComment(input:$in) { clientMutationId } }' -F in=@x.json |

  Rule: what is not a comment is silent

    Scenario Outline: reads, PR and issue bodies, reviews with no body, and text that names gh
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                                                                         |
        | gh pr edit 116 --body "Replacement is the intent"                                                               |
        | gh pr create -t t -b "Replacement is the intent"                                                                |
        | gh issue create -t t -b x                                                                                       |
        | gh pr review 4 --approve                                                                                        |
        | gh pr review 4 --approve --body ""                                                                              |
        | gh pr comment 1 --web                                                                                           |
        | gh pr view 116 --comments                                                                                       |
        | gh api repos/o/r/issues/1/comments                                                                              |
        | gh api repos/o/r/pulls/1/comments --jq '.[].body'                                                               |
        | gh api -X PATCH repos/o/r/pulls/1 -f body="Replacement is the intent"                                           |
        | gh api repos/o/r/issues/comments/5/reactions -f content=+1                                                      |
        | gh api graphql -f query='query { viewer { login } }'                                                            |
        | gh api graphql -f query='mutation { resolveReviewThread(input:{threadId:"T"}) { thread { isResolved } } }'      |
        | gh api graphql -f query='mutation { submitPullRequestReview(input:{pullRequestReviewId:"R", event:APPROVE}) { clientMutationId } }' |
        | git commit -m "gh pr comment 1 -b Done"                                                                         |
        | echo 'gh pr comment 1 -b Done'                                                                                  |
