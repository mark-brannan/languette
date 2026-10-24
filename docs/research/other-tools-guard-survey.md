# Guards other agent-safety tools ship that languette lacks

A survey, not a proposal. No guard is approved or filed. Every row is a
candidate that must still pass `docs/decisions.md`, "New guards"
(2026-10-09): it enters through an issue with incident, root cause, hazard,
concept and name; the hazard is one that could ruin a day, not waste an
hour; root cause comes before the guard.

## Sources

- `Dicklesworthstone/destructive_command_guard` (dcg), README pack list,
  fetched 2026-10-24. Pack names and one-line scopes are taken from it;
  rule bodies were not read.
- `kenryu42/claude-code-safety-net`, README, fetched 2026-10-24. It cites
  no incident.
- languette: `languette/guards/` and `features/` on `main` at `46e147e`.
  "Planned" means a `@planned` row in a feature file: a verdict no guard
  gives yet.
- Not read: Cursor and Kiro rule files, Claude Code hook collections, and
  sandbox wrappers. The last are a different concept (confine the process,
  not judge the command) and appear only in the last section.

The sources publish rules, not incidents. The "hazard" column is therefore
this survey's reading of what the rule guards against, marked as such; no
tool above was found citing a specific incident for these rules.

## Already covered

| Other tool's rule | languette |
|---|---|
| dcg `core.filesystem`, `windows.filesystem` recursive delete (Unix side) | `guard-recursive-delete` |
| dcg `core.git`, safety-net reset/force push | `guard-git-work-loss` |
| dcg `system.disk` | `guard-disks` |
| dcg `system.permissions` | `guard-permissions` |
| dcg `system.services` | `guard-protected-services`, `guard-host-availability` |
| safety-net `curl \| bash` | `guard-pipe-to-shell` |
| dcg `infrastructure.terraform`, `pulumi`; `cloud.aws`/`gcp`/`azure` deletes; `kubernetes.kubectl`, `helm` | `guard-infra` (per-run approval) |
| dcg `platform.github` deletes, visibility | `guard-github-issues`, `guard-bypass-*`; repo deletes are planned rows in `infrastructure.feature` |
| dcg `containers.*` prune and `down -v` | deliberately allowed on the user's dev host (`files.feature`) |

## Not covered, and where it stands

| Guard (dcg pack or tool) | Blocks | Hazard (survey's reading) | languette today |
|---|---|---|---|
| Reading secret files (safety-net; dcg `secret_disclosure`, opt-in) | agent reads `~/.ssh`, `.env`, `~/.aws`, CLI credentials, or prints secret values | the content lands in the transcript and any later post; a leak is not undoable | values printed from a secret store: `@planned` in `secrets.feature`; files read from disk: no row. `guard-secrets` catches a credential typed into a command, not one read from disk. `guard-protected-paths` is an unwired stub, which would be the home |
| Database packs (dcg `database.*`) | DROP, TRUNCATE, unfiltered DELETE, `FLUSHALL`, `dropDatabase`, Supabase reset, Snowflake/BigQuery/Databricks drops | production data gone, backups may not exist | `guard-databases` is an unwired stub; rows are `@planned` in `data.feature`; scan feasibility in `sql-ddl-scan.md` |
| Cloud storage packs (dcg `storage.s3`/`gcs`/`minio`/`azure_blob`) | bucket removal, recursive delete, destructive sync | objects deleted with no trash | `aws s3 rm --recursive` and `rb --force` are in `guard-infra`; `gsutil rsync -d`, minio, azure blob are `@planned` |
| `rsync --delete` (dcg `remote.rsync`) | destination files absent from source are removed | a swapped argument order empties a tree | `@planned` in `files.feature`, with `--remove-source-files` |
| Messaging (dcg `messaging.kafka`/`nats`/`rabbitmq`/`sqs_sns`) | topic, stream, queue deletion, purges, offset resets | messages lost, consumers replay or skip | `@planned` in `data.feature` |
| DNS (dcg `dns.*`) | record and zone deletion | outage plus slow propagation back | `@planned` in `infrastructure.feature` |
| Secret managers (dcg `secrets.*`: AWS Secrets Manager, Vault, 1Password, Doppler, Infisical) | secret, vault, engine and lease deletion | credentials lost or revoked | `@planned` in `secrets.feature` |
| CI/CD (dcg `cicd.*`) | variables, secrets, runners, build history | pipelines break; history gone | `@planned` for build history (`data.feature`) and Actions secrets (`secrets.feature`) |
| Payments (dcg `payment.*`) | customer deletion, subscription cancel, key rotation | money and customer records | `@planned` in `money.feature` |
| Edge, API gateway, load balancer, feature flags, monitoring, email (dcg) | service, route, flag, monitor, template deletion | an outage or silent alerting loss | mostly `@planned` in `infrastructure.feature` and `data.feature` |
| Windows (dcg `windows.*`) | shadow copy deletion, `diskpart`, `Format-Volume`, registry, `wsl --unregister` | machine unrecoverable | `@planned` in `files.feature` |
| Wrapper and custom rulebooks (safety-net) | the same, through `bash -c`, `python -c` | rules bypassed by nesting | not a guard: `scan` already follows `sh -c`; a user-supplied rulebook is `ask-first`'s list |
| Kubernetes drain, namespace and Kustomize apply (dcg) | node drain, unreviewed apply | workload eviction | `kubectl delete` in `guard-infra`; `drain` `@planned` in `stop.feature`; `apply --prune` `@planned` in `infrastructure.feature` |

## Reading

- Most gaps are already carried as `@planned` rows. They are a queue, not a
  discovery; the survey adds no new category there.
- One item looks new: reading secret files from disk. It has the strongest
  hazard (irreversible disclosure) and an obvious concept:
  a setting of the stubbed `guard-protected-paths`, not a new guard.
- Per-service packs (payments, email, monitoring, messaging) show the shape
  dcg chose: many opt-in packs, one regex each. Languette's decisions lean
  toward a rules engine with few deep special cases, so these would be rows
  in an existing guard's table, not guards.

## Sandbox wrappers

A sandbox (filesystem and network confinement of the process) answers a
different question from a command guard: it limits what any command can do
instead of judging this one. It would cover disk, permission and
exfiltration hazards with no list to maintain, at the cost of no per-command
reason to show the agent. Not surveyed beyond this note; nothing here
proposes one.
