# Guard rules

The design behind #198, on [the guard pipeline](guard-pipeline.md). Present
tense is the aim, not today's code. Field names below are a sketch, not a
schema.

## Purpose

A new guard should cost a few rules, not a new file of matching code. Most
guards ask the same three questions in their own words: does this command run
program P with these options, does this call write to these paths, does this
text carry this pattern. Each question is answered once, by an engine, and a
guard becomes a named set of rules for it. Code stays for what rules cannot
say: state that spans calls, and lookups where one answer picks the next
question.

## Four engines

| Engine | One rule says |
|---|---|
| Command rules | program + its options + a condition → deny, or ask once |
| Write targets | the paths a call writes match a list |
| Text rules | a pattern or term appears in text the call carries |
| Code guards | anything else, through Need and Act as today |

Which guard goes where is in #198. A guard may use more than one engine:
recursive-delete is a command rule that hands its targets to write targets.

Every engine is pure: it plans in step 2, the facts and paths it needs, and
judges in step 4, guard. Its rules are data, read in gather like any other
fact. A rule runs no code and names no program to run.
Each rule that matches is one finding; verdict combines findings as it does
today. A rule only tightens: its action is `deny` or `ask-once`, never allow, so
a repo's rule set adds to what languette judges and takes nothing from it.

A guard keeps its name, its settings and its feature file. Moving it onto an
engine changes how it is written, never what it decides: its feature suite
passes unchanged.

## Command rules

ask-first's match format is the seed. A rule names a command word and a run of
its non-option words, and the scanner already sees through wrappers, chains,
`sh -c` and launchers:

```json
{"cmd": "npm", "args": ["run", "e2e"]}
```

The engine adds four things to it.

- **Options**: a flag present or absent, by long name, short name inside a
  cluster (`-ir` holds `r`) or prefix (`--har` is `--hard`). A prefix the
  program would call ambiguous matches every option it could be, so a deny
  rule still denies and an ask rule still asks.
- **A program description**: which options take a value, so the value is
  never read as a subcommand, and where the subcommand sits. git's comes from
  #197's finder; infra's `VALUED` table is the same thing for six programs.
- **A condition**: a closed list of tests on the matched words, such as a
  unit in the protected_services setting. A test that needs a fact names it,
  and plan turns it into a Need.
- **An action**: `deny`, or `ask-once`, ask-first's approval spent once per run.

One populated rule, `crontab -r` as guard-scheduled-jobs would write it:

```json
{"id": "crontab-wipe", "guard": "guard-scheduled-jobs",
 "match": {"cmd": "crontab", "flags": ["r"]},
 "action": "deny",
 "why": "it deletes the whole crontab with no undo"}
```

deny-always is then ask-first with the action set to deny, and its list is the
repo's. guard-sudo is one rule whose `cmd` is a list: `sudo`, `su`, `doas`
and `pkexec`.

## Facts a condition may name

A condition's fact is one of a closed list, each a Need kind and a pure
shaping of its answer: the repo a cwd's origin names, whether a path exists.
The list begins with what the moved guards ask today and grows when a rule
needs a fact, not before. A fact with a shape of its own, such as a PR's
threads or who wrote a comment, is shaped by one code guard today and stays
there until a second guard asks for it; then it earns a name here.

## Write targets

recursive-delete, permissions and worktrees each work out which paths a call
writes, then resolve them against the payload's cwd and through the
filesystem. That step is done once, for every guard: the engine lists the
paths to resolve, gather resolves them, and a call's targets are a list of
resolved paths, or a reason one could not be resolved. A rule is a
list of path patterns and an action. A target that cannot be resolved fails
closed, as both guards do today.

Command rules say which words are targets (`rm -r <targets>`); file tools name
theirs in `tool_input`. guard-protected-paths is the first guard built on this
step alone.

## Text rules

secrets, private-terms and bypass-labels each find the text a call carries,
then test it. The finding is done once: literal flag values, heredoc bodies, a
body file's contents, an MCP tool's strings. A rule is a pattern or a term,
where it applies (any repo, or a public one), and an action.

`secret_rules` is already this shape: an id, a description, a regex. The
private-terms list and the bypass-labels list are terms. guard-databases' SQL
scan is the first new guard on this engine.

## Rule sets that do not load

A rule set that does not parse, or has another shape, denies every call its
guard would judge, naming the file and the fault. That is ask-first's and
guard-secrets' behaviour today: the guard cannot tell what it was meant to
cover. A test loads every rule set languette ships, so that deny never greets
an install.

## Path there

The steps from today's guards to the four engines, in order (#198). A step
that lands leaves this list; what it built is then described above.

1. Every guard reads the call through Document; none opens the payload
   itself for the command.
2. The command engine: one rule loader and one matcher, where ask-first,
   scheduled-jobs and protected-services each load and match in their own
   way today. Program descriptions hold every value-taking option table,
   infra's and the commit guard's beside git's. Those three guards move
   onto it.
3. deny-always and guard-sudo, written as rules alone: the measure of what
   a new guard costs on the engine.
4. The other command guards move, smallest first.
5. Write targets, then guard-protected-paths on it; recursive-delete,
   permissions and worktrees switch to it.
6. The text engine: `secret_rules`, private-terms' terms and bypass-labels,
   then guard-databases.

## Open

- Shipped rules as JSON beside the code, or as Python data in the guard.
- How wide a condition's closed list grows before a guard is better as code.
- #134's step 3 asks the same question for git and GitHub alone; this design
  is one answer to it, not a decision on it.
