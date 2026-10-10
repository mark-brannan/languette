# Ansible harms: which are defined well enough for a guard

Research for mark-brannan/languette#163. No guard code. Measured on
ansible-core 2.21.3 (installed on the research machine), run against
`localhost` with `ansible_connection=local` and files under `/tmp`. Statements
marked *(guess)* were not measured.

## Answer in one paragraph

The command line decides one thing well: whether a run is a preview or a real
run. Everything about *what* a real run does lives in the playbook, the
inventory, `-e` variables and the roles it pulls in, and a playbook read does
not recover it (the same file deletes or creates depending on a variable).
Recommend two rules in `guard-infra`: ask before a real `ansible-playbook`
run, and ask before an ad-hoc `ansible` run whose module is not on a short
read-only list. Do not read playbooks. `--check` is a cheap pass signal but
not a guarantee, and the rule should say so.

## 1. What the command line alone decides

Ansible has no `apply`/`plan` split. Every `ansible-playbook` run without a
preview flag is a real run, and there is no interactive approval to bypass
(unlike `terraform apply`), so "unreviewed" cannot be read off a flag the
way `-auto-approve` is.

| Command | Measured effect | Guard can say |
|---|---|---|
| `ansible-playbook -i inv p.yml` | runs every task | real run |
| `... --check` / `-C` | `shell`, `command`, `raw` tasks skipped (3 of 4 tasks in the test play); `file state=absent` reported `ok`, nothing removed | preview |
| `... --list-tasks`, `--list-hosts`, `--list-tags`, `--syntax-check` | documented as not executing; `--list-tasks` printed the task list only | preview |
| `... --diff` / `-D` alone | not tested; documented as display only *(guess: still a real run)* | real run |
| `ansible all -m shell -a '...'` | real run; with `--check`: `SKIPPED` | real run unless `--check` |
| `ansible all -a '...'` (no `-m`) | default module is `command`; with `--check`: `SKIPPED` | real run unless `--check` |
| `ansible all -m ping` / `setup` / `stat` | reads *(guess: not run)* | read, by module name |
| `ansible all -m file -a 'state=absent'` | deletes; with `--check`: `SUCCESS`, nothing removed | by argument text |

Examples from the repo's own corpus (`features/infrastructure.feature`):

- passes today, and should: `ansible-playbook -i inventory/prod site.yml --check`
- planned `asks`: `ansible-playbook -i inventory/prod site.yml`,
  `ansible-playbook -b -i hosts.ini upgrade.yml`
- planned `asks`: `ansible all -i inventory/prod -m ansible.builtin.shell -a 'terraform {{ op }} -auto-approve' -e 'op=destroy'`

`features/guard-infra.feature` currently pins `ansible-playbook site.yml` as
"ansible is not covered".

### What the parser needs

Same shape as `_kubectl`: command word, then positionals with valued options
skipped. Valued options in `ansible-playbook --help`: `-i -e -l -t -f -u -c
-T -M` and the long forms `--inventory --extra-vars --limit --tags --skip-tags
--start-at-task --forks --user --connection --timeout --private-key
--vault-id --vault-password-file --become-method --become-user
--become-password-file --connection-password-file --ssh-common-args
--ssh-extra-args --sftp-extra-args --scp-extra-args --module-path`; ad-hoc
`ansible` adds `-m -a`. `-b`, `-K`, `-k`, `-v`, `-J` are flags. Roughly 30
lines plus a table row *(guess)*, like `kubectl`.

Module names for the ad-hoc allowlist have two spellings (`shell`,
`ansible.builtin.shell`), and `ansible-doc -l` lists 8794 plugins on this
machine once collections are counted, so a *deny*list of dangerous modules
cannot be enumerated. An *allow*list of read modules can: `ping`, `setup`,
`stat`, `debug`, `slurp`, `find`, `gather_facts`, `package_facts`,
`service_facts`, each with and without `ansible.builtin.`. (The list is a
guess at what counts as read-only; the maintainer owns it.)

### Wrapped commands

`-m shell -a 'terraform destroy'` carries a second command inside an
argument. guard-infra already reads nested shell text (`sh -c`, `echo | sh`);
pointing the same reader at the `-a` text of `shell`/`command` modules would
catch the literal case cheaply. It misses the planned row's actual form,
because the command there is `terraform {{ op }}` with `op` set by `-e`. That
row is caught only because it has no `--check`.

## 2. What needs the playbook read

Measured, a one-task playbook:

```yaml
- ansible.builtin.file: {path: /tmp/x, state: "{{ s | default('touch') }}"}
```

| Run | Result |
|---|---|
| `ansible-playbook -i inv r.yml` | `changed=1`, file created |
| `ansible-playbook -i inv r.yml -e s=absent` | `changed=1`, file removed |

