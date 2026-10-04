#!/bin/sh
# PreToolUse Bash: before a `git commit`, runs the prose-budget engine
# (mark-brannan/claude, bin/prose-budget) with --staged and denies the
# commit on findings, so documentation bloat is caught at the moment it
# is written rather than in CI. The engine is not bundled here: it is
# found through $PROSE_BUDGET, else `prose-budget` on PATH. No engine, no
# config in the target repo, or an engine crash is a no-op -- this guard
# can only ever narrow what already passes through it.
#
# Detection is structural via lib-shell-words.awk (read its header): a
# commit mentioned in a commit message, a comment, or a heredoc body is
# not a commit. `cd DIR && git commit` and `git -C DIR commit` run the
# engine in DIR, denying rather than skipping the check if DIR cannot be
# resolved (an unexpanded `~`, a literal `$VAR`). `git merge --continue`
# counts too, since resolving a conflict finishes the merge; the engine's
# own --staged mode already skips every check mid-merge.
#
# Each `cd` and `-C` is folded onto the one before it, so `cd a && cd b`
# and `git -C a -C b` both land in a/b.
#
# `--staged` only sees what is already in the index at hook time, so
# `git commit -a`/`--all`/`-am`, a pathspec commit (`git commit path/x`,
# `git commit -m x -- path/x`), and a `git add path/x && git commit` in one
# call are also run through `prose-budget --file` against the named paths
# -- the working-tree content those commands actually commit, not the
# index. `-a`/`--all` and `add -u`/`--update` widen that to every path
# `diff --name-only` reports changed; an `add` that stages by pattern
# (`-A`, `--all`, `.`, `*`, `:`) rather than by name also widens it to
# `ls-files --others --exclude-standard`, since that can commit a
# brand-new file no diff would show. Both run through whichever of
# `git`/`yadm` the commit named (looked up fresh on PATH -- the commit's own
# wrapper word is as attacker-controlled as the rest of the command, so this
# guard reads from it only which CLI to use, never runs the word itself),
# and both stage repo-wide -- `-a`/`add .` is not scoped to `$dir` -- so
# each path they report is anchored to the repo root as an absolute path
# rather than read against `$dir`, which would misplace anything outside
# it. A pathspec word this guard cannot resolve (an unexpanded `~`, a
# literal `$VAR`, a quoted path with spaces) denies rather than skips, same
# as an unresolvable `cd`/`-C`; so does a `diff`/`ls-files` that itself
# fails. A path starting with `-` is prefixed `./` before it reaches the
# engine, so it can't be read as one of the engine's own options. A
# pathspec that is a directory on disk also denies -- `--file` would just
# silently drop it, leaving everything under it unchecked. Residual gap:
# an `add`/`commit` pair that `cd`s between the two resolves both against
# the commit's own directory, which is wrong if they really do run in
# different places.
#
# Exit 1 is a finding and denies. Exit 2 is a bad budgets config (or an
# engine too old for --staged/--file) and denies too, saying so: the repo
# asked for budgets and they cannot be checked. Any other exit is a no-op.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"
ENGINE=${PROSE_BUDGET:-$(command -v prose-budget 2>/dev/null)}

command -v jq >/dev/null 2>&1 || exit 0
command -v awk >/dev/null 2>&1 || exit 0
[ -r "$LIB" ] || exit 0
[ -n "$ENGINE" ] || exit 0

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

input=$(cat) || exit 0
[ "$(printf '%s' "$input" | jq -r '.tool_name // ""' 2>/dev/null)" = "Bash" ] || exit 0
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null) || exit 0
[ -n "$cmd" ] || exit 0
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""' 2>/dev/null)
case $cwd in /*) : ;; *) cwd=$PWD ;; esac
# Resolved against the commit's own cwd, before any `cd` below: a relative
# $PROSE_BUDGET (e.g. ./bin/prose-budget) means relative to the project, not
# to wherever this hook process happens to run from. A bare name (no `/`,
# e.g. PROSE_BUDGET=prose-budget) is a command, looked up on PATH like the
# unset-PROSE_BUDGET fallback above, not a path under the project.
case $ENGINE in /*) : ;; */*) ENGINE=$cwd/$ENGINE ;; *) ENGINE=$(command -v "$ENGINE" 2>/dev/null) ;; esac
[ -x "$ENGINE" ] || exit 0

