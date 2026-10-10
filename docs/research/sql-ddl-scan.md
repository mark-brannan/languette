# Can a SQL-level scan flag DROP, TRUNCATE and other DDL in an agent's command?

Research for #158. No guard code is added. The numbers below come from a
throwaway prototype (about 100 lines, standard library plus languette's own
`Document` and `Scan`), run on 2026-10-10. It is not in the repo.

## Answer

Yes, for the common carriers, and cheaply. A scan that (1) finds a database
client in a command segment, (2) takes the quoted strings and heredoc bodies
the shell scan already hands over, and (3) masks comments and string literals
before reading each statement's head word, flagged every destructive
statement in the planned rows of `features/data.feature` that is SQL text
(see "Measured"). On a corpus of 119,438 distinct agent commands it flagged
nothing, and it cost about 5 ms per candidate command.

What it cannot see is text that is not on the command line: a `.sql` file, a
shell variable, a script an ORM runs. Those need gather (I/O) or are out of
reach. The recommendation is a setting inside the planned `guard-databases`
guard, answered with `asks`, not a separate guard (see "Recommendation").

## Carriers

"Handed over" means the existing shell scan (`Document.texts()`,
`Document.heredoc_bodies()`) already yields the SQL as one string, with
quotes and heredoc syntax removed. "Prototype" is what the prototype flagged.

| Carrier | Example | Handed over by shell scan | Prototype flagged |
|---|---|---|---|
| `-c` / `-e` / `-q` argument | `psql -c "DROP TABLE users"` | yes, one quoted word | yes |
| positional (sqlite3, bq, snow) | `sqlite3 a.db "DROP TABLE t"` | yes | yes |
| heredoc | `psql shop <<'EOF' ... EOF` | yes (`heredoc_bodies`) | yes, comment-first too |
| pipe from echo or printf | `echo "TRUNCATE t;" \| psql` | yes, in the echo segment | yes |
| wrapped in ssh, docker exec, kubectl exec, sudo | `kubectl exec pg-0 -- psql -c "..."` | yes | yes |
| split by the shell | `-c "DR""OP TABLE users"` | yes, joined | yes |
| MySQL executable comment | `-e "/*!50000 DROP TABLE users */"` | yes | yes (a naive comment strip would miss it) |
| attached or `=` form | `-c"DROP ..."`, `--command="DROP ..."` | not checked | missed; a prototype gap, not shown to be a scan limit |
| here-string | `psql <<< 'DROP ...'` | not checked | missed; same |
| `$$`-quoted `DO` block | `DO $$ BEGIN EXECUTE 'DROP ...'; END $$` | yes, with `\$` escapes | missed; the escapes are the likely cause (unverified) |
| file named on the line | `psql -f drop_users.sql`, `mysql < wipe.sql` | no, only the name | no; needs a gather step to read the file |
| shell variable | `Q="DROP TABLE x"; psql -c "$Q"` | no, the text is never expanded | no |
| written, then run | `echo 'DROP ...' > x.sql && psql -f x.sql` | the echo segment is | yes, but only while a client is on the same line |
| language driver | `python3 -c "cur.execute('DROP ...')"` | yes, as a quoted string | no: no client word; reading arbitrary code is another problem |
| ORM or migration tool | `rails db:drop`, `prisma migrate reset`, `manage.py flush` | the argv only | no SQL exists to read; an argv rule, not a SQL scan |
| dynamic SQL | `EXECUTE 'DR' \|\| 'OP TABLE x'` | yes | no, and in principle cannot |
| non-SQL client verbs | `dropdb`, `mysqladmin drop`, `bq rm -r -f -d`, `bq load --replace` | the argv | no: argv rules (the existing `@planned` rows) |

The shell scan hands over the large majority of what an agent types. The
gaps that remain are the ones where the SQL is not in the command at all.

## Statements worth reading

Read the first keyword of each `;`-separated statement, after masking:

| Class | Rule | Note |
|---|---|---|
| DROP | any `DROP` | tables, schemas, databases, roles, indexes alike |
| TRUNCATE | any | |
| ALTER ... DROP | `ALTER` with a `DROP` in the statement | column drops; other ALTERs a lower tier |
| DELETE / UPDATE with no WHERE | head word, and no `WHERE` anywhere in the statement | `WHERE true` and `WHERE 1=1` pass; a subquery's WHERE hides a missing outer one. Both are real misses |
| GRANT / REVOKE | any | |
| MERGE ... DELETE, RESET MASTER | head word plus a keyword | BigQuery and MySQL rows in `data.feature` |
| LOAD DATA OVERWRITE | head words | BigQuery; not in the prototype, a one-line addition |

Masking is what keeps the false-positive rate down: remove `--` and `/* */`
comments, string literals, quoted identifiers and `$tag$` bodies (read those
again as SQL, since `DO $$ ... $$` runs them), keeping `/*! ... */` contents,
which MySQL runs. A `SELECT 'DROP TABLE users'`, a trailing `-- DROP` comment
and a `/* DROP */` comment are correctly silent.

## Dialects, in order