The harm is chosen by a variable on the command line, so reading the file
(or the module name in it) does not decide it. Other ways the playbook hides
it, from Ansible's design *(guess: not each measured)*: `import_tasks` and
`include_role` pull in files the playbook text does not contain; roles live
in directories found through `ansible.cfg` and `roles_path`; inventory and
`group_vars` supply variables; dynamic inventory plugins run code.

What a playbook read would add: literal `state: absent`, `shell:`/`command:`
modules, `become: true`, `hosts: all`. Cost:

- **YAML.** The project is standard library only (`dependencies = []` in
  `pyproject.toml`, README line 47). Python has no YAML parser. PyYAML 6.0.3
  happens to be on this machine, but it is not a dependency and the guard
  runs in whatever interpreter the hook finds. A hand-written subset parser
  must handle anchors, flow and block styles, multi-document files and
  multi-line scalars; an incomplete one fails silently toward "looks safe".
- **Second parser.** `docs/design/guard-pipeline.md` has one parse, one
  document, and only gather and act do I/O. Reading the playbook is I/O at
  guard time, against that rule, and the file the agent is about to write
  may not exist yet.
- **Value.** Literal matches are the easy cases; the variable case above is
  the hard one and stays out of reach. A guard that reads the file and finds
  nothing would give a false pass.

Verdict: not well enough defined. Do not build it.

## 3. `--check` and `--diff`

Measured:

- `--check` skips `shell`, `command` and `raw` tasks entirely (3 skipped, 1
  `ok`, `changed=0`), so a preview of those tasks shows nothing.
- `--check` is **not** a guarantee: a task with `check_mode: false` runs for
  real under `--check`. Test: `shell: echo ran > /tmp/lang-ans-q` with
  `check_mode: false`, run with `--check`: `changed=1`, and the file existed
  afterwards. Playbook authors use this for read tasks that feed later ones,
  and nothing on the command line shows it.
- Modules without check-mode support are skipped *(guess, from Ansible's
  documentation)*, so a clean check run can hide whole tasks.
- No environment variable or `ansible.cfg` key was found that turns check on
  by default *(guess: not exhaustively searched)*; so absence on the command
  line is real absence.
- `--diff` alone previews nothing *(guess)*.

Is requiring `--check` a useful, cheap rule? Useful as the **pass signal**,
the way `--dry-run=server` is for kubectl: cheap (one flag, `-C` included),
and `features/infrastructure.feature` already expects it to pass. Not useful
as a **hard requirement**: denying every run without `--check` blocks
legitimate applies with no way through. Ask, using guard-infra's existing
one-click approval. The deny text should state the limits above, so the agent
does not report a clean `--check` as proof.

`--limit` is not a pass signal *(guess)*: `--limit prod-db` is narrower, not
safer. The planned row's note "no --limit, no --check" suggests otherwise;
that is the maintainer's call.

## 4. Recommendation and placement

Put it in `guard-infra` as a setting, not a new guard: `docs/decisions.md`
("New guards") says a concept is a setting of an existing guard or a new one,
and Ansible's hazard is the one guard-infra's docstring names (a command that
changes real infrastructure). It fits the module's shape (tool word, first
positionals, flags, rule table, same approval).

| Rule id | Fires on | Passes |
|---|---|---|
| `ansible-playbook-run` | `ansible-playbook` (found through wrappers and launchers as other tools are) | `--check`/`-C`, `--list-*`, `--syntax-check`, `--help` |
| `ansible-adhoc-run` | `ansible` with a module not on the read list, or no `-m` | `--check`/`-C`, read modules, `--help` |

Next to the siblings: Terraform has `destroy` and `-auto-approve` because
those are *words on the line*. Ansible has no such word; the nearest honest
analogue is "a real run", which is weaker. Same trade as `kubectl-delete`:
the approval is the rule's, so a click on "Run ansible-playbook" pays for the
next real run of any playbook. The deny text should therefore ask for the
playbook, inventory, `--limit` and `-e` values in the question (guard-infra's
text already asks for the exact command). Expect more clicks than Terraform:
every real run asks.

Related tools *(guess, not measured)*: `ansible-pull` runs a playbook from a
repository and belongs with `ansible-playbook`; `ansible-vault decrypt|view`
touches secrets (secrets family, not infra); `ansible-galaxy`, `ansible-doc`,
`ansible-inventory`, `ansible-config` do not change hosts.

Not recommended: playbook parsing, a module denylist, `--check` as a deny.

## Follow-up

Ready to become an issue under the "New guards" ruling (fields: incident,
root cause, hazard, concept, name):

- Concept: two rules in `guard-infra`, `ansible-playbook-run` and
  `ansible-adhoc-run`, per section 4; the planned scenarios in
  `features/infrastructure.feature` become the tests, and the `ansible` row
  in `features/guard-infra.feature` changes from "not covered".
- Open for the maintainer: whether every real run asking is acceptable noise;
  whether `--limit` counts as a pass; the read-module allowlist; whether
  `ansible-pull` is in scope.
- No incident is named in #163; the issue needs one before it earns `ready`.
