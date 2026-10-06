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

## License: Solace, 2026-10-04

- languette stays unlicensed (all rights reserved), confirming #25. Not
  revisited before 2026-11-04, unless someone outside asks to use or fork it
  first.

## Shell parser: Solace, 2026-10-04

- Languette goes to a real shell parser (#4); it is part of the value
  proposition.
- The engines cascade: a guard uses whichever the user has installed, the
  parser first and awk last.

## Parser ladder: Solace, 2026-10-06

- The cascade's order: a user-installed `shfmt` first, then a pip-installed
  parser, and awk only when none of those is available.
- Which pip parser, or both in turn (tree-sitter-bash, bashlex), is open (#4).

## Runtime dependencies: Solace, 2026-10-06

- Languette runs on python3 and its standard library plus the parser ladder
  above, takes no other dependency, and depends on nothing in
  mark-brannan/claude: `jq` goes, `prose-budget-commit` loses its engine
  there, and `no-checkout-home` recognises the shape of a command that checks
  out `$HOME` through git, yadm, chezmoi or another common dotfiles manager,
  without needing that tool installed. `gh` is optional, for
  `no-delete-stacked-base` only.
