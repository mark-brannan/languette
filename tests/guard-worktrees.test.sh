#!/usr/bin/env bash
# Tests for guard-worktrees' foreign-worktree check. Run: bash tests/guard-worktrees.test.sh
#
# The fixture is a throwaway repo with two linked worktrees, not this
# machine's real ones: the hook asks git what a path is, so the checks are
# only meaningful against paths git really answers about, and naming a
# sibling worktree that exists today would rot the moment it is archived.
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
  git worktree add -q --no-checkout -b mine .claude/worktrees/mine >/dev/null 2>&1 || git worktree add -q -b mine .claude/worktrees/mine
  git -C .claude/worktrees/mine checkout -q mine 2>/dev/null || true
  git worktree add -q -b theirs .claude/worktrees/theirs
  mkdir -p .claude/worktrees/theirs/sub
  : > .claude/worktrees/theirs/sub/file.txt
  # A second, unrelated clone: a MAIN worktree, shared by every session and
  # nobody's private space, so it must stay allowed.
  cd "$TMP"
  git clone -q repo other-clone
  # A yadm-shaped repo: the git dir is `repo.git`, not `<toplevel>/.git`,
  # and its linked worktrees are foreign like any other.
  mkdir -p yadm
  git init -q --initial-branch=main --separate-git-dir="$TMP/yadm/repo.git" yhome
  git -C yhome -c user.email=t@e -c user.name=t commit -q --allow-empty -m init
  git -C yhome worktree add -q -b ytheirs "$TMP/ywt/theirs"
  # The state-dir scratchpad, for a session with no CLAUDE_CODE_TMPDIR.
  mkdir -p "home/.local/state/claude-tmpdir/claude-1000/proj/$SID/scratchpad"
  # Worktrees created under a session's scratchpad, in the claude-tmpdir
  # layout: one for the session the payloads will claim to be, one for
  # another session. Linked worktrees, so without the session-id rule both
  # are foreign.
  mkdir -p "scratch/claude-tmpdir/claude-1000/proj/$SID/scratchpad" \
           "scratch/claude-tmpdir/claude-1000/proj/$OTHER_SID/scratchpad"
  git -C repo worktree add -q -b own-scratch "$TMP/scratch/claude-tmpdir/claude-1000/proj/$SID/scratchpad/wt"
  git -C repo worktree add -q -b other-scratch "$TMP/scratch/claude-tmpdir/claude-1000/proj/$OTHER_SID/scratchpad/wt"
  # A directory whose name merely CONTAINS the id is not that session's.
  mkdir -p "scratch/claude-tmpdir/claude-1000/proj/x$SID/scratchpad"
  git -C repo worktree add -q -b substr-scratch "$TMP/scratch/claude-tmpdir/claude-1000/proj/x$SID/scratchpad/wt"
)
SID=aaaaaaaa-1111-4222-8333-444444444444
OTHER_SID=bbbbbbbb-1111-4222-8333-444444444444
setup || { echo "fixture setup failed"; exit 1; }

REPO="$TMP/repo"
MINE="$REPO/.claude/worktrees/mine"
THEIRS="$REPO/.claude/worktrees/theirs"
CLONE="$TMP/other-clone"
SCRATCH="$TMP/scratch/claude-tmpdir/claude-1000/proj"
OWN_WT="$SCRATCH/$SID/scratchpad/wt"
OTHER_WT="$SCRATCH/$OTHER_SID/scratchpad/wt"
SUBSTR_WT="$SCRATCH/x$SID/scratchpad/wt"
WTS="$REPO/.claude/worktrees"
# The hook keeps its per-session record under TMPDIR: keep every record this
# suite writes inside the fixture, never in the machine's /tmp.
export TMPDIR="$TMP/records"
mkdir -p "$TMPDIR" "$TMP/plain-tmp"

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

# bash <deny|allow> <description> <command> [cwd]
bash_check() {
  check_json "$1" "$3" "$(jq -n --arg c "$3" --arg d "${4:-$MINE}" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')"
}

