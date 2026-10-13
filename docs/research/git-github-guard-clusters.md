# Git and GitHub guards: the regex guard's rules beside ours, clustered by harm

Step one of #134. Every guard name below is a candidate; none is approved.

## Sources

- the regex guard: a public command guard that decides each command by
  regex, `Dicklesworthstone/destructive_command_guard` at `467a3be`
  (default branch, fetched 2026-10-10). Packs read: `core.git` (25 destructive, 7 safe
  rules), `strict_git` (19 destructive), `platform.github` (20 destructive,
  13 safe), `cicd.github_actions` (6 destructive, 7 safe). Rule ids were
  extracted by pattern from the Rust source; the counts are `destructive_pattern!`
  occurrences. Its GitLab, Azure DevOps and CI packs for other vendors are out of range.
- languette: `languette/guards/` and `features/` on `main` at `f89f0e1`;
  open PRs #118 and #119 (verified open); #125 as listed in #134, not re-checked.

## What each side covers

| Regex-guard pack | Opt-in? | Reads as |
|---|---|---|
| `core.git` | always on | discard uncommitted work, rewrite history, force push, delete refs, drop stashes, LFS loss |
| `strict_git` | opt-in | every force push and ref delete, rebase, amend, cherry-pick, `gc`, `add .`, push to main |
| `platform.github` | opt-in | `gh` deletes (repo, gist, release, issue, keys, secrets), visibility, archive, run cancel |
| `cicd.github_actions` | opt-in | secret and variable removal, workflow disable, run cancel, `gh api DELETE` on actions |

The regex guard decides one command at a time, with a hand-written safe pattern
(for example `checkout -b`, `restore --staged`, `clean -n`) beside each
destructive one. It has no notion of who is acting, no GitHub lookups, no
approval flow and no memory between calls.

languette's shipped and pending members:

| Member | What it refuses | Needs GitHub or state? |
|---|---|---|
| `guard-git-work-loss` | blanket staging, stash pop/drop/clear, force push, discard (`checkout .`, `restore .`, `clean -f`, `reset --hard`), `branch -D` | no; one switch per rule |
| `guard-git-stacked-base` | deleting a remote branch an open PR names as base or head | yes (`gh pr list`); asks when it cannot answer |
| `guard-bypass-hooks` | `--no-verify`, `-n` on commit/am, `core.hooksPath` | approval, spent once |
| `guard-bypass-labels` | an agent applying `churn-ok`, `mixed-loops-ok` | no (reads flags, `gh api`, MCP fields) |
| `guard-bypass-ruleset` | a push to the default branch that needs a PR; `gh pr merge --admin` | yes (rulesets, cached an hour) |
| #118 `guard-review-threads` | resolving a bot's thread with no reply that names a commit or link | yes |
| #119 `guard-signed-comments` | a GitHub comment not signed as an agent's | session id |
| #125 `guard-duplicate-pr` | opening a PR that closes an issue an open PR already references | yes (issue timeline) |
| `guard-github-issues` (approved) | more than one issue create/transfer/delete per human turn | per-turn door |
| `guard-private-terms` (approved) | a private term in text bound for a public repo | terms file |
| `guard-commits` (approved) | a commit failing a check the repo lists (today: `prose-budget-commit`, which warns) | engine on PATH |
| `guard-worktrees` (approved) | branch switch in a `$HOME` worktree; another session's worktree | worktree list |

## Clusters by harm

Clustered by what is lost or spent, not by git or GitHub object. "Gap" means
the harm is in the cluster and neither side's rule set covers a member.

