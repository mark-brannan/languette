# Can a cheap, deterministic estimate say what a Bash command will cost?

Research for #136. No guard code is added. The timings below come from three
throwaway scripts run against languette's own `scan` and `Document` with the
repo's venv on 2026-10-24; they are not in the repo.

## Answer

Partly. From the parse alone, an estimate can sort a command into a few
bands (seconds, minutes, possibly hours or unbounded; one core or every core)
by naming the program, its flags and the scope of its paths. It cannot give a
number of seconds: the cost of `pytest` or `make` depends on the repo, the
cache and the machine, none of which are in the command. The one input that
turns a band into a number is the history of the same command on the same
machine, and that is a gather read of records the plugin itself wrote in act.

On cost: the parse is already paid by the guards. Reading 16 cost rules
against the parse the run already holds took a median 0.11 ms per command
(max 0.18 ms, 26 commands). The parse itself is 2.7 to 3.3 ms, nearly all
of it the `shfmt` process start (see "Measured").

## What the parse can see

The scanner already sees through wrappers (`timeout`, `sudo`, `nice`,
`xargs`), launchers (`npx`) and `sh -c`, so a rule in the command-rules
format of [guard-rules.md](../design/guard-rules.md) ("Command rules") is
enough to name the program. Checked: `timeout 30 pytest`, `sudo find /`,
`sh -c "du -sh /"`, `nice make -j8`, `echo a | xargs rg foo` and `npx jest`
each matched their inner program.

| Signal | Example | What it says | Band it supports |
|---|---|---|---|
| Program class | `find`, `du`, `rg`, `tar`, `rsync` | cost grows with the tree it walks | depends on scope, below |
| Test runners | `pytest`, `jest`, `cargo test`, `npm test`, `tox` | cost is the suite's; unknown without history | minutes, unknown |
| Builds | `make`, `cargo build`, `go build`, `docker build`, `bazel` | cost is the project's; cache decides most of it | minutes, unknown |
| Containers | `docker run`, `docker compose up` | runs whatever the image does; may not end | unbounded |
| Parallel flags | `-n auto`, `-j$(nproc)`, `-j` bare, `--parallel` | holds every core | all cores |
| Release flags | `--release`, `-O3`, `--no-cache` | slower than the default build | one band up |
| Path scope | `/`, `~`, `$HOME`, `~/*`, `..` | the walk covers a home or the disk | hours, possibly |
| Path scope | `.`, `src/`, a named file | the walk covers the project | seconds |
| Limits in the command | `-maxdepth 2`, `head -n`, `timeout 30` | an upper bound the command sets itself | caps the band |
| Long-lived by design | `sleep 600`, `watch`, `tail -f`, a dev server | wall time without CPU | wall only |
| Media and compression | `ffmpeg`, `xz -9`, `zstd -19` | CPU-heavy per byte of input | minutes, unknown size |
| Loops | `for f in **/*.py; do ...` | runs the body once per match | multiplies the body |

`$HOME` reaches the scan unexpanded, which is the useful case: a literal
`$HOME`, `~` or `/` is the scope signal, and no expansion is needed to see it.

## Gather: what it would read, and what it costs

A static band needs no gather at all. Each read below sharpens it; costs are
medians of ten runs on this machine (16 cores, load average about 8).

| Read | Sharpens | Cost | Within gather's rules |
|---|---|---|---|
| Records this plugin wrote: past wall time of the same command here | band to a number | 0.92 ms for a 2,000-row JSON file | yes, "records this plugin wrote in act" |
| Core count | "all cores" means how many | 0.007 ms | yes, its own environment |
| Load average | whether all cores are free now | 0.001 ms | yes |
| `stat` of a named path | the path exists, is a dir | 0.003 ms | yes, the filesystem |
| One `scandir` of the path's top | how wide `~/*` is (182 entries here) | 0.09 ms | yes |
| `git ls-files` count | size of the project a test or build covers | 3.2 ms (150 files) | yes, git |
| A full walk of the path | how many files `find ~` will see | as much as the command itself | no: it is the cost being estimated |