# --- must deny: attaching to another session's worktree --------------------
bash_check deny 'git -C <foreign worktree>'        "git -C $THEIRS status"
bash_check deny 'git -C a subdir of one'           "git -C $THEIRS/sub log"
bash_check deny 'cd into one'                      "cd $THEIRS && git commit -m x"
bash_check deny '--work-tree=<foreign>'            "git --work-tree=$THEIRS status"
bash_check deny 'GIT_WORK_TREE=<foreign>'          "GIT_WORK_TREE=$THEIRS git status"
bash_check deny 'a relative path into one'         "git -C ../theirs status"
bash_check deny 'writing a file in one'            "sed -i s/a/b/ $THEIRS/sub/file.txt"
bash_check deny 'a file that does not exist yet'   "echo hi | tee $THEIRS/sub/new.txt"
bash_check deny 'reading a file in one'            "cat $THEIRS/sub/file.txt"
bash_check deny 'removing one'                     "git worktree remove $THEIRS"
bash_check deny 'inside sh -c'                     "sh -c \"cd $THEIRS && ls\""
bash_check deny 'from the main worktree'           "git -C $THEIRS status" "$REPO"
bash_check deny 'from an unrelated cwd'            "git -C $THEIRS status" /tmp
# cd drops `nope/..` lexically and lands in the sibling; the walk up to an
# existing directory would stop at the worktrees parent and allow it.
bash_check deny 'a .. after a missing dir, into a sibling' "cd $WTS/nope/../theirs && ls"
check_json deny 'Write through a .. after a missing dir' "$(jq -n --arg f "$WTS/nope/../theirs/f.txt" --arg d "$MINE" \
  '{tool_name:"Write",tool_input:{file_path:$f,content:"x"},cwd:$d}')"
