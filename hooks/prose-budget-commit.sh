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
# to wherever this hook process happens to run from.
case $ENGINE in /*) : ;; *) ENGINE=$cwd/$ENGINE ;; esac
[ -x "$ENGINE" ] || exit 0

# Prints "COMMIT<TAB>cd-dir<TAB>-C-dir" for the first git/yadm commit found.
hit=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
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
function segment(lo, hi, nested,   g, i, dir) {
  if (w[lo] == "cd" && k[lo + 1] == "w") CD = w[lo + 1]
  g = cmd_index(w, k, lo, hi, "(^|/)(git|yadm)$", nested, "")
  if (!g) return
  i = g + 1; dir = ""
  while (i <= hi && w[i] ~ /^-/) {
    if (w[i] == "-C") { dir = w[i + 1]; i++ }
    else if (w[i] ~ /^(-c|--git-dir|--work-tree|--namespace)$/) i++
    i++
  }
  if (i <= hi && w[i] == "commit") { print "COMMIT\t" CD "\t" dir; exit }
  if (i <= hi && w[i] == "merge") {
    for (j = i + 1; j <= hi; j++) if (w[j] == "--continue") { print "COMMIT\t" CD "\t" dir; exit }
  }
}') || exit 0
case $hit in COMMIT*) ;; *) exit 0 ;; esac

cd_dir=$(printf '%s' "$hit" | cut -f2)
c_dir=$(printf '%s' "$hit" | cut -f3)
dir=$cwd
for step in "$cd_dir" "$c_dir"; do
  [ -n "$step" ] || continue
  newdir=$(cd "$dir" 2>/dev/null && cd "$step" 2>/dev/null && pwd) \
    || deny "Blocked by prose-budget-commit: this commit's working directory (\"$step\") could not be resolved, so staged prose could not be checked. Run the commit from a plain, resolvable path."
  dir=$newdir
done

out=$(cd "$dir" && "$ENGINE" --staged 2>&1)
rc=$?
case $rc in 1|2) ;; *) exit 0 ;; esac

deny "Blocked by prose-budget-commit: prose-budget --staged found:
$out
Fix the prose and retry the same commit. Do not ask the user; this is settled."
