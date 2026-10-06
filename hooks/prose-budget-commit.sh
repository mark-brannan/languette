#!/bin/sh
# PreToolUse Bash: before a `git commit`, runs the prose-budget engine
# (mark-brannan/claude, bin/prose-budget) and denies the commit on a
# finding, so documentation bloat is caught as it is written, not in CI.
# `--staged` checks the index; a commit that reaches past it (-a, a
# pathspec, an `add` in the same command, -p, --pathspec-from-file) also
# runs `--file` on what it would commit.
#
# The engine is found through $PROSE_BUDGET, else `prose-budget` on PATH.
# No engine, no config in the target repo, or an engine crash is a no-op:
# this guard only narrows what already passes through it. Exit 1 is a
# finding and denies; exit 2 (bad budgets config, or an engine too old for
# --staged/--file) denies and says so; any other exit is a no-op.
#
# Fail closed: anything the guard cannot resolve -- a `cd`/`-C` target, a
# pathspec word, a directory pathspec, a failed `diff`/`ls-files`, a second
# commit in a different directory -- denies rather than skips.
#
# `yadm` is recognised as git's wrapper word only, the same as in the other
# guards, and is never called unless the command named it.
#
# Every case is a scenario in features/prose-budget-commit.feature.
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
# <TAB>all-new<TAB>wrapper<TAB>multi" once, in END, for the git/yadm commits
# found (cd-dir, -C-dir and wrapper are the first commit's). paths is
# \037-joined: every pathspec word on an `add`, plus any trailing pathspec
# on a commit; a directory, glob, or other pattern among them widens
# all-flag/all-new (below) instead of being passed on as a literal,
# doomed-to-miss --file argument. all-flag is 1 when `-a`/`--all`/`-am` or
# `--pathspec-from-file` on commit, or `add -u`/`--update`, means every
# unstaged tracked change is in play, not just the named paths. all-new is
# 1 when an `add` staged by pattern rather than by name (`-A`, `--all`,
# `.`, `*`, `:`, an unrecognized flag), or the commit staged interactively
# (-p/--patch/--interactive) -- either can also pick up a brand new, still-
# untracked file, which a tracked-only diff cannot see. wrapper is the
# word that ran the commit (`git`, `yadm`, or a path to either) -- read
# only for *which* CLI it names, never executed itself, since it is as
# attacker-controlled as the rest of the command. A later commit in the
# same context (same cumulative cd, same -C dir, same git-vs-yadm) merges
# its tail into the same fields; one in a different context sets multi to
# 1, which the shell denies: one check cannot serve two repositories.
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
  if (!SEEN) exit
  pj = ""
  for (j = 1; j <= PATHN; j++) pj = pj (pj == "" ? "" : SEP) PATHS[j]
  print "COMMIT\t" CCD "\t" CDIR "\t" (ALLFLAG ? 1 : 0) "\t" (BAD ? 1 : 0) "\t" pj "\t" (ALLNEW ? 1 : 0) "\t" CBIN "\t" (MULTI ? 1 : 0)
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
function commit_tail(lo, hi,   i, v, c) {
  i = lo
  while (i <= hi) {
    if (w[i] == "--") {
      for (i++; i <= hi; i++) { if (isbad(i)) BAD = 1; else addwide_commit(w[i]) }
      return
    }
    if (w[i] == "--all") { ALLFLAG = 1; i++; continue }
    # The pathspec file is never read: a commit that names one reaches
    # past the index, and widening to every unstaged tracked change covers
    # whatever it lists.
    if (w[i] ~ /^--pathspec-from-file=/) { ALLFLAG = 1; i++; continue }
    if (w[i] == "--pathspec-from-file") { ALLFLAG = 1; i += 2; continue }
    # Interactive staging can pick hunks from any tracked change and add
    # an untracked file, so it widens to both listings.
    if (w[i] ~ /^(--patch|--interactive)$/) { ALLFLAG = 1; ALLNEW = 1; i++; continue }
    if (w[i] ~ /^(-m|--message|-F|--file|-C|--reuse-message|-c|--reedit-message|--fixup|--squash|--author|--date|--template)$/) { i += 2; continue }
    if (w[i] ~ /^-[A-Za-z]+$/) {
      # A short-option cluster: the first letter that takes a value takes
      # the rest of the word, or the next word when it is the last letter
      # -- `-am msg` skips msg, but `-mfix` carries its own message and the
      # word after it is a pathspec.
      v = match(w[i], /[mFcCt]/)
      c = substr(w[i], 2, (v ? v - 2 : length(w[i])))
      if (c ~ /a/) ALLFLAG = 1
      if (c ~ /p/) { ALLFLAG = 1; ALLNEW = 1 }
      i += (v && v == length(w[i])) ? 2 : 1
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
  if (i <= hi && (w[i] == "add" || w[i] == "stage")) {
    # "stage" is a built-in synonym for "add". The directory this add ran
    # in (cumulative cd plus its own -C) is recorded so the commit below
    # can tell whether it ran somewhere else -- a literal path collected
    # here only resolves against the commit own dir if the two agree.
    ADDSEEN = 1; ADDCTX = CD SUBSEP dir
    collect_add(i + 1, hi)
    return
  }
  if (i <= hi && w[i] == "commit") {
    commit_tail(i + 1, hi)
    commit_seen(CD, dir)
    return
  }
  if (i <= hi && w[i] == "merge") {
    for (j = i + 1; j <= hi; j++) if (w[j] == "--continue") { commit_seen(CD, dir); return }
  }
}
# Records a commit (or a merge --continue) in its context: cumulative cd,
# own -C dir, and which CLI (git or yadm) ran it. The first context seen
# is the one reported; a later commit elsewhere sets MULTI.
function commit_seen(cd, dir,   ctx) {
  ctx = cd SUBSEP dir SUBSEP (BIN ~ /(^|\/)yadm$/ ? "yadm" : "git")
  if (ADDSEEN && ADDCTX != (cd SUBSEP dir)) { ALLFLAG = 1; ALLNEW = 1 }
  if (!SEEN) { SEEN = 1; CTX = ctx; CCD = cd; CDIR = dir; CBIN = BIN }
  else if (ctx != CTX) MULTI = 1
}') || exit 0
case $hit in COMMIT*) ;; *) exit 0 ;; esac

