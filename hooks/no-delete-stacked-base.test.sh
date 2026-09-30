#!/usr/bin/env bash
# Tests for no-delete-stacked-base.sh. Run:
#   bash hooks/no-delete-stacked-base.test.sh
# Set AWK_PATH to a directory whose `awk` is another implementation (mawk,
# nawk, busybox) to check portability; CI runs it under mawk, gawk and
# original-awk.
#
# `gh` is stubbed on PATH throughout -- no test here reaches the network, and
# a test that did would pass or fail on whatever PRs happened to be open.
set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/no-delete-stacked-base.sh"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
CWD="$(cd "$(dirname "$0")/.." && pwd)"
pass=0
fail=0

STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR"' EXIT

# Open PRs the stub reports: #1 is stacked on claude/base-branch, which is
# itself the head of #2. claude/lonely is the head of #3 and the base of
# nothing.
# It records its arguments in $STUB_DIR/calls, ignores the filters (the
# hook's own jq select is what the tests exercise), and with GH_TAB set puts
# a literal tab in a title -- the character the decision JSON must survive.
cat > "$STUB_DIR/gh" <<'STUB'
#!/bin/sh
printf '%s\n' "$*" >> "${GH_CALLS:?}"
[ -n "${GH_FAIL:-}" ] && exit 1
t="stacked change"; [ -n "${GH_TAB:-}" ] && t="stacked\\tchange"
cat <<JSON
[
 {"number":1,"title":"$t","baseRefName":"claude/base-branch","headRefName":"claude/stacked-one"},
 {"number":2,"title":"the base change","baseRefName":"main","headRefName":"claude/base-branch"},
 {"number":3,"title":"unrelated","baseRefName":"main","headRefName":"claude/lonely"}
]
JSON
STUB
chmod +x "$STUB_DIR/gh"

# check <deny|ask|allow> <description> <command> [env assignment...]
check() {
  local want=$1 desc=$2 cmd=$3; shift 3
  local out got json
  json=$(jq -n --arg c "$cmd" --arg d "$CWD" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')
  : > "$STUB_DIR/calls"
  out=$(printf '%s' "$json" | env "$@" GH_CALLS="$STUB_DIR/calls" PATH="$STUB_DIR:$PATH" sh "$HOOK" 2>&1)
  LAST_OUT=$out
  case "$out" in
    *'"permissionDecision":"deny"'*) got=deny ;;
    *'"permissionDecision":"ask"'*)  got=ask ;;
    *) got=allow ;;
  esac
  if [ "$got" = "$want" ]; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    printf 'FAIL (want %s, got %s): %s\n' "$want" "$got" "$desc"
    [ -n "$out" ] && printf '  hook output: %s\n' "$out"
  fi
}

# --- must deny: deleting a branch an open PR is stacked on -----------------
check deny 'push --delete of a base branch'      'git push origin --delete claude/base-branch'
check deny 'push -d of a base branch'            'git push -d origin claude/base-branch'
check deny 'colon refspec delete of a base'      'git push origin :claude/base-branch'
check deny 'colon refspec, fully qualified'      'git push origin :refs/heads/claude/base-branch'
check deny 'refs/heads/ prefix stripped'         'git push origin --delete refs/heads/claude/base-branch'
check deny '--delete before the remote'          'git push --delete origin claude/base-branch'
check deny 'one of several refs is a base'       'git push origin --delete claude/spare claude/base-branch'
check deny 'yadm spelling'                       'yadm push origin --delete claude/base-branch'

# --- must deny: deleting the head branch of an open PR ---------------------
check deny 'push --delete of an open PR head'    'git push origin --delete claude/stacked-one'
check deny 'push --delete of a head that is nothing'\''s base' 'git push origin --delete claude/lonely'

# --- must deny: the REST spelling ------------------------------------------
check deny 'gh api -X DELETE'          'gh api -X DELETE repos/o/r/git/refs/heads/claude/base-branch'
check deny 'gh api --method DELETE'    'gh api --method DELETE repos/o/r/git/refs/heads/claude/base-branch'
check deny 'gh api -XDELETE'           'gh api -XDELETE repos/o/r/git/refs/heads/claude/base-branch'
check deny 'gh api --method=DELETE'    'gh api --method=DELETE repos/o/r/git/refs/heads/claude/base-branch'

