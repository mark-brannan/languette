# Decisions

Rulings that settle languette's public interface. The README says what the
interface is; this file says who decided it and why, one line each.

## ask-first config: Solace, 2026-10-02 and 2026-10-03

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

## Parser ladder: Solace, 2026-10-06

- The shell parser's cascade (#4), in order: a user-installed `shfmt`
  first, then a pip-installed parser, and awk only when none of those is
  available.
- Which pip parser, or both in turn (tree-sitter-bash, bashlex), is open (#4).

## Parser ladder refusals: Solace, 2026-10-07

- `bash -n` is a rung; a rung reads, refuses (a deny naming it) or passes down.
- tree-sitter-bash refuses on an ERROR node; bashlex on an unclosed quote,
  bracket or unexpected end; the built-in lexer on an unclosed quote.

## Parse check: Solace, 2026-10-07

- shfmt is the critical path; below it, `bash -n` decides the parse check; a
  pip parser, if installed, only adds the column.
- This replaces the pip parsers' refusals in the ruling above: tree-sitter-bash
  and bashlex no longer refuse.

## Runtime dependencies: Solace, 2026-10-06

- Languette runs on python3 and its standard library plus the parser ladder
  above, takes no other dependency, and depends on nothing in
  mark-brannan/claude: `jq` goes, `prose-budget-commit` loses its engine
  there, and `no-checkout-home` recognises the shape of a command that checks
  out `$HOME` through git, yadm, chezmoi or another common dotfiles manager,
  without needing that tool installed. `gh` is optional, for
  `no-delete-stacked-base` only.

## Guard names: Solace, 2026-10-07

- Every guard is named `guard-<concept>`, the asset or scenario it guards
  against; no `no-` prefix, no "footguns". One guard per concept, a setting
  per scenario inside it.
- `no-rm-tree` is `guard-recursive-delete`, `no-iac-destroy`
  `guard-infra`, `issue-door` `guard-github-issues`, `public-issue-guard`
  `guard-private-terms`; config keys follow, with underscores. The rest are
  renamed as reached.

## Three concerns: Solace, 2026-10-07

- Parse reads the command into parts. Guards are pure functions reporting
  findings. Verdict turns findings and configuration into an action.
- Guards needing enriched data: how is unruled; first try is
  request-and-answer (#79).

## The guard pipeline: Solace, 2026-10-07

- Six steps: parse, plan, gather, guard, verdict, act. Plan, guard and
  verdict are pure; gather reads, act writes.
- A guard splits into plan and judge when its questions are known after
  the parse.
- Design: [docs/design/guard-pipeline.md](design/guard-pipeline.md).

## Gather reads only: Solace, 2026-10-09

- No Need writes or runs a host-named program. Scar: #107.
- The readable set is the read kinds in `KINDS` in `languette/world.py`.
- Whether `prose-budget-commit` keeps running the engine `prose_budget_bin`
  names is unruled.

## New guards: Solace, 2026-10-09

- A guard enters languette through an issue, never straight from a miss.
  Issue fields: incident, root cause, hazard, concept, name. Scar: #125.
- Hazard: why it could ruin a day, as the README's lede puts it; a waste
  of an hour is not one. Concept: a setting of an existing guard, or a new
  one. Name: under the naming ruling above.
- Root cause first, guard second. A miss is often a workflow gap, and a
  guard at most a backstop for it.
- No prototypes here, not even as drafts; a closed PR is residue. A quick
  fix lands in the author's own hook layer, or an unstable sibling repo, and
  comes here once Solace puts the GitHub label `ready` on its issue.
- If prototyping outside is hard because the parser and engine live here,
  the fix is to expose those interfaces, not to admit the prototype.
- Whether guards that watch an agent's conduct on GitHub (#118, #119, #125)
  are one concept or several is unruled.
- Prose now; a check with teeth once the gate's shape is settled.

## Base-case guard names: Solace, 2026-10-09

- `require-well-formed` replaces `guard-unparsable`. Well-formed means
  parsed whole, within the size and depth bounds.
- `ask-first` and `deny-always` stand, in pen for now; config's form may
  change them, or merge them into one guard.
- These name what happens, outside the `guard-<concept>` scheme. The
  suffix `-first` is not reserved.