bash_check allow 'a ref range is not a .. component' 'git log main..theirs'
# A control character in the reported path must still give valid JSON.
mkdir -p "$THEIRS/tab	dir"
out=$(jq -n --arg c "ls '$THEIRS/tab	dir'" --arg d "$MINE" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' | bash "$HOOK" 2>&1)
if jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1 <<<"$out"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL (want valid deny JSON): a tab in the path\n  hook output: %s\n' "$out"; fi

# --- must allow: everywhere that is not a private working directory --------
bash_check allow 'the main worktree of the repo'   "git -C $REPO status"
bash_check allow 'an unrelated clone'              "git -C $CLONE status"
bash_check allow 'this session own worktree'       "git -C $MINE status"
bash_check allow 'a path inside own worktree'      "cat $MINE/nothing-here.txt"
bash_check allow 'a plain relative path'           'cat README.md'
bash_check allow 'the worktrees parent directory'  "ls $REPO/.claude/worktrees/"
bash_check allow 'a ref, not a path'               'git log origin/main'
bash_check allow 'no path at all'                  'git status --porcelain'
# The whole point of the alternative the deny message offers.
bash_check allow 'reading a branch from here'      'git show theirs:sub/file.txt'

# --- own-scratchpad worktrees (measured 2026-09-30: 25 of 187 denials) -----
# sid_check <deny|allow> <description> <command> <session_id or ""> [cwd]
# A payload carrying a session id; an empty id leaves the field out, which
# is what a payload with no session looks like to the hook.
sid_check() {
  local json
  if [ -n "$4" ]; then
    json=$(jq -n --arg c "$3" --arg d "${5:-$MINE}" --arg s "$4" \
      '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')
  else
    json=$(jq -n --arg c "$3" --arg d "${5:-$MINE}" \
      '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')
  fi
  check_json "$1" "$2" "$json"
}
sid_check allow 'own-scratchpad worktree, id in payload'      "git -C $OWN_WT status" "$SID"
sid_check allow 'a file inside it'                            "cat $OWN_WT/file.txt" "$SID"
sid_check allow 'cd into it'                                  "cd $OWN_WT && git log" "$SID"
sid_check allow 'from the main worktree'                      "git -C $OWN_WT status" "$SID" "$REPO"
sid_check deny  'another session scratchpad worktree'         "git -C $OTHER_WT status" "$SID"
sid_check deny  'own-scratchpad path, no session id'          "git -C $OWN_WT status" ""
sid_check deny  'own-scratchpad path, wrong session id'       "git -C $OWN_WT status" "$OTHER_SID"
sid_check deny  'a dir name that merely contains the id'      "git -C $SUBSTR_WT status" "$SID"
sid_check deny  'the id does not unlock sibling worktrees'    "git -C $THEIRS status" "$SID"
check_json deny 'EnterWorktree(path=own-scratchpad worktree)' \
  "$(jq -n --arg p "$OWN_WT" --arg d "$MINE" --arg s "$SID" \
    '{tool_name:"EnterWorktree",tool_input:{path:$p},cwd:$d,session_id:$s}')"
# TMPDIR pointing at the scratchpad changes nothing by itself: the id in the
# payload is what decides, so a bare TMPDIR of /tmp allows nothing.
out=$(printf '%s' "$(jq -n --arg c "git -C $OWN_WT status" --arg d "$MINE" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')" \
  | TMPDIR="$SCRATCH/$SID/scratchpad" bash "$HOOK" 2>&1)
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: TMPDIR alone, no session id, must not allow\n  hook output: %s\n' "$out"; fi
out=$(printf '%s' "$(jq -n --arg c "git -C $OWN_WT status" --arg d "$MINE" --arg s "$SID" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')" \
  | TMPDIR="$TMP/plain-tmp" bash "$HOOK" 2>&1)
if grep -q '"permissionDecision":"deny"' <<<"$out"; then
  fail=$((fail + 1)); printf 'FAIL: own-scratchpad worktree with a TMPDIR outside it must still allow on the id\n  hook output: %s\n' "$out"; else pass=$((pass + 1)); fi
for tool in Edit Write; do
  check_json allow "$tool inside own-scratchpad worktree" \
    "$(jq -n --arg p "$OWN_WT/file.txt" --arg d "$MINE" --arg t "$tool" --arg s "$SID" \
      '{tool_name:$t,tool_input:{file_path:$p},cwd:$d,session_id:$s}')"
  check_json deny "$tool into another session scratchpad worktree" \
    "$(jq -n --arg p "$OTHER_WT/file.txt" --arg d "$MINE" --arg t "$tool" --arg s "$SID" \
      '{tool_name:$t,tool_input:{file_path:$p},cwd:$d,session_id:$s}')"
done

# --- sticky own: a cd elsewhere must not lock a session out (dotfiles#455)
# sc <deny|allow> <description> <command> <session_id> <cwd> [agent_id]
sc() {
  local json
  if [ -n "${6:-}" ]; then
    json=$(jq -n --arg c "$3" --arg d "$5" --arg s "$4" --arg a "$6" \
      '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s,agent_id:$a}')
  else
    json=$(jq -n --arg c "$3" --arg d "$5" --arg s "$4" \
      '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')
  fi
  check_json "$1" "$2" "$json"
}
S1=11111111-0000-4000-8000-000000000001
sc allow 'S1 starts in its own worktree'                 'git status' "$S1" "$MINE"
sc allow 'S1 cds into another repo'                      "cd $CLONE" "$S1" "$MINE"
sc allow 'from there, cd back to its own worktree'       "cd $MINE" "$S1" "$CLONE"
sc allow 'from there, git -C its own worktree'           "git -C $MINE status" "$S1" "$CLONE"
sc allow 'from there, Edit-shaped write into its own'    "sed -i s/a/b/ $MINE/x.txt" "$S1" "$CLONE"
sc deny  'from there, a sibling is still foreign'        "git -C $THEIRS status" "$S1" "$CLONE"
sc_edit=$(jq -n --arg p "$MINE/file.txt" --arg d "$CLONE" --arg s "$S1" \
  '{tool_name:"Edit",tool_input:{file_path:$p},cwd:$d,session_id:$s}')
check_json allow 'Edit into its own worktree from another repo' "$sc_edit"
# No session id: nothing recorded, so the old answer stands.
bash_check deny  'no session id: own worktree from elsewhere is foreign' "git -C $MINE status" "$CLONE"

# A cwd reached by an unchecked route is own while the shell stands in it
# (as before) but never recorded: leaving it makes it foreign again.
S2=11111111-0000-4000-8000-000000000002
sc allow 'S2 starts in its own worktree'                 'git status' "$S2" "$MINE"
sc allow 'S2 standing in a sibling, as before'           "git -C $THEIRS status" "$S2" "$THEIRS"
sc deny  'S2 after leaving it: not laundered into own'   "git -C $THEIRS status" "$S2" "$CLONE"

# A worktree the session made and cd'd into in one command is recorded.
S3=11111111-0000-4000-8000-000000000003
NEW3="$WTS/new3"
sc allow 'S3 starts in its own worktree'                 'git status' "$S3" "$MINE"
sc allow 'S3 add-and-cd a worktree that does not exist'  "git worktree add -b new3 $NEW3 && cd $NEW3" "$S3" "$MINE"
git -C "$REPO" worktree add -q -b new3 "$NEW3"
sc allow 'S3 working in it'                              'git status' "$S3" "$NEW3"
sc allow 'S3 leaves and comes back to it'                "cd $NEW3" "$S3" "$CLONE"
sc allow 'S3 still owns where it started'                "git -C $MINE status" "$S3" "$CLONE"
# The record carries the .git inode: a worktree re-created at a recorded
# path is not inherited. Simulated by corrupting the recorded inode.
S3REC="$TMPDIR/languette-guard-worktrees.$S3"
awk -F'\t' -v p="$NEW3" 'BEGIN { OFS = FS } $1 == p { $2 = 1 } { print }' "$S3REC" > "$S3REC.new" && mv "$S3REC.new" "$S3REC"
sc deny  'S3 record with a stale inode is not own'       "git -C $NEW3 status" "$S3" "$CLONE"
# A sibling that already existed is not recorded by a cd that names it.
S3b=11111111-0000-4000-8000-00000000003b
sc allow 'S3b starts in its own worktree'                'git status' "$S3b" "$MINE"
sc deny  'S3b cd into an existing sibling'               "cd $THEIRS" "$S3b" "$MINE"

# EnterWorktree(name=...) vouches for the next call's cwd.
S4=11111111-0000-4000-8000-000000000004
ENT4="$WTS/ent4"
sc allow 'S4 starts in its own worktree'                 'git status' "$S4" "$MINE"
check_json allow 'S4 EnterWorktree(name=ent4)' \
  "$(jq -n --arg d "$MINE" --arg s "$S4" '{tool_name:"EnterWorktree",tool_input:{name:"ent4"},cwd:$d,session_id:$s}')"
git -C "$REPO" worktree add -q -b ent4 "$ENT4"
sc allow 'S4 first call in the entered worktree'         'git status' "$S4" "$ENT4"
sc allow 'S4 leaves and reaches back into it'            "git -C $ENT4 status" "$S4" "$CLONE"
# Without the EnterWorktree, the same arrival is not vouched for.
S5=11111111-0000-4000-8000-000000000005
sc allow 'S5 starts in its own worktree'                 'git status' "$S5" "$MINE"
sc allow 'S5 lands in ent4 by no vouched route'          'git status' "$S5" "$ENT4"
sc deny  'S5 leaves: ent4 is not its own'                "git -C $ENT4 status" "$S5" "$CLONE"

# A subagent keeps its own record: parent and child do not share worktrees.
S6=11111111-0000-4000-8000-000000000006
sc allow 'S6 parent starts in its worktree'              'git status' "$S6" "$MINE"
sc allow 'S6 subagent starts in another'                 'git status' "$S6" "$THEIRS" agent-1
sc allow 'S6 subagent reaches its own from elsewhere'    "git -C $THEIRS status" "$S6" "$CLONE" agent-1
sc deny  'S6 parent does not inherit the subagent one'   "git -C $THEIRS status" "$S6" "$CLONE"
sc deny  'S6 subagent does not inherit the parent one'   "git -C $MINE status" "$S6" "$CLONE" agent-1

# A record that is a symlink is ignored (a shared /tmp could plant one).
S7=11111111-0000-4000-8000-000000000007
printf '%s\t%s\n' "$THEIRS" "$(ls -di "$THEIRS/.git" | awk '{print $1}')" > "$TMP/planted"
ln -s "$TMP/planted" "$TMPDIR/languette-guard-worktrees.$S7"
sc deny  'a symlinked record grants nothing'             "git -C $THEIRS status" "$S7" "$MINE"

# --- a cd target is checked whatever its spelling (dotfiles#455) ----------
bash_check deny  'one-component cd into a sibling'       'cd theirs' "$WTS"
bash_check deny  'cd -P with one component'              'cd -P theirs && ls' "$WTS"
bash_check deny  'pushd with one component'              'pushd theirs' "$WTS"
bash_check deny  'a chain of one-component cds'          'cd .claude && cd worktrees && cd theirs' "$REPO"
bash_check deny  'cd .. then a relative path'            'cd .. && cat theirs/sub/file.txt' "$MINE"
bash_check deny  'git -C with one component'             'git -C theirs status' "$WTS"
bash_check deny  'one-component cd inside sh -c'         'sh -c "cd theirs && ls"' "$WTS"
bash_check allow 'one-component cd into a plain dir'     'cd .claude' "$REPO"
bash_check allow 'one-component cd into own'             'cd mine' "$MINE"
sc allow 'S1 one-component cd home from the worktrees dir' 'cd mine' "$S1" "$WTS"
bash_check allow 'a bare cd'                             'cd' "$MINE"
bash_check allow 'cd -'                                  'cd -' "$MINE"
bash_check allow 'a word cd mentioned in prose'          'git commit -m "cd theirs"' "$WTS"

# --- must allow: prose that mentions a foreign path -----------------------
# A quoted string holding whitespace is one unresolvable word, and the
# scanner only queues it for a nested scan when the segment could execute
# it -- git and gh are prose consumers, so a message or an issue body passes.
bash_check allow 'a commit message naming one'     "git commit -m \"worktree $THEIRS is stale\""
bash_check allow 'an issue body naming one'        "gh issue comment 1 -b \"old work is in $THEIRS\""
bash_check allow 'an echo naming one'              "echo \"see $THEIRS for the old work\""

# --- must allow: an unresolvable word is not judged ------------------------
bash_check allow 'an unexpanded variable'          'git -C "$SOME_DIR" status'
bash_check allow 'a glob'                          "ls $REPO/.claude/worktrees/*/"

# --- file-editing tools ---------------------------------------------------
for tool in Edit Write MultiEdit; do
  check_json deny "$tool into a foreign worktree" \
    "$(jq -n --arg p "$THEIRS/sub/file.txt" --arg d "$MINE" --arg t "$tool" \
      '{tool_name:$t,tool_input:{file_path:$p},cwd:$d}')"
  check_json allow "$tool inside own worktree" \
    "$(jq -n --arg p "$MINE/file.txt" --arg d "$MINE" --arg t "$tool" \
      '{tool_name:$t,tool_input:{file_path:$p},cwd:$d}')"
done
check_json deny 'NotebookEdit into a foreign worktree' \
  "$(jq -n --arg p "$THEIRS/sub/nb.ipynb" --arg d "$MINE" \
    '{tool_name:"NotebookEdit",tool_input:{notebook_path:$p},cwd:$d}')"

# --- the deny's advice -----------------------------------------------------
check_msg() {  # check_msg <description> <pattern that must be in the deny message>
  local desc=$1 pattern=$2 out
  out=$(printf '%s' "$(jq -n --arg c "git -C $THEIRS status" --arg d "$MINE" \
      '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')" | bash "$HOOK" 2>&1)
  if grep -qF "$pattern" <<<"$out"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1)); printf 'FAIL (message missing %s): %s\n  hook output: %s\n' "$pattern" "$desc" "$out"
  fi
}
check_msg 'recovery advice is the ff-only merge, not checkout (dotfiles#233)' 'git merge --ff-only theirs'
check_msg 'message says why a self-made worktree is foreign (dotfiles#472)' 'yours only when the command that creates it also'