# --- must deny: the bypasses the shared scanner exists to close ------------
check deny 'nested in sh -c'            "sh -c 'git push origin --delete claude/base-branch'"
check deny 'trailing shell comment'     'git push origin --delete claude/base-branch # harmless'
check deny 'absolute-path invocation'   '/usr/bin/git push origin --delete claude/base-branch'
check deny 'after a compound separator' 'echo hi && git push origin --delete claude/base-branch'
check deny 'unusual whitespace'         'git   push   origin   --delete   claude/base-branch'

# --- must ask: the branch or the PR list can't be resolved -----------------
check ask 'branch named by a variable' 'git push origin --delete "$b"'
check ask 'branch named by a glob'     'git push origin --delete claude/old-*'
check ask 'gh cannot answer'           'git push origin --delete claude/base-branch' GH_FAIL=1
check deny 'bare pr/merge/-d words after a real delete do not excuse it' \
                                        'git push origin --delete claude/base-branch pr merge -d'

# --- must ask: git pointed at a repository that is not the cwd -------------
check ask 'git -C another repo'        'git -C /elsewhere push origin --delete claude/base-branch'
check ask 'git --git-dir'              'git --git-dir=/elsewhere/.git push origin --delete claude/base-branch'
check ask 'GIT_DIR in the environment' 'GIT_DIR=/elsewhere/.git git push origin --delete claude/base-branch'
check deny 'git -C is not the ask when the delete itself is unrelated' 'git -C /elsewhere status && git push origin --delete claude/base-branch'

# --- the REST endpoint names the repository the PR list is read from ------
check deny 'gh api endpoint repo is queried' 'gh api -X DELETE repos/o/r/git/refs/heads/claude/base-branch'
grep -q -- '-R o/r' "$STUB_DIR/calls" || { fail=$((fail + 1)); printf 'FAIL: gh api endpoint repo o/r was not passed to gh pr list -R\n'; }
check deny 'gh api {owner}/{repo} placeholder is the cwd' 'gh api -X DELETE repos/{owner}/{repo}/git/refs/heads/claude/base-branch'
grep -q -- '-R' "$STUB_DIR/calls" && { fail=$((fail + 1)); printf 'FAIL: {owner}/{repo} endpoint should query the cwd, not -R\n'; }
check ask 'gh api endpoint repo unresolvable' 'gh api -X DELETE "repos/$OWNER/r/git/refs/heads/claude/base-branch"'

# --- the decision is JSON whatever the PR title holds ----------------------
check deny 'a tab in a PR title still denies' 'git push origin --delete claude/base-branch' GH_TAB=1
printf '%s' "$LAST_OUT" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 \
  || { fail=$((fail + 1)); printf 'FAIL: decision with a tab in the title is not valid JSON:\n  %s\n' "$LAST_OUT"; }

# --- must allow: the safe deletions and the non-deletions ------------------
# `gh pr merge` names no branch; it never reaches the scanner at all.
check allow 'delete of a branch no open PR names' 'git push origin --delete claude/already-merged'
check allow 'ordinary push'                       'git push origin main'
check allow 'ordinary push with a refspec'        'git push origin HEAD:main'
check allow 'force-push of a stacked branch'      'git push --force-with-lease origin claude/stacked-one'
check allow 'local delete takes nothing from a PR' 'git branch -D claude/base-branch'
check allow 'local delete, lowercase'             'git branch -d claude/base-branch'
check allow 'gh pr merge --delete-branch'         'gh pr merge 2 --delete-branch'
check allow 'gh pr merge -d'                      'gh pr merge 2 -d'
check allow 'merge and delete in one segment'     'gh pr merge 2 --delete-branch && echo done'
check allow 'unrelated command'                   'git status'
check allow 'gh api GET on a ref'                 'gh api repos/o/r/git/refs/heads/claude/base-branch'
check allow 'a delete quoted into prose'          "echo 'git push origin --delete claude/base-branch'"

if [ "$fail" -eq 0 ]; then
  printf 'no-delete-stacked-base: %d/%d passed\n' "$pass" "$pass"
else
  printf 'no-delete-stacked-base: %d passed, %d FAILED\n' "$pass" "$fail"
  exit 1
fi