| # | Harm | Regex-guard rules | languette today | Gap or overlap |
|---|---|---|---|---|
| A | Uncommitted work lost in the working tree or index | `checkout-discard`, `restore-worktree`, `reset-hard`, `clean-force` | `guard-git-work-loss` discard rules | The regex guard is wider: `switch -f`, `rm -f`, `read-tree --reset`, `reset --merge`, `show ref:path > path`. |
| B | Stash lost | `stash-drop`, `stash-clear` | `guard-git-work-loss` (stash pop/drop/clear) | languette also denies `pop`, because the stack is shared across worktrees. |
| C | Committed history rewritten or unreachable locally | `filter-branch`, `branch-force-delete`; strict: `rebase`, `commit-amend` | `branch -D` only | Largest gap. Rebase and amend are plausible agent moves; the regex guard bans them, ban or ask is undecided. |
| D | Remote history rewritten or remote refs deleted | `push-force-long`; strict: `push-force-any`, `push-mirror`, `push-delete` | `guard-git-work-loss` force push; `guard-git-stacked-base` remote deletion when a PR depends on it | The regex guard denies on shape, `stacked-base` on a live fact (an open PR). `--mirror` reaches only `guard-bypass-ruleset`; `--prune` is unmatched. |
| E | Pushing around the repo's review path | strict: `push-main`, `push-master` | `guard-bypass-ruleset` (asks GitHub whether the branch needs a PR) | The regex guard hard-codes two branch names; ours reads the repo's own rules. Same harm. |
| F | Skipping the repo's own checks | none | `guard-bypass-hooks` | Ours only. `guard-commits` (approved) is the positive side of the same harm: run the checks. |
| G | Secrets or junk committed by blanket staging | strict: `add-all-dot`, `add-all-flag` | `guard-git-work-loss` blanket staging; `guard-secrets` (approved) | Same harm, two homes. |
| H | Git LFS data lost | `lfs-prune`, `lfs-uninstall`, `lfs-migrate-rewrite` | none | Gap. No evidence an agent session meets LFS. |
| I | A GitHub object destroyed for good | `gh-repo-delete`, `gh-api-delete-repo`, `curl-api-delete-repo`, `gh-api-delete-generic` | `guard-github-issues` covers issue delete only, and as a count | Large gap. Repo, release and gist deletion are unguarded. |
| J | Access or CI configuration removed or changed | `gh-secret-delete`, `gh-repo-deploy-key-delete`, `gh-repo-visibility-change`; gha: `workflow-disable` | `guard-bypass-ruleset`, `guard-bypass-labels` guard the gates, not the config | Gap. Visibility change also touches `guard-private-terms`' premise (public vs private). |
| K | A running job interrupted | `gh-run-cancel`, `gh-actions-run-cancel` | none | Gap; the regex guard itself calls it reversible. |
| L | A gate waived by the gated party | none | `guard-bypass-labels`, `guard-bypass-ruleset` (`--admin`), `guard-bypass-hooks` | Ours only; this is the cluster the regex guard has no concept for, because its actor is anonymous. |
| M | An agent's words taken as the user's | none | #119 signed comments, #118 review threads | Ours only. |
| N | Private text leaving the machine | none | `guard-private-terms` | Ours only. |
| O | Identifiers minted that cannot be recalled | none (`gh-issue-delete` is the nearest) | `guard-github-issues`, #125 duplicate PR | Ours only. |
| P | Another session's work disturbed | none | `guard-worktrees` | Ours only. |

<details>
<summary>All regex-guard rule ids behind the trimmed rows (A, C, D, I, J)</summary>

```
A  checkout-discard, -ref-discard, -discard-cwd, -force; switch-discard;
   restore-worktree, -explicit; reset-hard, reset-merge; clean-force;
   rm-force; read-tree-reset; show-redirect-overwrite-source
C  filter-branch, reflog-expire-now, lfs-migrate-rewrite, update-ref-delete,
   branch-force-delete; strict: rebase, commit-amend, cherry-pick,
   filter-repo, reflog-expire, gc-aggressive, submodule-deinit,
   worktree-remove
D  push-force-long, -short, -refspec; strict: push-force-any, push-mirror,
   push-delete, push-delete-refspec, push-prune, push-dynamic-argument
I  gh-repo-delete, -gist-delete, -release-delete, -release-delete-asset,
   -issue-delete, gh-api-delete-repo, -release, curl-api-delete-repo,
   gh-api-delete-generic
J  gh-ssh-key-delete, gh-repo-deploy-key-delete, gh-secret-delete,
   gh-variable-delete, gh-api-delete-hook, -deploy-key, -actions-secret,
   -actions-variable; gh-repo-visibility-change, gh-repo-archive;
   gha: secret-remove, variable-remove, workflow-disable, api-delete-*
```

</details>

Reading the table: A through E and I through K are about destroying state, and
the regex guard has the longer list. F and L through P turn on a fact, a count or an
actor that a pattern cannot see, and only languette has them. That split is the
useful finding: the two are different kinds of rule (see below).

## Candidate names

All are candidates under the pattern in `approved-guard-names.md` (countable
thing plural, act or mass noun singular). None is proposed for approval.