cd_dir=$(printf '%s' "$hit" | cut -f2)
c_dir=$(printf '%s' "$hit" | cut -f3)
allflag=$(printf '%s' "$hit" | cut -f4)
badpaths=$(printf '%s' "$hit" | cut -f5)
paths=$(printf '%s' "$hit" | cut -f6)
allnew=$(printf '%s' "$hit" | cut -f7)
wrapper=$(printf '%s' "$hit" | cut -f8)
multi=$(printf '%s' "$hit" | cut -f9)
[ "$multi" = "1" ] && deny "Blocked by prose-budget-commit: this command commits in two different directories (or through both git and yadm), so the second commit's prose could not be checked against the right repository. Run the commits as separate commands."
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
Fix the prose and retry the same commit: this is a mechanical length check, not a judgment call that needs anyone's sign-off." ;;
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
  # $(...) drops NUL bytes, which would run every name in a -z listing
  # together into one path the engine never finds, so each listing goes
  # through a file and only `tr` ever sees the NULs (languette#49 review).
  tmp=$(mktemp -d 2>/dev/null) \
    || deny "Blocked by prose-budget-commit: could not make a temp directory to list this commit's unstaged changes, so they could not be checked. Retry the commit."
  trap 'rm -rf "$tmp"' EXIT
  # listz WHAT GIT-ARGS...: appends each path the listing names, anchored to
  # the repo root, to $files; a failed listing denies, naming WHAT.
  listz() {
    what=$1; shift
    (cd "$reporoot" && "$binary" "$@") >"$tmp/out" 2>"$tmp/err"
    erc=$?
    [ "$erc" -eq 0 ] \
      || deny "Blocked by prose-budget-commit: \"$binary $*\" could not list this commit's $what (exit $erc), so they could not be checked:
$(cat "$tmp/err")
Fix whatever made that fail, then retry the commit."
    [ "$(tr -cd '\n' <"$tmp/out" | wc -c)" -eq 0 ] \
      || deny "Blocked by prose-budget-commit: one of this commit's $what has a newline in its name, which cannot reach prose-budget intact, so it could not be checked. Rename it, then retry the commit."
    files="$files
$(tr '\0' '\n' <"$tmp/out" | R=$reporoot awk 'length { print ENVIRON["R"] "/" $0 }')"
  }
  # -z: a quoted (core.quotePath) name would reach --file as the quoted,
  # octal-escaped text, not the real path, and be silently dropped.
  # --diff-filter=d: a deleted file isn't content to check.
  [ "$allflag" = "1" ] && listz "unstaged tracked changes" diff -z --name-only --diff-filter=d
  [ "$allnew" = "1" ] && listz "new untracked files" ls-files -z --others --exclude-standard
fi
files=$(printf '%s\n' "$files" | awk 'length')
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
Fix the prose and retry the same commit: this is a mechanical length check, not a judgment call that needs anyone's sign-off." ;;
  2) deny "Blocked by prose-budget-commit: prose-budget --file could not check those files (exit 2: a bad budgets config, or an engine too old for --file):
$fout
Fix the config or update the engine, then retry the commit." ;;
esac
exit 0