# Prints "COMMIT<TAB>cd-dir<TAB>-C-dir<TAB>all-flag<TAB>bad-pathspec<TAB>paths
# <TAB>all-new<TAB>wrapper" for the first git/yadm commit found. paths is
# \037-joined: every pathspec word on an `add` before it, plus any trailing
# pathspec on the commit itself; a directory, glob, or other pattern among
# them widens all-flag/all-new (below) instead of being passed on as a
# literal, doomed-to-miss --file argument. all-flag is 1 when `-a`/`--all`/
# `-am` on commit, or `add -u`/`--update`, means every unstaged tracked
# change is in play, not just the named paths. all-new is 1 when an `add`
# staged by pattern rather than by name (`-A`, `--all`, `.`, `*`, `:`,
# an unrecognized flag) -- that can also pick up a brand new, still-
# untracked file, which a tracked-only diff cannot see. wrapper is the
# word that ran the commit (`git`, `yadm`, or a path to either) -- read
# only for *which* CLI it names, never executed itself, since it is as
# attacker-controlled as the rest of the command.
hit=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
BEGIN { SEP = sprintf("%c", 31) }
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  ntexts = texts_of(buf, texts, nested)
  for (x = 1; x <= ntexts; x++) {
    n = scan(texts[x], w, k, q)
    a0 = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a0 < i) segment(a0, i - 1, nested[x])
      a0 = i + 1
    }
  }
}
function join(base, step) { return (base == "" || step ~ /^\//) ? step : base "/" step }
function isbad(idx) { return k[idx] == "q" || SW_live[idx] }
function addpath(p) { PATHS[++PATHN] = p }
# A directory (trailing /), a magic (`:`-led) or glob pathspec names more
# than itself, so it widens the check rather than being added as a literal
# --file argument the engine would just fail to find.
function is_wide(p) { return p == "." || p == "*" || p == ":" || p ~ /[*?[]/ || p ~ /\/$/ || p ~ /^:/ }
# an `add` pathspec can introduce brand-new untracked files; a `commit`
# pathspec only ever narrows what is already tracked or staged, so it
# widens to ALLFLAG (every unstaged tracked change) but never ALLNEW.
function addwide_add(p) { if (is_wide(p)) { ALLFLAG = 1; ALLNEW = 1 } else addpath(p) }
function addwide_commit(p) { if (is_wide(p)) ALLFLAG = 1; else addpath(p) }
function collect_add(lo, hi,   i) {
  for (i = lo; i <= hi; i++) {
    if (w[i] == "--") continue
    if (w[i] ~ /^-/) {
      if (w[i] ~ /^--(a|al|all)$/ || (w[i] ~ /^-[A-Za-z]+$/ && w[i] ~ /A/)) { ALLFLAG = 1; ALLNEW = 1 }
      else if (w[i] ~ /^--(u|up|upd|upda|updat|update)$/ || (w[i] ~ /^-[A-Za-z]+$/ && w[i] ~ /u/)) ALLFLAG = 1
      # -n/-v (dry-run/verbose) are the only `add` flags that provably
      # change nothing about what gets staged. Everything else -- -f
      # (stages a gitignored file `ls-files --exclude-standard` would
      # miss), -p/-i (either can stage untracked content interactively),
      # or an option this guard does not recognize -- widens rather than
      # silently keeping the narrower, named-paths-only check.
      else if (w[i] ~ /^-[nv]+$/) { }
      else if (w[i] ~ /^--(dry-run|verbose)$/) { }
      else { ALLFLAG = 1; ALLNEW = 1 }
      continue
    }
    if (isbad(i)) { BAD = 1; continue }
    addwide_add(w[i])
  }
}
function commit_tail(lo, hi,   i) {
  i = lo
  while (i <= hi) {
    if (w[i] == "--") {
      for (i++; i <= hi; i++) { if (isbad(i)) BAD = 1; else addwide_commit(w[i]) }
      return
    }
    if (w[i] == "--all") { ALLFLAG = 1; i++; continue }
    if (w[i] ~ /^(-m|--message|-F|--file|-C|--reuse-message|-c|--reedit-message|--fixup|--squash|--author|--date|--template|--pathspec-from-file)$/) { i += 2; continue }
    if (w[i] ~ /^-[A-Za-z]+$/) {
      if (w[i] ~ /a/) ALLFLAG = 1
      i += (w[i] ~ /[mFcC]/) ? 2 : 1
      continue
    }
    if (w[i] ~ /^-/) { i++; continue }
    if (isbad(i)) { BAD = 1; i++; continue }
    addwide_commit(w[i]); i++
  }
}
function segment(lo, hi, nested,   g, i, j, dir, pj) {
  if (w[lo] == "cd" && k[lo + 1] == "w") CD = join(CD, w[lo + 1])
  g = cmd_index(w, k, lo, hi, "(^|/)(git|yadm)$", nested, "")
  if (!g) return
  BIN = w[g]
  i = g + 1; dir = ""
  while (i <= hi && w[i] ~ /^-/) {
    if (w[i] == "-C") { dir = join(dir, w[i + 1]); i++ }
    else if (w[i] ~ /^(-c|--git-dir|--work-tree|--namespace)$/) i++
    i++
  }
  if (i <= hi && w[i] == "add") { collect_add(i + 1, hi); return }
  if (i <= hi && w[i] == "commit") {
    commit_tail(i + 1, hi)
    pj = ""
    for (j = 1; j <= PATHN; j++) pj = pj (pj == "" ? "" : SEP) PATHS[j]
    print "COMMIT\t" CD "\t" dir "\t" (ALLFLAG ? 1 : 0) "\t" (BAD ? 1 : 0) "\t" pj "\t" (ALLNEW ? 1 : 0) "\t" BIN
    exit
  }
  if (i <= hi && w[i] == "merge") {
    for (j = i + 1; j <= hi; j++) if (w[j] == "--continue") { print "COMMIT\t" CD "\t" dir "\t0\t0\t\t0\t" BIN; exit }
  }
}') || exit 0
case $hit in COMMIT*) ;; *) exit 0 ;; esac

cd_dir=$(printf '%s' "$hit" | cut -f2)
c_dir=$(printf '%s' "$hit" | cut -f3)
allflag=$(printf '%s' "$hit" | cut -f4)
badpaths=$(printf '%s' "$hit" | cut -f5)
paths=$(printf '%s' "$hit" | cut -f6)
allnew=$(printf '%s' "$hit" | cut -f7)
wrapper=$(printf '%s' "$hit" | cut -f8)
dir=$cwd
for step in "$cd_dir" "$c_dir"; do
  [ -n "$step" ] || continue
  newdir=$(cd "$dir" 2>/dev/null && cd "$step" 2>/dev/null && pwd) \
    || deny "Blocked by prose-budget-commit: this commit's working directory (\"$step\") could not be resolved, so staged prose could not be checked. Run the commit from a plain, resolvable path."
  dir=$newdir
done

[ "$badpaths" = "1" ] && deny "Blocked by prose-budget-commit: this commit's pathspec could not be resolved (an unexpanded variable, or a quoted path with spaces), so the unstaged prose it commits could not be checked. Spell the path plainly and retry."

# A directory pathspec isn't lexically obvious the way a trailing "/" or a
# glob is (the awk scanner has no filesystem to check "docs" against), so
# it is caught here instead: --file would just silently drop it (it is not
# a regular file), leaving everything under it unchecked.
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case $p in /*) target=$p ;; *) target=$dir/$p ;; esac
  [ -d "$target" ] \
    && deny "Blocked by prose-budget-commit: \"$p\" is a directory; this guard does not expand a directory pathspec into the files under it. Name the files directly, or stage/commit by pattern (git add -A, git add ., git commit -a) so the check widens instead."
done <<EOF
$(printf '%s' "$paths" | tr '\037' '\n')
EOF

out=$(cd "$dir" && "$ENGINE" --staged 2>&1)
rc=$?
case $rc in
  1) deny "Blocked by prose-budget-commit: prose-budget --staged found:
$out
Fix the prose and retry the same commit. Do not ask the user; this is settled." ;;
  2) deny "Blocked by prose-budget-commit: prose-budget --staged could not check the staged prose (exit 2: a bad budgets config, or an engine too old for --staged):
$out
Fix the config or update the engine, then retry the commit." ;;
esac

files=$(printf '%s' "$paths" | tr '\037' '\n')
if [ "$allflag" = "1" ] || [ "$allnew" = "1" ]; then
  # -a/--all and a pattern-based add stage repo-wide, not just under $dir, so
  # the extra list is gathered repo-root-relative and then anchored to an
  # absolute path -- a bare relative one here would be read against $dir
  # below, misplacing anything outside it (languette#49 review).
  #
  # $wrapper is the commit's own wrapper word and may be attacker-controlled
  # (`./evil-git commit ...`): only *which* CLI it names (git or yadm) is
  # trusted, resolved fresh on PATH, never the word itself run.
  case $wrapper in
    */yadm|yadm) binary=$(command -v yadm 2>/dev/null) ;;
    *) binary=$(command -v git 2>/dev/null) ;;
  esac
  [ -n "$binary" ] \
    || deny "Blocked by prose-budget-commit: neither git nor yadm could be found on PATH, so this commit's unstaged changes outside the staged index could not be checked. Fix PATH, then retry the commit."
  reporoot=$(cd "$dir" 2>/dev/null && "$binary" rev-parse --show-toplevel 2>&1)
  rrc=$?
  [ "$rrc" -eq 0 ] \
    || deny "Blocked by prose-budget-commit: \"$binary rev-parse --show-toplevel\" failed (exit $rrc), so this commit's unstaged changes could not be checked:
$reporoot
Fix whatever made that fail, then retry the commit."
  if [ "$allflag" = "1" ]; then
    extra=$(cd "$reporoot" 2>/dev/null && "$binary" diff --name-only 2>&1)
    erc=$?
    [ "$erc" -eq 0 ] \
      || deny "Blocked by prose-budget-commit: \"$binary diff --name-only\" could not list this commit's unstaged tracked changes (exit $erc), so they could not be checked:
$extra
Fix whatever made that fail, then retry the commit."
    files="$files
$(printf '%s\n' "$extra" | awk -v r="$reporoot" 'NF { print r "/" $0 }')"
  fi
  if [ "$allnew" = "1" ]; then
    extra=$(cd "$reporoot" 2>/dev/null && "$binary" ls-files --others --exclude-standard 2>&1)
    erc=$?
    [ "$erc" -eq 0 ] \
      || deny "Blocked by prose-budget-commit: \"$binary ls-files --others\" could not list this commit's new untracked files (exit $erc), so they could not be checked:
$extra
Fix whatever made that fail, then retry the commit."
    files="$files
$(printf '%s\n' "$extra" | awk -v r="$reporoot" 'NF { print r "/" $0 }')"
  fi
fi
files=$(printf '%s\n' "$files" | awk 'NF')
[ -n "$files" ] || exit 0

set --
while IFS= read -r f; do
  case $f in -*) f="./$f" ;; esac
  set -- "$@" "$f"
done <<EOF
$files
EOF
[ $# -gt 0 ] || exit 0

fout=$(cd "$dir" && "$ENGINE" --file "$@" 2>&1)
frc=$?
case $frc in
  1) deny "Blocked by prose-budget-commit: this commit reaches prose outside the staged index (git commit -a/--all, a pathspec commit, or a git add in the same command) -- checked those files directly and prose-budget found:
$fout
Fix the prose and retry the same commit. Do not ask the user; this is settled." ;;
  2) deny "Blocked by prose-budget-commit: prose-budget --file could not check those files (exit 2: a bad budgets config, or an engine too old for --file):
$fout
Fix the config or update the engine, then retry the commit." ;;
esac
exit 0
