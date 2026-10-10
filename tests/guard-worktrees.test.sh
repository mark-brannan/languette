#!/usr/bin/env bash
# What guard-worktrees' tests keep in shell: the cases features/guard-worktrees-*.feature
# cannot say, because they edit the per-session record on disk or take a tool
# off PATH. Everything else lives in the feature files. Run: bash tests/guard-worktrees.test.sh
#
# The fixture is a throwaway repo with two linked worktrees, not this
# machine's real ones: the hook asks git what a path is, so the checks are
# only meaningful against paths git really answers about.
set -uo pipefail

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# `pwd -P` inside the hook resolves symlinks (/tmp is one on macOS), so the
# fixture paths must be resolved here too or every comparison misses.
TMP=$(cd "$TMP" && pwd -P)
# The guard runs as hooks.json runs it, by an absolute python3, so a
# bare-PATH case below still reaches the guard.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$TMP/hook"
printf '#!/bin/sh\nexec "%s" -I "%s/languette/run.py" --guard guard-worktrees\n' "$(command -v python3)" "$ROOT" >"$HOOK"

setup() (
  set -e
  cd "$TMP"
  git init -q --initial-branch=main repo
  cd repo
  git -c user.email=t@e -c user.name=t commit -q --allow-empty -m init
  mkdir -p .claude/worktrees
  git worktree add -q -b mine .claude/worktrees/mine
  git worktree add -q -b theirs .claude/worktrees/theirs
  cd "$TMP"
  git clone -q repo other-clone
)
setup || { echo "fixture setup failed"; exit 1; }

REPO="$TMP/repo"
MINE="$REPO/.claude/worktrees/mine"
THEIRS="$REPO/.claude/worktrees/theirs"
CLONE="$TMP/other-clone"
WTS="$REPO/.claude/worktrees"
# The hook keeps its per-session record under TMPDIR: keep every record this
# suite writes inside the fixture, never in the machine's /tmp.
export TMPDIR="$TMP/records"
mkdir -p "$TMPDIR"

pass=0
fail=0

# check <deny|allow> <description> <json payload>
check_json() {
  local want=$1 desc=$2 json=$3 out got
  out=$(printf '%s' "$json" | bash "$HOOK" 2>&1)
  if grep -q '"permissionDecision":"deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [ "$got" = "$want" ]; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf 'FAIL (want %s, got %s): %s\n' "$want" "$got" "$desc"
    [ -n "$out" ] && printf '  hook output: %s\n' "$out"
  fi
}

# sc <deny|allow> <description> <command> <session_id> <cwd>
sc() {
  check_json "$1" "$2" "$(jq -n --arg c "$3" --arg d "$5" --arg s "$4" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')"
}

# The record carries the .git inode: a worktree re-created at a recorded
# path is not inherited. Simulated by corrupting the recorded inode.
S3=11111111-0000-4000-8000-000000000003
NEW3="$WTS/new3"
sc allow 'S3 starts in its own worktree'                 'git status' "$S3" "$MINE"
sc allow 'S3 add-and-cd a worktree that does not exist'  "git worktree add -b new3 $NEW3 && cd $NEW3" "$S3" "$MINE"
git -C "$REPO" worktree add -q -b new3 "$NEW3"
sc allow 'S3 working in it'                              'git status' "$S3" "$NEW3"
S3REC="$TMPDIR/languette-guard-worktrees.$S3"
awk -F'\t' -v p="$NEW3" 'BEGIN { OFS = FS } $1 == p { $2 = 1 } { print }' "$S3REC" > "$S3REC.new" && mv "$S3REC.new" "$S3REC"
sc deny  'S3 record with a stale inode is not own'       "git -C $NEW3 status" "$S3" "$CLONE"

# A record that is a symlink is ignored (a shared /tmp could plant one).
S7=11111111-0000-4000-8000-000000000007
printf '%s\t%s\n' "$THEIRS" "$(ls -di "$THEIRS/.git" | awk '{print $1}')" > "$TMP/planted"
ln -s "$TMP/planted" "$TMPDIR/languette-guard-worktrees.$S7"
sc deny  'a symlinked record grants nothing'             "git -C $THEIRS status" "$S7" "$MINE"

# --- fails closed --------------------------------------------------------
# An absolute interpreter, since PATH is what is being taken away. The
# fail-closed reasons must not need sed or awk to be serialised, so this
# checks the output is valid JSON, not merely that it says deny.
out=$(printf '%s' "$(jq -n --arg c "git -C $THEIRS status" --arg d "$MINE" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')" \
  | env -i PATH=/nonexistent HOME="$HOME" /bin/sh "$HOOK" 2>/dev/null)
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass=$((pass + 1))
else
  fail=$((fail + 1))
  printf 'FAIL: nothing on PATH must fail closed with valid JSON\n  hook output: %s\n' "$out"
fi

# jq/awk/sed present, git absent: git is what every foreignness decision is
# asked of, so its absence must deny too, not treat every path as non-foreign.
no_git_dir=$(mktemp -d)
for t in jq awk sed; do
  p=$(command -v "$t") && ln -s "$p" "$no_git_dir/$t"
done
out=$(printf '%s' "$(jq -n --arg c "git -C $THEIRS status" --arg d "$MINE" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')" \
  | env -i PATH="$no_git_dir" HOME="$HOME" /bin/sh "$HOOK" 2>/dev/null)
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then
  pass=$((pass + 1))
else
  fail=$((fail + 1))
  printf 'FAIL: no git on PATH must fail closed\n  hook output: %s\n' "$out"
fi
rm -rf "$no_git_dir"

printf '%s\n' "guard-worktrees: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1
