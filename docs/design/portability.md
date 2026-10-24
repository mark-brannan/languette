# Portability

What languette may and may not assume about the machine, the account and
the workflow it runs in. Present tense is the aim; "(planned)" marks where
the code lags. The other design docs: [the guard
pipeline](guard-pipeline.md), [guard rules](guard-rules.md),
[exceptions](exceptions.md).

## Purpose

Languette is for anyone who runs an agent, not for the one setup it was
born in. Every assumption about its first home that reaches the code is a
step a new user must undo before the guards are theirs, and most such
steps are invisible until a stranger trips on one. Without a written rule
new work slides back toward the maintainer's own machine, login and
habits, because that is where it is tested. This document is the line.

## The rules

> Nothing in the package, the hooks, the specs or the tests names the
> maintainer or the maintainer's setup, and nothing depends on it.

1. **No identity.** No login, name, email address, hostname, home path or
   repository of the maintainer's appears in the package, the hooks, the
   feature files or the tests. Fixtures use placeholders that are plainly
   placeholders. The project's own homepage and links to its own issues
   are the one exception, and they live in metadata and prose, never in a
   rule a guard applies.

2. **Paths are resolved, never assumed.** The home directory, the state and
   cache directories and the agent's own configuration are found where the
   platform and the agent say they are, at run time. No path is written as
   if every user's home were under the same parent, and no rule assumes a
   second user, a container or another operating system lays its home out
   as the maintainer's does.

3. **The default branch is read, never presumed.** A guard that needs the
   default branch asks the repository. A fixed name is a last fallback for
   when the repository cannot say, and the reason says so.

4. **A workflow convention is an option, off by default.** Labels, comment
   signatures, release rituals, the names of bypass tokens, the shape of a
   review reply: any of these that one workflow uses is a setting with a
   name and an empty default. A guard that enforces a convention runs only
   when its setting turns it on, and its reason names the setting.

5. **No shared identity between agent and user.** Nothing assumes the agent
   acts under the user's own login, that there is one user, or that one
   person is both maintainer and operator. Where the agent's identity
   matters, it is read from the payload or a setting.

6. **A fork is a first-class install.** The repository's own automation
   runs green on a fork with no secrets and no owner-only access, or stays
   out of the fork's way by an explicit gate. Nothing a contributor runs
   needs the maintainer's account.

7. **The toolchain is found on the path.** Languette needs an interpreter,
   git and the GitHub client, and nothing else outside the standard
   library. Each is found on the path, never at a fixed location. WSL is
   the first platform and the README leads with it on purpose; it is a
   recommendation, not an assumption. Nothing in the code requires WSL,
   and the maintainer runs it on more than one platform.

8. **Costs are declared, not discovered.** What a check may read, run or
   fetch is written down per test and held there, so a new platform or a
   stranger's machine meets no surprise. The budget lives with the tests.

9. **A tool is recognised by what it does, not by who uses it.** A program
   that rewrites the work tree, moves a branch or deletes outside the
   repository is dangerous for that reason, whoever's habit it is. When
   one such program is named, the name stands for a class, and the rule
   says which class.

## What enforces it

A test holds rule 1 (planned): a denylist of the maintainer's identifiers
over the package, the hooks, the feature files and the tests, with an
allowlist for the project's own metadata and issue links. Rule 8 is held
today by the per-test I/O budget. The rest are review rules until each
gets a check; this document is what the reviewer reads.

## What this document is not

It is not a list of today's violations. Those are issues, fixed in their
own pull requests. It is not a platform support matrix; the README owns
that.