# --- EnterWorktree -------------------------------------------------------
# `path` is refused whatever it names: the tool does no ownership check, so
# there is no path value that makes it safe. `name` creates a fresh one.
check_json deny 'EnterWorktree(path=foreign)' \
  "$(jq -n --arg p "$THEIRS" --arg d "$MINE" '{tool_name:"EnterWorktree",tool_input:{path:$p},cwd:$d}')"
check_json deny 'EnterWorktree(path=own)' \
  "$(jq -n --arg p "$MINE" --arg d "$MINE" '{tool_name:"EnterWorktree",tool_input:{path:$p},cwd:$d}')"
check_json allow 'EnterWorktree(name=...)' \
  "$(jq -n --arg d "$MINE" '{tool_name:"EnterWorktree",tool_input:{name:"fresh"},cwd:$d}')"

# EnterWorktree(path=foreign)'s recovery advice is the ff-only merge, not
# checkout -- `git checkout <branch>` is denied by the auto-mode classifier
# even on a clean tree (dotfiles#233), so the hook must never recommend it.
out=$(printf '%s' "$(jq -n --arg p "$THEIRS" --arg d "$MINE" '{tool_name:"EnterWorktree",tool_input:{path:$p},cwd:$d}')" | bash "$HOOK" 2>&1)
if printf '%s' "$out" | grep -qF 'git merge --ff-only <branch>' && ! printf '%s' "$out" | grep -qF 'git checkout <branch>'; then
  pass=$((pass + 1))