History is the read worth having. It needs a write first: act would note the
clock at the PreToolUse call and again after the call (act already runs at
that second moment for the issue door, #83), keyed by the call's id, and store
the elapsed time against the command's normalized form. Whether the
PostToolUse payload carries a duration of its own is unverified; the two clock
reads do not depend on it. CPU time is harder: a hook runs in its own process
and cannot read the command's CPU use without wrapping the command, which a
guard does not do.

## Prior art

| Tool | What it does | Lesson |
|---|---|---|
| [sandwatch](https://hackage.haskell.org/package/sandwatch) | records each command's directory, line and runtime as JSON; predicts a new run from the mean of past ones, matched on directory and the first two words | history keyed by directory and a short normal form is enough for a forecast |
| [Atuin](https://github.com/atuinsh/atuin) | stores every shell command's duration, exit code and directory in SQLite | the data a history estimate needs is cheap to keep |
| [slurmpast](https://pypi.org/project/slurmpast/0.2.0/) | sizes a Slurm time request from the 90th percentile of past runs, plus headroom | a percentile, not a mean: under-asking kills the run |
| Slurm runtime prediction ([Tanash et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC8974354), [LANL](https://lanl.gov/org/ddste/aldsc/hpc/_assets/docs/abstracts/Whitton_abstract.pdf)) | models trained on accounting history beat the limit users write by hand | the user's own estimate is the weak baseline; history wins |
| [Ninja measure.py](https://fuchsia.googlesource.com/third_party/ninja/+/v1.8.0/misc/measure.py) | runs a command several times, reports the fastest | measuring is the only exact estimate, and it costs the run |
| [Bazel critical path](https://bazel.virtuslab.com/book/5~4~2/) | the action graph is known before a build, durations only from a profile of a past run | even a build tool with the whole plan needs history for time |
| [pytest-timeout](https://lincc-ppt.readthedocs.io/en/latest/practices/pytest_timeout.html) | fails a test past a set time; `--durations` lists the slowest | a suite reports its own cost only after it runs |
| [GNU timeout](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html), [setrlimit `RLIMIT_CPU`](https://man7.org/linux/man-pages/man2/setrlimit.2.html) (`ulimit -t`) | cap wall time or CPU seconds on one process | a cap, not an estimate; it acts after the cost is spent |
| [systemd-run](https://www.mankier.com/1/systemd-run) with [`RuntimeMaxSec=`](https://www.freedesktop.org/software/systemd/man/257/systemd.scope.html), `CPUQuota=` | runs a command in a scope with a wall limit and a CPU share | caps cores as well as time; the machine is protected even when the estimate is wrong |
| Claude Code's Bash tool ([reports](https://github.com/anthropics/claude-code/issues/5615)) | a per-call timeout, two minutes by default and ten at most per third-party docs; long commands may move to the background | the agent's own limit bounds a foreground call but not a backgrounded one |

No tool found estimates a shell command's cost from its text alone. Every
working estimate in the list is history or measurement; static reading is
used only to pick the key the history is filed under.

## What it misses

- **Repo-sized work.** `pytest -q` is 2 seconds in one repo and 40 minutes in
  the next. Without history, every test runner and build is "unknown".
- **Indirection.** `./scripts/e2e.sh`, `make check`, `npm run ci` name a
  script, not its cost. The parse cannot read the script's contents (a gather
  read of the file could, at the price of parsing another program).
- **Caches.** A warm `cargo build` or `docker build` takes seconds; a cold one,
  minutes. Nothing in the command says which.
- **Data size.** `ffmpeg -i in.mov` or `tar czf ~/projects` cost what the input
  weighs; a `stat` gives one file's size, not a tree's.
- **Variables and substitutions.** `find "$DIR"` or `rg foo $(cat dirs)` has no
  scope until it runs.
- **Pipes on stdin.** `git log | grep fix` matched the `grep` rule; a rule
  must ask whether a walker has a path at all, or a pipe's reader is called
  costly.
- **Machine state.** Load, a disk being slow, a network call; history keyed
  only by command averages them away.
- **CPU time.** A hook can read the clock around a call, not the command's CPU
  seconds. A wall-time history with a parallel-flag signal stands in for it.

## Measured

Method: three scripts imported `languette.scan` and `languette.document` from
this checkout, with the repo's `.venv/bin/python`, `shfmt` 3.12.0
on the path, 16 cores, load average 8.2 to 8.8. For each of 26 sample
commands (the table above's examples, plus loops, heredocs, `gh`, `git` and
`python3 -c`), the parse caches were cleared and each step timed ten times
with `time.perf_counter`; the median is reported.

| Step | Median | Max | What it is |
|---|---|---|---|
| `scan.parse` (shfmt rung) | 2.7 to 3.3 ms across two runs | 4.1 ms | one `shfmt --to-json` process; paid today by every Bash call |
| `scan.Scan` (parse plus word map) | 2.7 to 3.3 ms | 3.9 ms | the same process, plus a pure walk of its tree |
| 16 rules via `scan.matches`, cold `Document` | 2.8 ms | 5.4 ms | one parse, two for `sh -c` |
| 16 rules via `scan.matches`, parse already held | 0.11 ms | 0.18 ms | the marginal cost of an estimate step |
| naive first-word table over `Scan.segments()` | 0.005 ms | 0.008 ms | no wrapper handling; shown as a floor |

The marginal cost of a static estimate is about a tenth of a millisecond; a
history lookup adds about a millisecond. Both sit far under the parse a call
already pays.

## Recommendation

A pure step the guards read, not a guard. Its inputs are the parse and, when
present, the plugin's own history of the command; it returns a band for wall
time and one for cores, plus where the band came from (rule, history, none).
A budget guard, ask-first, or a future rules engine then decides with it.
Rules live in the command-rules format, so one table serves both the estimate
and ask-first's list; ask-first's `cost` field is prose today and would gain
a band beside it. Without history the band for test runners and builds is
"unknown", and a guard should treat unknown as unknown, not as cheap.
