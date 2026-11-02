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
and graphql mutations reach its harm. Each ported guard has a scenario per
forge in its feature file. Today the rows sit in the guard; on the engine
they become rule data, one `match` entry per client (planned).

| Guard | GitLab |
|---|---|
| guard-github-issues | `glab issue create\|new\|delete\|del`; `glab api` issue create, clone, move, delete; graphql `createIssue`, `workItemCreate`, `issueMove`, `workItemDelete` |
| private-terms, signed-comments, bypass-labels | notes, labels, project visibility (planned) |
| duplicate-prs, review-threads, bypass-ruleset | merge requests, discussions, protected branches (planned) |
| GitLab's MCP tools | (planned), once their names are verified |
