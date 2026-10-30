# Guard rules

The design behind #198, on [the guard pipeline](guard-pipeline.md). Present
tense is the aim, not today's code; the decisions are in
[decisions.md](../decisions.md). Field names are a sketch, not a schema.

## Purpose

A new guard should cost a few rules, not a file of matching code. Twenty-six
guards ask thirty-six questions between them, and every one composes named
tests with all, any and not; none needs an expression. The repetition is in
how a guard reaches the words it tests and the facts it needs: the `gh api`
walk is written eight times, cd tracking four, "is this word live" thirteen.

So there is one engine. A guard is a rule set held as data. Code is the
engine, the primitives a rule may name, and the messages. A rule says which
calls, under which conditions, get which verdict; it runs nothing and names
no program to run. Configuration first: a rule set is readable without
reading Python, and a guard is tested by its feature file as today, so moving
it onto the engine changes how it is written, never what it decides.

## A rule

```json
{"guard": "guard-github-issues",
 "rules": [{"id": "issue-write", "action": "deny",
            "match": {"any": [{"cmd": "gh", "args": ["issue", "create"]},
                              {"cmd": "gh", "args": ["api"], "method": "POST", "path": "repos/*/issues"},
                              {"tool": "mcp__github*__create_issue"}]},
            "when": {"all": [{"fact": "door", "is": "open"}, {"not": "in-loop"}]},
            "why": "issue_door_shut"}],
 "on": {"UserPromptSubmit": "door-open", "PostToolUse": "door-spend"}}
```

- `match` selects calls: a command word and its non-option words, as
  ask-first writes them today, with flags, a tool name, a path or a text
  pattern. The scanner sees through wrappers, chains, `sh -c` and launchers.
  A command word may be held to where it runs, never another command's
  argument (`apt-get install sudo` is not `sudo`).
- `when` is predicates over the matched words and over facts, under `all`,
  `any` and `not`. Absent, the match alone decides.
- `action` and `why`: the verdict, and the message key that explains it.
- `on` names the event handlers a stateful guard keeps, by name.

Each rule that matches is one finding; verdict combines findings as today.

## Primitives

What a rule may name, each a Python function in languette with a name in a
closed registry. Three kinds:

| Kind | Does | Examples |
|---|---|---|
| selector | finds the words, paths or text a call carries | `cmd`, `flags`, `path` (a `gh api` path), `text` (literal values, heredocs, a body file, an MCP tool's strings) |
| predicate | tests words or facts, pure | subcommand-in, word-live, cd-present, flag-in-cluster, option-value-in, text-matches, long-prefix, setting-equals |
| fact | a Need kind and a pure shaping of its answer | the repo a cwd's origin names, whether a path exists, the door's state |

A program description belongs to selectors: which options take a value, so a
value is never read as a subcommand, and where the subcommand sits. git's
comes from #197's finder; infra's `VALUED` table is the same thing for six
programs.

The registry grows when a rule needs a primitive, not before. Seventeen
predicates serve one guard each today; those are that guard's own logic and
stay beside it, named, until a second guard asks. A primitive two guards
share lands in scan or verdict first (decisions: "New guards").

Sequence is a fact, never a condition: the five guards that would lose
precision as pure data (git-work-loss relaxations, bypass-ruleset binding,
private-terms' rewrite, signed-comments tracing, worktrees landings) lose it
on order within a command, and order is computed per segment in gather.

## Actions

A verdict only tightens. A rule's action is `deny`, `ask` (ask-first's
approval, spent once per run when the rule says so), `context` or `rewrite`;
allow only follows a redaction. A rewrite transforms data, so a repo rule may
loosen one a wider tier applies; what each tier may say is open below.

`rewrite` replaces inside the text a call carries, never its words or flags.
The rule names what to find, a term, a secret shape or the value of an
environment variable such as `HOME`, and what to put there: `~`, the literal
`$HOME`, a placeholder. The replacement is spliced as data into the matched
literal span, never across a quote boundary; a find that would cross one is
a deny. The new bytes are parsed and judged again by every rule; a rewrite
that still matches a deny is a deny. A redaction is then allowed, Verdict
carrying the rewrite; any other rewrite is asked about, before and after in
the reason. guard-private-terms' redactions are the first rules on it: the
entries in the user's redacted terms file, whose defaults (home, host and
address shapes) the doctor writes there; secret redaction is another.

## Plan from the rules

The engine reads a rule set and knows its facts before gather: every `when`
names them, and every fact is a Need kind. So plan is a function of the
configuration and the parse, as the pipeline requires, and the two shapes of
guard are two shapes of rule set: plan/judge when `when` names facts alone,
ask-as-it-goes when a fact's argument is another fact's answer. State across
calls is a fact read in gather and a write made in act by a handler `on`
names; the handler is code, as the issue door's protocol is today.

## Trust tiers

| Tier | Lives | May say |
|---|---|---|
| shipped | `languette/rules/`, one file per guard | everything above |
| user | a file the user names in the plugin options; guard-private-terms' redacted terms file is the first | everything above |
| repo | `.languette/`, agent-writable | data that adds `deny`; the rest open |

Primitives are Python in languette at every tier; no tier loads code. An
agent writes the repo tier, so what it may say is bounded by what an agent
could abuse: a rule that loosens, or one that puts code into the process that
judges it. A plug point for outside code is not designed; it enters by
request, as an issue.

## Rule sets that do not load

A rule set that does not parse, names an unknown primitive, or has another
shape, denies every call its guard would judge, naming the file and the
fault. That is ask-first's and guard-secrets' behaviour today. A test loads
every rule set languette ships, so that deny never greets an install.
guard-private-terms' two lists deny only its own public-bound posts.

## Path there

From today's guards to the engine, in order. A stage that lands leaves this
list; what it built is then described above.

1. The registry: the shared selectors first (the `gh api` walk, cd
   tracking, word-live, the valued-option tables), each landing with the
   guards that repeat it moved onto it.
2. The command guards move, smallest first; then the text guards, whose
   `secret_rules`, term list and label list are already data.
3. The stateful guards: their rules move, their handlers stay code.
4. The repo tier, once its bounds are decided.

Lines, from the survey: ~3000 of guard code become data plus engine, ~1500
stay code, ~2000 are messages and stay where they are.

## Open

- `rewrite` then allow, with a note to the agent after the call runs, for a
  safer flag (`--force` to `--force-with-lease`). It would keep an unattended
  session going where an ask is a deny, as a redaction's allow does; the
  user never sees the bytes. Today a safer flag is a deny with the fix in the reason.
- Repo-tier actions: `ask` and `context`, probably yes; `rewrite`, at least
  dropping a wider tier's pair, though it then runs with the agent's privileges.
- A repo rule naming a fact that costs network or a program run.
- #134's step 3 asks the same question for git and GitHub alone; this design
  is one answer to it, not a decision on it.
