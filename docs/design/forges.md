# Forges

The design behind #288: guards for forges beyond GitHub. Present tense is
the aim; "(planned)" marks where the code lags. It builds on [guard
rules](guard-rules.md) and [portability](portability.md) rule 9: a forge is
a row of a table, never the rule itself.

## Purpose

An agent on GitLab can do the harm a guard stops on GitHub, through another
client, and no guard fires. A guard names the harm; each forge says how an
agent reaches it there.

## A forge is a row

`scan.FORGES` holds one row per forge: its client (`gh`, `glab`), the host
its service answers on and the other names a remote's URL gives that host,
the first label of a self-hosted install's host (`gitlab.example.com`), and
the shape of a repository's path there (`owner/repo`; GitLab's
`group/subgroup/project`). A forge enters as a row; Forgejo and Gitea are
next (planned).

## Which forge a repository is on

The host in the URL of the repository's remote, the one the guard already
reads, picks the row. A host no row fits is no forge: a guard that needs
the forge's answer treats the repository as unknown, as it does a remote it
cannot read.

## The world asks the forge's client

A guard yields `forge-api` with the forge, the host and an API path; the
world runs that row's client (`gh api`, `glab api`), adding `--hostname` for
a self-hosted host. The answer is the status and parsed body, or nothing
when the client cannot say. Only reads, as every Need.

## A guard's rows per forge

A guard's matching says, per forge, which client words, API paths, methods
and graphql mutations reach its harm, and, for a guard that asks the forge,
which of its facts answers the guard's question there. Each ported guard has a scenario per
forge in its feature file. Today the rows sit in the guard; on the engine
they become rule data, one `match` entry per client (planned).

| Guard | GitLab |
|---|---|
| guard-github-issues | issue create, delete and move through glab (see the guard's header) |
| guard-private-terms | `glab issue\|mr` create, update, note and merge text; `glab api` and graphql notes |
| guard-bypass-labels | `-l` on `glab issue\|mr create\|update`, `glab label edit -n`, `glab api` labels, graphql labelIds |
| guard-duplicate-prs | `glab mr create` descriptions, judged against each issue's related merge requests |
| guard-git-stacked-base | branch deletions by git or `glab api`, judged by `glab mr list` on target and source branch |
| guard-cross-session-send | glab's issue, merge request, note, pipeline, job log, release and repo reads, and `glab api` reads |
| guard-bypass-ruleset | a push to a protected default branch no role may push to; a user or group allowed there is the bypass |
| guard-review-threads, guard-signed-comments | none (planned): the reads and writes a port needs are documented, but not on the note itself whose account is a bot (below) |
| GitLab's MCP tools | (planned), once their names are verified |

Why those two have no row. GitLab resolves a thread by `PUT
projects/:id/merge_requests/:iid/discussions/:discussion_id` with `resolved=true`, or by
`glab mr note resolve [<mr>] <discussion-id|note-id>` (a discussion id, a prefix of 8 or
more characters of it, or a note id; glab marks the verb experimental), and reads it with
`GET` on the same path. A note is posted by `POST
projects/:id/merge_requests/:iid/notes`; all of these are in GitLab's and glab's docs.
What the docs leave out is a bot field on the note: its embedded author object carries
none. The Users API does (`GET /users/:id` shows `bot`; `GET /users` filters with
`humans` and `without_project_bots`), so telling a bot costs a second read per author,
and which usernames count (project and group access-token accounts, a named list) is a
design choice, as is how guard-signed-comments tells its bot's account. Until that
choice, neither guard reads glab: a GitLab thread resolved or note posted passes both unjudged.

Each row's glab verbs and API paths are cited from glab's and GitLab's own
docs in that guard's feature file. A verb those docs do not show stays out
of the row.