| Cluster | Candidate | Concept (one line) | Existing home |
|---|---|---|---|
| A, B | `guard-work-loss` | uncommitted work and stashes | today's `guard-git-work-loss` minus its push and branch rules |
| C, D | `guard-history` | commits and refs rewritten or deleted, local or remote | split of `guard-git-work-loss` and `guard-git-stacked-base` |
| D (live fact) | `guard-git-stacked-base` stays | remote branch an open PR needs | unchanged |
| E, L | `guard-bypass-ruleset` stays | review path skipped | unchanged |
| F, L | `guard-bypass-hooks`, `guard-bypass-labels` stay | gate waived | unchanged; the overrides umbrella is set aside per the issue |
| G | fold into `guard-secrets` and blanket staging | what a commit sweeps in | needs a call |
| I, J, K | `guard-github-repos` | repo, release, gist, key, secret, visibility | new; cluster I and J might split |
| J, K | `guard-github-actions` | workflows, runs, Actions secrets | new; the regex guard keeps this a separate pack |
| M | `guard-github-reviews` (from #134) | review threads and signed comments | #118, #119 |
| O | `guard-github-issues` (approved) and a PR sibling | numbered things minted | #125 |
| F (positive) | `guard-commits` (approved) | commit checks run | joins this workshop per the issue's comment |

Name hazards seen: `guard-git-work-loss` already spans four harms (work, stash,
push, branch delete), so its name no longer says what it refuses. `guard-github-*`
today names an object (issues, planned reviews); clusters I and J name an
object too, but cluster M is about authorship, not the object.

## Domain guards or one rules engine

Both are undecided. What each costs, from the code as it stands:

| | Domain guards (today) | One rules engine over git and GitHub actions |
|---|---|---|
| Unit | one guard module per harm, own switch, own feature file | one rule table; a rule is data: action pattern, conditions, outcome (deny, ask, allow) |
| Live facts | any guard can yield a `Need` (gh lookup, rulesets, issue timeline) | rules need a condition vocabulary for facts; every new fact is a new language feature |
| State | per-turn door, spent approvals, caches live in the guard | state has no home in a table; it stays code, so the engine is not the whole set |
| Parsing | each guard rereads git/gh options with `scan` helpers, with some duplicated flag logic (`GIT`, `GLOBAL_VALUE` appear in several modules) | one reader of git and gh options, written once |
| Adding a regex-style rule | a code change, or a setting in the guard it belongs to | a data line; the regex guard's ~70 git and GitHub rules would be 70 lines |
| Testing | a feature file per guard | the table plus one spec per rule kind |
| Risk | stretching a name (the problem #134 started from) | defining the rule language; a table that cannot say "an open PR exists" or "this label is on the list" falls back to code anyway |
| Precedent here | every shipped guard | `ask-first` already matches command patterns to an outcome from a repo list; `deny-always` is approved, not built |

Evidence that bears on the choice, from the clustering:

- Clusters A through E, I through K are pattern to outcome. A table fits them,
  and `ask-first` already hosts that shape (`deny-always` is approved, not built). These are the clusters
  the regex guard is strong in.
- Clusters F, L through P turn on a lookup, a count, a signature or a record
  of approval. A table does not hold them without a condition vocabulary.
- A hybrid is possible: the pattern-to-outcome clusters as data (possibly just
  more entries for the existing `ask-first` list, shipped as a
  default git/GitHub list), the fact-bearing clusters as domain guards. This is
  a guess, not tested; it leaves the rule-language cost small because the
  language never needs conditions.
- Open: whether a shipped default list is languette's job at all, or the
  user's, since `ask-first` is described as the repo's own list.

## Questions for the maintainer

1. Is the regex guard's stricter tier (rebase, amend, cherry-pick, any force push, `gc`) in
   range, as a deny, an ask, or out? Cluster C is the largest gap.
2. Are clusters I through K (repo, release, secret, visibility deletion) in
   range at all, or is `gh` outside the agent's reach by other means?
3. Does `guard-github-issues` stay one guard, or does a PR sibling join it
   (#125)? Reopening an approved name is a ruling.
4. Does `guard-commits` stay about checks, or also absorb G (what a commit
   sweeps in)?

## Follow-up

Draft issue, not filed:

> **Git and GitHub guards: narrow the clusters to concepts**
> Report: `docs/research/git-github-guard-clusters.md` (#134 step one).
> Rule on the four questions at its end (strict tier, GitHub deletions, issue/PR sibling, `guard-commits` scope), then pick domain guards, a rules engine, or the hybrid.
> Names follow from that; only then does `approved-guard-names.md` change.
