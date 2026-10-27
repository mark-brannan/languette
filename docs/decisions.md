# Decisions

Decisions that settle languette's public interface. The README says what the
interface is; this file says what was decided and why, one line each. Every
line is the maintainer's (@mark-brannan) unless it says otherwise.

## ask-first config: 2026-10-02 and 2026-10-03

- The config lives at `.languette/ask-first.json`, replacing
  `.claude/languette-ask.json`. The folder names who made it and the file
  names the guard; no agent host is in the path, since other hosts are on the
  roadmap (#5).
- It is not marked experimental. The interface is designed before anyone else
  adopts it.
- `approve_label` is the text of the yes button the agent must offer the user.
  Each click allows one run. Labels are unique within the file, so a click
  approves exactly one command.
- The agent's question is not checked for the command's `id`. The agent writes
  the question, so only the user's click proves anything; the id is the
  command's name in messages.
- `cost` is free text, which the agent repeats to the user when it asks, for
  example `"> 40 minutes, using all CPU cores on a typical desktop"`.
- No `cost_from` (#24, closed). Reading the cost from another file saved one
  repeated sentence and added a way for the command to run unasked: a slow
  pattern times the hook out, and a timed-out hook does not block.
- Examples and fixtures use generic commands, not one project's.

## Parser ladder: 2026-10-06

- The shell parser's cascade (#4), in order: a user-installed `shfmt`
  first, then a pip-installed parser, and awk only when none of those is
  available.
- Which pip parser, or both in turn (tree-sitter-bash, bashlex), is open (#4).

## Parser ladder refusals: 2026-10-07

- `bash -n` is a rung; a rung reads, refuses (a deny naming it) or passes down.
- tree-sitter-bash refuses on an ERROR node; bashlex on an unclosed quote,
  bracket or unexpected end; the built-in lexer on an unclosed quote.

## Parse check: 2026-10-07

- shfmt is the critical path; below it, `bash -n` decides the parse check; a
  pip parser, if installed, only adds the column.
- This replaces the pip parsers' refusals in the decision above: tree-sitter-bash
  and bashlex no longer refuse.

## Runtime dependencies: 2026-10-06

- Languette runs on python3 and its standard library plus the parser ladder
  above, takes no other dependency, and depends on nothing in
  the maintainer's own hook layer: `jq` goes, `prose-budget-commit` loses its engine
  there, and `no-checkout-home` recognises the shape of a command that checks
  out `$HOME` through git, yadm, chezmoi or another common dotfiles manager,
  without needing that tool installed. `gh` is optional, for
  `no-delete-stacked-base` only.

## Guard names: 2026-10-07

- Every guard is named `guard-<concept>`, the asset or scenario it guards
  against; no `no-` prefix, no "footguns". One guard per concept, a setting
  per scenario inside it.
- `no-rm-tree` is `guard-recursive-delete`, `no-iac-destroy`
  `guard-infra`, `issue-door` `guard-github-issues`, `public-issue-guard`
  `guard-private-terms`; config keys follow, with underscores. The rest are
  renamed as reached.

## Three concerns: 2026-10-07

- Parse reads the command into parts. Guards are pure functions reporting
  findings. Verdict turns findings and configuration into an action.
- Guards needing enriched data: how is open; first try is
  request-and-answer (#79).

## The guard pipeline: 2026-10-07

- Six steps: parse, plan, gather, guard, verdict, act. Plan, guard and
  verdict are pure; gather reads, act writes.
- A guard splits into plan and judge when its questions are known after
  the parse.
- Design: [docs/design/guard-pipeline.md](design/guard-pipeline.md).

## Gather reads only: 2026-10-09

- No Need writes or runs a host-named program. Scar: #107.
- The readable set is the read kinds in `KINDS` in `languette/world.py`.
- Whether `prose-budget-commit` keeps running the engine `prose_budget_bin`
  names is open.

## New guards: 2026-10-09

- A guard enters languette through an issue, never straight from a miss.
  Issue fields: incident, root cause, hazard, concept, name. Scar: #125.
- Hazard: why it could ruin a day, as the README's lede puts it; a waste
  of an hour is not one. Concept: a setting of an existing guard, or a new
  one. Name: under the naming decision above.
- Root cause first, guard second. A miss is often a workflow gap, and a
  guard at most a backstop for it.
- No prototypes here, not even as drafts; a closed PR is residue. A quick
  fix lands in the author's own hook layer, or an unstable sibling repo, and
  comes here once the maintainer puts the GitHub label `ready` on its issue.
- If prototyping outside is hard because the parser and engine live here,
  the fix is to expose those interfaces, not to admit the prototype.
- Whether guards that watch an agent's conduct on GitHub (#118, #119, #125)
  are one concept or several is open.
- Prose now; a check with teeth once the gate's shape is settled.
- 2026-10-13: a new guard is written against the shared layer
  first: Document for the call, scan for the words, verdict for the
  answer. A primitive the guard needs that two or more guards would share
  (a program pattern, an option walk, a sentence) goes into scan or
  verdict in the same PR, and the siblings that repeat it move onto it, or
  an issue names them. A guard that reads sequential or external facts (PR
  state, review threads, a transcript) is the exception, not the shape.
- Current thinking, not settled: guards trend toward a rules engine with a
  few deep special cases.

## Base-case guard names: 2026-10-09

- `require-well-formed` replaces `guard-unparsable`. Well-formed means
  parsed whole, within the size and depth bounds.
- `ask-first` and `deny-always` stand, in pen for now; config's form may
  change them, or merge them into one guard.
- These name what happens, outside the `guard-<concept>` scheme. The
  suffix `-first` is not reserved.

## License and versions: 2026-10-08 and 2026-10-09

- Code is AGPL-3.0-or-later and prose is CC BY-SA 4.0 ("AGPL + CC SA for
  writing").
- The first release is 0.0.1, carrying `languette doctor`.
- Every release bumps the patch number only, until the maintainer says otherwise. No
  semver; a review that asks for a minor or major bump is out of scope.

## Releases and titles: 2026-10-10

- The maintainer ships when ready, by merging the standing release pull request.
  Work piles up in it until then; nothing ships on a schedule.
- Pull request titles, and so the squashed commits, carry a conventional
  type with the area as its scope: `fix(doctor): …`, not `doctor: …`.
- Docs changes count toward a release, so a README fix can open the
  release pull request. Opening it obliges nothing.

## Trust and licence riders: 2026-10-09

- No licence rider against AI companies: AGPL answers hosting, and no licence
  answers training. The README states the distrust as a position, not a condition.

## One rules engine: 2026-10-27

- Primitives (selectors, predicates, facts) are Python inside languette.
  The user tier and the repo tier hold rules as data, never Python, at
  every tier. Current thinking.
- A plug point for outside code, reusing the scanner or the engine in a
  user's own hook, is not designed; it enters by request from a user, as
  an issue. Current thinking.
- `rewrite` is a rule action: it replaces inside the text a call carries,
  never its words or flags; the result is judged again by every rule. A
  redaction is then allowed, any other rewrite asked about, before and after
  in the reason. Shipped and user tiers only.
- What a rewrite finds and puts is the rule's: a term, a secret shape or an
  environment variable's value, replaced by `~`, the literal `$HOME`, a
  placeholder or another variable's name.
- Rewrite then allow, with a note to the agent after the call, for a safer
  flag: open, no strong view.
- Design: [docs/design/guard-rules.md](design/guard-rules.md).

## guard-private-terms: 2026-10-27

- No environment variable configures languette. One is a last resort, for a
  pressing need with real design intent behind it.
- guard-private-terms is two behaviours. Anonymize rewrites text bound for
  a public repo by a list of [find, put] pairs and allows the call: shipped,
  the home directory ($HOME and its other spellings, such as /home/<user>,
  /Users/<user>, /mnt/c/Users/<user>) to `~`; the user's own in a rewrites
  file. It is on by default, needs no configuration and runs whether or not
  a blocked terms file is set. Hard block denies the whole post for a term
  on a short list of really sensitive terms, where even a redacted post
  could leak concepts or strategy. Only the hard block needs its file, and
  only it fails closed on text it cannot see.
- Rewrite then allow is the action for redaction.
- The hard block's list is the blocked terms file, option `blocked_terms_file`,
  default `~/.config/languette/blocked-terms.txt`. "Private terms" names the
  guard and what anonymize redacts; "blocked" says what the list does.
- The rewrites file, option `rewrites_file`, default
  `~/.config/languette/rewrites.json`, is `{"rewrite": [[find, put], ...]}`:
  the `rewrite` rule's own find and put, so it reads unchanged as the user
  tier's first rule set when the engine lands. A find `$NAME` is that
  variable's value; a pair with no put puts `<redacted>`. Current thinking.
- A list that is missing or unreadable never fails a call: a cloud session
  has no copy of it. ([thread](https://github.com/mark-brannan/languette/pull/290#discussion_r4395050677))
- A rewrite transforms data, so a per-repo rule may loosen one a wider tier
  applies. Current thinking. ([thread](https://github.com/mark-brannan/languette/pull/290#discussion_r4395034528))
- Anonymize never denies for text it cannot read; only a loaded blocked
  terms list fails closed there.
- Spec: [features/guard-private-terms.feature](../features/guard-private-terms.feature).