1. PostgreSQL (`psql`): the dollar quoting and `\` meta-commands are the only
   syntax that changes masking.
2. MySQL and MariaDB (`mysql`, `mariadb`): executable comments, backtick
   identifiers, `RESET MASTER`.
3. SQLite (`sqlite3`): `.`-commands (`.read file`) are carriers of their own.
4. Cloud warehouse CLIs (`bq query`, `snow sql -q`, `aws athena
   start-query-execution --query-string`): same statement heads, different
   carrier flag. The prototype handles the first two; `aws athena` needs the
   client list widened (a wrapper word such as `aws` is in the prototype's
   list and was flagged).

Statement heads are close to common across all of them, so one head-word
reader covers the family; the dialects differ in quoting, not in what DROP
and TRUNCATE mean.

## Options

| Option | Cost | Reads | Misses |
|---|---|---|---|
| Stdlib mask-and-split (prototyped) | none; about 5 ms per candidate | heads of statements, in any dialect's quoting if masked per dialect | dynamic SQL, `WHERE true`, subquery WHERE, anything not on the line |
| `sqlite3` module as a parser (`complete_statement`, authorizer) | none | SQLite only, and the authorizer needs the schema to prepare | every other dialect; not recommended |
| Optional dependency, e.g. `sqlglot` (pure Python, many dialects, real parse trees) | a dependency the repo does not carry; unmeasured here (not installed, nothing fetched) | `WHERE true` and subqueries correctly | files, variables and dynamic SQL, the same as the above; parse failures on dialect corners need a fallback anyway |

The deciding point: the misses that matter are not parse misses. They are
text that never reaches the command line. A real parser improves only the
`WHERE` rows. The standard library option takes the same shape as the rest
of languette (no dependency, and only gather and act touch the world).

## Measured

Corpus: every distinct Bash command in the maintainer's local Claude Code
transcripts, 6,789 sessions, 127,000 calls, 119,438 distinct commands. This is
not a repo file; it is a biased sample (mostly work on languette and
adjacent repos), so it measures false positives well and says little about
how often a real database command is typed.

| Reader | Hits | Real destructive database statements |
|---|---|---|
| Regex on the raw command text (DROP, TRUNCATE, DELETE FROM, ALTER TABLE, GRANT, REVOKE) | 124 | 0 |
| Carrier-aware scan (client in a segment, then masked SQL) | 0 | 0 |

- The 124 raw hits were checked by command shape, not one by one: 82 are
  heredocs (code or docs being written), 22 are `git` or `gh` text (commit
  bodies, PR and issue comments), the rest are `cd`-led scripts and a
  `grep`. None ran a database client with a destructive statement.
- Only 23 of the 214 commands that named a client or matched the regex had a
  client word in a command position; the carrier-aware scan flagged none.
- So the raw-text reader would be wrong 124 times in 119,438 (0.10%) and the
  carrier-aware scan 0 times. With zero hits the rate is bounded, not
  pinned: the 95% upper bound is about 3 in 119,438 (rule of three).
- There are no true positives in the corpus, so recall is not measured from
  it. The substitute is `features/data.feature`: 32 database rows (7 allowed
  reads and prose, 25 destructive), the prototype got 27 right, silent on all
  the allowed rows. The 5 misses: `dropdb` and `mysqladmin drop` (argv, not
  SQL), `DELETE ... WHERE true` (the tautology), `LOAD DATA OVERWRITE` and
  `bq query --replace` (a flag). None is a parse failure.
- Cost: the shell ladder ran 214 candidates in 1.2 s (5.4 ms each, including
  `shfmt`), after a regex prefilter that a guard would do with its plan step.

## Recommendation

Worth it, modestly, as a stdlib scan inside `guard-databases`, verdict
`asks`, never `deny`.

- Why: the false-positive rate on the available corpus is 0 once the client
  must be present; the hazard is as in the README's lede (erased rows are not
  a waste of an hour); and `data.feature` already carries 25 planned rows
  this scan would turn from `@planned` to green, apart from the argv rows.
- Why not more: no real database command appears in the corpus, so the need
  rests on the hazard, not on a measured miss. #125's rule (an incident
  first) is not met by this evidence; it is the maintainer's call whether a
  prevented hazard counts.
- Shape: parse, plan (does a segment name a client or wrapper?), gather
  (only for `-f`, `<` and `.read`, reading the named file under a size cap),
  guard (the masked statement-head reader, pure), verdict `asks`.
- Keep two readers: the SQL scan for text, and plain argv rules for
  `dropdb`, `mysqladmin drop`, `bq rm`, ORM `db:drop`-style verbs. They are
  different guards' work in `data.feature`'s `@planned` rows.
- Do not add a parser dependency for this guard. Revisit only if `WHERE`
  tautologies prove to matter.

## Open for the maintainer

- Name: the issue says `guard-database`; the stub in the repo and the
  approved-names ruling say `guard-databases`. Left as the stub has it.
- Whether this hazard clears the "New guards" bar without an incident.
- Verdict strength for `GRANT`/`REVOKE` and plain `ALTER` (a lower tier or
  silent).

## Follow-up

Candidate issue, not filed:

> **guard-databases: read DROP, TRUNCATE and DELETE/UPDATE without WHERE in a client's command.**
> Incident: none yet (research #158 found no real database command in 119k
> agent commands). Hazard: erased rows. Concept: a setting of
> `guard-databases`; stdlib mask-and-split reader over quoted words and
> heredoc bodies of a segment naming psql, mysql, sqlite3, bq or snow; gather
> reads `-f`/`<` files; verdict `asks`. Done when the `@planned` SQL rows in
> `features/data.feature` pass; the argv rows stay separate.