else
  fail=$((fail + 1)); printf 'FAIL: EnterWorktree(path=...) must recommend ff-only merge, not checkout\n  hook output: %s\n' "$out"
fi

# The deny names the cross-repo recipe with this session's real scratchpad
# and the foreign worktree's git dir, and running that recipe is allowed.
recipe_cmd="git --git-dir=$REPO/.git worktree add $SCRATCH/$SID/scratchpad/<name> && cd $SCRATCH/$SID/scratchpad/<name>"
out=$(printf '%s' "$(jq -n --arg c "git -C $THEIRS status" --arg d "$MINE" --arg s "$SID" \
  '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')" \
  | CLAUDE_CODE_TMPDIR="$TMP/scratch/claude-tmpdir" bash "$HOOK" 2>&1)
if printf '%s' "$out" | grep -qF "$recipe_cmd"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: deny must print the scratchpad worktree recipe\n  hook output: %s\n' "$out"; fi
sid_check allow 'following the printed recipe' "${recipe_cmd//<name>/fresh-wt}" "$SID" /tmp
# A yadm-shaped repo: the recipe names repo.git, where `-C <repo>` has no
# directory to name.
out=$(printf '%s' "$(jq -n --arg c "git -C $TMP/ywt/theirs status" --arg d "$MINE" --arg s "$SID" \
  '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')" \
  | CLAUDE_CODE_TMPDIR="$TMP/scratch/claude-tmpdir" bash "$HOOK" 2>&1)
