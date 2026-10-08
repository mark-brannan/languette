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