if printf '%s' "$out" | grep -qF "git --git-dir=$TMP/yadm/repo.git worktree add $SCRATCH/$SID/scratchpad/<name>"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: recipe for a yadm-shaped repo must name its repo.git\n  hook output: %s\n' "$out"; fi
# No CLAUDE_CODE_TMPDIR (a terminal session): the scratchpad is found under
# the state dir, not left as a placeholder.
out=$(printf '%s' "$(jq -n --arg c "git -C $THEIRS status" --arg d "$MINE" --arg s "$SID" \
  '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,session_id:$s}')" \
  | env -u CLAUDE_CODE_TMPDIR HOME="$TMP/home" bash "$HOOK" 2>&1)
if printf '%s' "$out" | grep -qF "worktree add $TMP/home/.local/state/claude-tmpdir/claude-1000/proj/$SID/scratchpad/<name>"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: recipe must find the state-dir scratchpad without CLAUDE_CODE_TMPDIR\n  hook output: %s\n' "$out"; fi

# --- other tools are none of this hook business --------------------------
check_json allow 'Read of a foreign path is not gated here' \
  "$(jq -n --arg p "$THEIRS/sub/file.txt" --arg d "$MINE" '{tool_name:"Read",tool_input:{file_path:$p},cwd:$d}')"

# --- fails closed --------------------------------------------------------
check_json deny 'unreadable payload' 'not json at all'
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

# jq/awk/sed present, git absent -- this is the case the header's own
# invariant would miss if only jq/awk/sed were checked: git is what every
# foreignness decision is asked of, so its absence must deny too, not
# silently treat every path as non-foreign.
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
