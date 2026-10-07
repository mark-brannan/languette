#!/usr/bin/env bash
# Tests for guard-private-terms.sh. Run: bash hooks/guard-private-terms.test.sh
# Set AWK_PATH to a directory whose `awk` is another implementation to run
# the same cases under it (CI does mawk, gawk, original-awk).
#
# What matters: a private term is caught wherever the body travels -- a
# flag value, a file, a heredoc, an MCP field, a different case -- the
# private repo is never scanned, reads are never touched, and the gate is
# loud when it cannot see the text or the denylist.
# shellcheck disable=SC2016  # the commands under test contain $(...) and $VAR on purpose
set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/guard-private-terms.sh"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
pass=0; fail=0
SCRATCH=$(mktemp -d); trap 'rm -rf "$SCRATCH"' EXIT
export HOME="$SCRATCH/home"; mkdir -p "$HOME"
export TMPDIR="$SCRATCH/tmp"; mkdir -p "$TMPDIR"

# A terms file, as the private_terms_file option names it. The terms here are
# invented: a real list is private and only ever read by path.
TERMS="$SCRATCH/private-terms.txt"
cat > "$TERMS" <<'EOF'
# private terms -- lines starting with # are comments

Wanderlust
gateway.home.example
  acct-4471
EOF
export CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE="$TERMS"
PRIVATE=you/notes
export CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS="someone/else, $PRIVATE"

# Two checkouts to resolve a cwd through: one whose origin is the private
# repo, one whose origin is public.
mkrepo() { mkdir -p "$1"; git -C "$1" init -q; git -C "$1" remote add origin "$2"; }
mkrepo "$SCRATCH/private" "git@github.com:$PRIVATE.git"
mkrepo "$SCRATCH/public" "https://github.com/mark-brannan/colregs.git"
mkdir -p "$SCRATCH/nogit"

LAST=""
# check <deny|allow> <desc> <json> [terms-file]
# An "allow" can come back empty (nothing to say) or as an explicit
# permissionDecision:allow carrying updatedInput (the home-path sanitizer) --
# both count as allow.
check() {
  local want=$1 desc=$2 json=$3 state=${4:-$CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE} out got
  out=$(printf '%s' "$json" | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE="$state" sh "$HOOK" 2>&1)
  if grep -q '"permissionDecision":"deny"' <<<"$out"; then got=deny
  elif [ -z "$out" ] || grep -q '"permissionDecision":"allow"' <<<"$out"; then got=allow
  else got=invalid; fi
  if [ "$got" = "$want" ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); printf 'FAIL (want %s, got %s): %s\n' "$want" "$got" "$desc"
    [ -n "$out" ] && printf '  hook output: %s\n' "$out"
  fi
  LAST=$out
}
reason() { if grep -Fq -- "$2" <<<"$(jq -r '.hookSpecificOutput.permissionDecisionReason' <<<"$LAST")"; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAIL (reason lacks [%s]): %s\n  %s\n' "$2" "$1" "$LAST"; fi; }
no_reason() { if grep -Fq -- "$2" <<<"$(jq -r '.hookSpecificOutput.permissionDecisionReason' <<<"$LAST")"; then fail=$((fail + 1)); printf 'FAIL (reason has [%s]): %s\n  %s\n' "$2" "$1" "$LAST"; else pass=$((pass + 1)); fi; }
updated_field() { printf '%s' "$LAST" | jq -r ".hookSpecificOutput.updatedInput$1 // empty"; }

# bash_in <cwd> <command>
bash_in() { jq -n --arg d "$1" --arg c "$2" '{tool_name:"Bash",cwd:$d,tool_input:{command:$c}}'; }
# mcp_in <tool> <tool_input json>
mcp_in() { jq -n --arg t "$1" --argjson i "$2" '{tool_name:$t,cwd:"/x",tool_input:$i}'; }
PUB="$SCRATCH/public"

# --- a term in the body, wherever it travels -----------------------------------
check deny 'term in --body'          "$(bash_in "$PUB" 'gh issue create --title "Log rotation" --body "seen on Wanderlust last night"')"
reason 'names the term'              'Wanderlust'
no_reason 'never the surrounding text' 'last night'
reason 'points at private_repos'      'private_repos'
reason 'or rewrite'                  'rewrite the body'
check deny 'term in --title'         "$(bash_in "$PUB" 'gh issue create -t "Wanderlust: AIS drops" -b "details below"')"
check deny 'term in -b glued'        "$(bash_in "$PUB" 'gh pr comment 12 -b"tested on Wanderlust"')"
check deny 'term in --body= form'    "$(bash_in "$PUB" 'gh issue edit 3 --body="host is gateway.home.example"')"
check deny 'term in pr review body'  "$(bash_in "$PUB" 'gh pr review 9 --approve --body "ok from acct-4471"')"
check deny 'term in issue close -c'  "$(bash_in "$PUB" 'gh issue close 3 -c "moved to Wanderlust log"')"
check deny 'term in pr merge -b'     "$(bash_in "$PUB" 'gh pr merge 5 --squash -b "tested on wanderlust"')"
check deny 'term after &&'           "$(bash_in "$PUB" 'git push && gh pr create --title x --body "cf Wanderlust"')"
check deny 'term escaped mid-word'   "$(bash_in "$PUB" 'gh issue create -t x -b Wander\lust')"
check deny 'term split across quotes' "$(bash_in "$PUB" "gh issue create -t x -b 'Wander'\"lust\"")"
check deny 'term in sh -c'           "$(bash_in "$PUB" "sh -c 'gh issue create -t x -b \"on Wanderlust\"'")"
check deny 'term in a heredoc'       "$(bash_in "$PUB" 'gh issue create -t x -F - <<'"'"'EOF'"'"'
Steps:
1. ssh to gateway.home.example
EOF')"
check deny 'term in a heredoc via variable' "$(bash_in "$PUB" 'body=$(cat <<EOF
crew of Wanderlust
EOF
)
gh issue create -t x -b "$body"')"

printf 'reproduced aboard Wanderlust\n' > "$SCRATCH/body.md"
printf 'nothing private here\n' > "$SCRATCH/clean.md"
check deny 'term in --body-file'     "$(bash_in "$PUB" "gh issue create -t x --body-file $SCRATCH/body.md")"
check deny 'term in -F, relative path' "$(bash_in "$SCRATCH" 'gh pr create -t x -F body.md')"
check deny 'term in --body-file=~ path' "$(cp "$SCRATCH/body.md" "$HOME/b.md"; bash_in "$PUB" 'gh issue comment 4 --body-file=~/b.md')"
check allow 'clean --body-file'      "$(bash_in "$PUB" "gh issue create -t x -F $SCRATCH/clean.md")"
# The path is read, not posted: a term in the directory name is not a hit,
# while a term in the file at that path still is.
mkdir -p "$SCRATCH/Wanderlust"; cp "$SCRATCH/clean.md" "$SCRATCH/body.md" "$SCRATCH/Wanderlust/"
check allow 'term in --body-file path only'   "$(bash_in "$PUB" "gh issue create -t x --body-file $SCRATCH/Wanderlust/clean.md")"
check allow 'term in --body-file= path only'  "$(bash_in "$PUB" "gh pr comment 4 --body-file=$SCRATCH/Wanderlust/clean.md")"
check allow 'term in api @file path only'     "$(bash_in "$PUB" "gh api repos/o/r/issues -f title=x -F body=@$SCRATCH/Wanderlust/clean.md")"
check deny  'term in file under such a path'  "$(bash_in "$PUB" "gh issue create -t x --body-file $SCRATCH/Wanderlust/body.md")"
check deny  'term elsewhere, path masked'     "$(bash_in "$PUB" "gh issue create -t Wanderlust --body-file $SCRATCH/Wanderlust/clean.md")"

# --- case-insensitive, fixed strings ------------------------------------------
check deny 'upper-case body, lower-case list' "$(bash_in "$PUB" 'gh issue create -t x -b "ACCT-4471 again"')"
check deny 'mixed case'              "$(bash_in "$PUB" 'gh issue create -t x -b "WANDERLUST"')"
check allow 'dot is literal, not any char' "$(bash_in "$PUB" 'gh issue create -t x -b "gatewayXhomeXexample"')"

# --- MCP ------------------------------------------------------------------------
check deny 'MCP create_issue body'   "$(mcp_in mcp__github__create_issue '{"owner":"mark-brannan","repo":"colregs","title":"x","body":"seen on Wanderlust"}')"
check deny 'MCP add_issue_comment'   "$(mcp_in mcp__github__add_issue_comment '{"owner":"o","repo":"r","issue_number":3,"body":"ping gateway.home.example"}')"
check deny 'MCP issue_write title'   "$(mcp_in mcp__github__issue_write '{"method":"create","owner":"o","repo":"r","title":"Wanderlust AIS"}')"
check deny 'MCP review comment nested' "$(mcp_in mcp__github__create_pull_request_review '{"owner":"o","repo":"r","pullNumber":1,"event":"COMMENT","comments":[{"path":"a.ts","body":"acct-4471"}]}')"
check allow 'MCP clean body'         "$(mcp_in mcp__github__create_issue '{"owner":"o","repo":"r","title":"x","body":"see mark-brannan/colregs#12"}')"
check allow 'MCP private repo'       "$(mcp_in mcp__github__create_issue '{"owner":"you","repo":"notes","title":"x","body":"Wanderlust"}')"
check allow 'MCP read tool ignored'  "$(mcp_in mcp__github__get_issue '{"owner":"o","repo":"r","issue_number":3}')"

# --- gh api -------------------------------------------------------------------------
check deny 'api POST issues -f body' "$(bash_in "$PUB" 'gh api repos/o/r/issues -f title=x -f body="aboard Wanderlust"')"
check deny 'api -X PATCH'            "$(bash_in "$PUB" 'gh api -X PATCH repos/o/r/issues/3 -f body=gateway.home.example')"
check deny 'api pulls review'        "$(bash_in "$PUB" 'gh api repos/o/r/pulls/3/reviews -f event=COMMENT -f body="acct-4471"')"
check deny 'api graphql addComment'  "$(bash_in "$PUB" "gh api graphql -f query='mutation { addComment(input:{subjectId:\"I_1\", body:\"from Wanderlust\"}) { clientMutationId } }'")"
check deny 'api -F body=@file'       "$(bash_in "$PUB" "gh api repos/o/r/issues/3/comments -F body=@$SCRATCH/body.md")"
check allow 'api GET issues'         "$(bash_in "$PUB" 'gh api repos/o/r/issues --jq ".[].title"')"
check allow 'api graphql read'       "$(bash_in "$PUB" "gh api graphql -f query='{ repository(owner:\"o\",name:\"r\"){ issue(number:3){ title } } }'")"
check allow 'api private repo path'  "$(bash_in "$PUB" "gh api repos/$PRIVATE/issues -f title=x -f body=Wanderlust")"

# --- the private repo is never scanned ------------------------------------------
check allow '--repo private'         "$(bash_in "$PUB" "gh issue create --repo $PRIVATE -t x -b 'aboard Wanderlust'")"
check allow '-R private, mixed case' "$(bash_in "$PUB" "gh issue create -R You/Notes -t x -b Wanderlust")"
check allow '--repo= URL form'       "$(bash_in "$PUB" "gh issue comment 3 --repo=https://github.com/$PRIVATE -b Wanderlust")"
check allow 'GH_REPO= private'       "$(bash_in "$PUB" "GH_REPO=$PRIVATE gh issue create -t x -b Wanderlust")"
check allow 'cwd origin is private'  "$(bash_in "$SCRATCH/private" 'gh issue create -t x -b "aboard Wanderlust"')"
# A positional URL or owner/repo#n, and a graphql node id, name a target
# other than the cwd's origin: a private cwd must not wave them through.
check deny 'cwd private, positional URL public' "$(bash_in "$SCRATCH/private" 'gh issue comment https://github.com/o/r/issues/1 -b Wanderlust')"
check deny 'cwd private, positional o/r#n public' "$(bash_in "$SCRATCH/private" 'gh pr comment o/r#1 -b Wanderlust')"
check allow 'cwd public, positional URL private' "$(bash_in "$PUB" "gh issue comment https://github.com/$PRIVATE/issues/1 -b Wanderlust")"
check deny 'cwd private, graphql mutation' "$(bash_in "$SCRATCH/private" "gh api graphql -f query='mutation { addComment(input:{subjectId:\"I_1\", body:\"from Wanderlust\"}) { clientMutationId } }'")"
# Nothing is private until the user lists it.
CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS='' check deny 'private_repos empty' "$(bash_in "$PUB" "gh issue create -R $PRIVATE -t x -b Wanderlust")"
check deny 'cwd private but cd elsewhere' "$(bash_in "$SCRATCH/private" "cd $PUB && gh issue create -t x -b Wanderlust")"
check deny 'cwd public'              "$(bash_in "$PUB" 'gh issue create -t x -b Wanderlust')"
check deny 'cwd not a repo'          "$(bash_in "$SCRATCH/nogit" 'gh issue create -t x -b Wanderlust')"
check deny 'one private, one public target' "$(bash_in "$PUB" "gh issue create --repo $PRIVATE -t x -b Wanderlust && gh issue comment 3 --repo o/r -b Wanderlust")"

# --- reads and clean bodies pass ------------------------------------------------
check allow 'gh issue list'          "$(bash_in "$PUB" 'gh issue list --label ready')"
check allow 'gh pr view'             "$(bash_in "$PUB" 'gh pr view 12 --comments')"
check allow 'gh pr checks'           "$(bash_in "$PUB" 'gh pr checks 12 --watch')"
check allow 'clean body, public names and URLs' "$(bash_in "$PUB" 'gh issue create -t "Ruling: Q-14" -b "Argument in mark-brannan/colregs requirements.md; see https://github.com/mark-brannan/colregs-engine/pull/25 and claude_prompts_scratch#3"')"
check allow 'no scannable text'      "$(bash_in "$PUB" 'gh pr merge 12 --squash --delete-branch')"
check allow 'echo mentioning a gh write' "$(bash_in "$PUB" 'echo "gh issue create --body hi"')"
check allow 'unrelated command'      "$(bash_in "$PUB" 'ls -la')"
check allow 'empty command'          "$(jq -n '{tool_name:"Bash",tool_input:{}}')"
check allow 'other tool'             "$(jq -n '{tool_name:"Read",tool_input:{file_path:"/x"}}')"

# --- the gate is loud when it cannot see ------------------------------------------
check deny '-F - with no heredoc'    "$(bash_in "$PUB" 'cat notes.md | gh issue create -t x -F -')"
reason 'says stdin'                  'stdin'
check allow '-F - with a clean heredoc' "$(bash_in "$PUB" 'gh issue create -t x -F - <<EOF
all public
EOF')"
check deny 'body from $(...)'        "$(bash_in "$PUB" 'gh issue create -t x -b "$(cat notes.md)"')"
reason 'says it is built at run time' 'run time'
check deny 'body from $VAR, no heredoc' "$(bash_in "$PUB" 'gh pr comment 3 --body "$body"')"
check allow 'inline $(cat <<EOF) clean' "$(bash_in "$PUB" 'gh pr create -t x --body "$(cat <<'"'"'EOF'"'"'
nothing private
EOF
)"')"
check deny 'inline $(cat <<EOF) with a term' "$(bash_in "$PUB" 'gh pr create -t x --body "$(cat <<'"'"'EOF'"'"'
seen aboard Wanderlust
EOF
)"')"
check allow '$VAR body fed by a clean heredoc' "$(bash_in "$PUB" 'b=$(cat <<EOF
public text
EOF
); gh pr comment 3 --body "$b"')"
check deny 'opaque $(...) beside an unrelated heredoc' "$(bash_in "$PUB" 'cat <<EOF
hello
EOF
gh issue create -t x --body "$(cat notes.md)"')"
reason 'says no heredoc feeds it'  'no heredoc in this command feeds it'
check deny '$VAR from a file, heredoc elsewhere' "$(bash_in "$PUB" 'body=$(cat notes.md); cat <<EOF
hi
EOF
gh pr comment 3 --body "$body"')"
# Single quotes make $ and ` ordinary characters: a body with markdown code
# spans or a literal $(...) is text the gate read, not a value it cannot see.
check allow 'backticks in a single-quoted body'  "$(bash_in "$PUB" "gh pr comment 3 -b 'Fixed in \`abc123\`, see \`prose-budget\`.'")"
check allow 'literal $(...) single-quoted'       "$(bash_in "$PUB" "gh issue create -t x -b 'run \$(date) yourself'")"
check deny  'backticks in a double-quoted body'  "$(bash_in "$PUB" 'gh pr comment 3 -b "Fixed in `git rev-parse HEAD`"')"
check deny  'term inside a single-quoted body'   "$(bash_in "$PUB" "gh pr comment 3 -b 'Fixed on \`Wanderlust\`.'")"

check deny 'missing --body-file'     "$(bash_in "$PUB" "gh issue create -t x -F $SCRATCH/absent.md")"
reason 'names the file'              'absent.md'
check allow 'missing --body-file, private repo' "$(bash_in "$PUB" "gh issue create --repo $PRIVATE -t x -F $SCRATCH/absent.md")"

# A file the same command writes from a heredoc does not exist yet, but its
# text does: the heredoc body is in the command the gate scanned. Denying it
# forced every session to split the write and the post into two Bash calls.
check allow 'heredoc writes the --body-file it posts' "$(bash_in "$PUB" "cat > $SCRATCH/later.md <<'EOF'
all public here
EOF
gh api -X POST repos/mark-brannan/dotfiles/pulls/1/comments -F body=@$SCRATCH/later.md")"
check deny  'heredoc-written --body-file still scanned' "$(bash_in "$PUB" "cat > $SCRATCH/later2.md <<'EOF'
hello from Wanderlust
EOF
gh api -X POST repos/mark-brannan/dotfiles/pulls/1/comments -F body=@$SCRATCH/later2.md")"
reason 'names the term'              'Wanderlust'
check allow 'heredoc tees the --body-file it posts' "$(bash_in "$PUB" "tee $SCRATCH/later3.md <<'EOF' >/dev/null
all public here
EOF
gh issue create -t x --body-file $SCRATCH/later3.md")"
check deny  'heredoc writes some other path' "$(bash_in "$PUB" "cat > $SCRATCH/other.md <<'EOF'
all public here
EOF
gh issue create -t x --body-file $SCRATCH/absent.md")"
reason 'names the file'              'absent.md'

# The path is resolved as the shell will resolve it (measured 2026-09-30:
# 218 denials for a --body-file "that cannot be read", 176 of them retried
# and passed with the same file; 88 still had a literal $SP in the path the
# hook tried, 30 missed a cd or a ..). Slice 1: . and .. are collapsed, and
# the file IS then scanned: a term in it still denies.
mkdir -p "$SCRATCH/proj/sub"; cp "$SCRATCH/clean.md" "$SCRATCH/body.md" "$SCRATCH/proj/"
check allow './ and .. in a relative --body-file, clean file' \
  "$(bash_in "$SCRATCH/proj/sub" 'gh pr comment 3 --body-file ./../clean.md')"
check deny  '.. in a relative --body-file, file still scanned' \
  "$(bash_in "$SCRATCH/proj/sub" 'gh pr comment 3 --body-file ../body.md')"
reason 'names the term'              'Wanderlust'
check allow '.. in an absolute --body-file' \
  "$(bash_in "$PUB" "gh pr comment 3 --body-file $SCRATCH/proj/sub/../clean.md")"
check allow '.. in the path a heredoc writes and posts' \
  "$(bash_in "$SCRATCH/proj" "cat > sub/../new.md <<'EOF'
all public
EOF
gh pr create -t x --body-file ./new.md")"
# Slice 2: a cd or pushd before the gh moves where a relative path is read
# from. popd, cd -, a bare pushd and a cd to somewhere the hook cannot
# resolve make that place unknown, and a relative path after it is denied.
check allow 'cd then a relative --body-file' \
  "$(bash_in "$PUB" "cd $SCRATCH/proj && gh pr comment 3 --body-file ./clean.md")"
check deny  'cd then a relative --body-file, file still scanned' \
  "$(bash_in "$PUB" "cd $SCRATCH/proj/sub && gh pr comment 3 --body-file ../body.md")"
reason 'names the term'              'Wanderlust'
check allow 'bare cd is $HOME' \
  "$(cp "$SCRATCH/clean.md" "$HOME/b.md"; bash_in "$PUB" 'cd; gh pr comment 3 -F b.md')"
check allow 'cd ~ is $HOME' \
  "$(bash_in "$PUB" 'cd ~ && gh pr comment 3 -F ./b.md')"
check allow 'cd ~ then .. collapses' \
  "$(mkdir -p "$HOME/d"; cp "$SCRATCH/clean.md" "$HOME/b.md"; bash_in "$PUB" 'cd ~/d; gh pr comment 3 -F ../b.md')"
check allow 'two cds, the second relative' \
  "$(bash_in "$PUB" "cd $SCRATCH; cd proj; gh pr comment 3 -F clean.md")"
check allow 'pushd then a relative --body-file' \
  "$(bash_in "$PUB" "pushd $SCRATCH/proj >/dev/null; gh pr comment 3 -F clean.md")"
check deny  'pushd, popd, then a relative --body-file is unknowable' \
  "$(bash_in "$SCRATCH" "pushd $SCRATCH/proj >/dev/null; popd >/dev/null; gh pr comment 3 -F clean.md")"
reason 'names the path as spelled'   'clean.md cannot be read'
# A directory literally named $X with a clean decoy in it must not let the
# literal text stand in for the value the shell will use.
mkdir -p "$SCRATCH/\$X"; cp "$SCRATCH/clean.md" "$SCRATCH/\$X/"
check deny  'cd to an unassigned $VAR makes a relative path unknowable, even past a literal $X decoy' \
  "$(bash_in "$SCRATCH" 'cd "$X" && gh pr comment 3 --body-file clean.md')"
mkdir -p "$SCRATCH/\`id\`"; cp "$SCRATCH/clean.md" "$SCRATCH/\`id\`/"
check deny  'cd to a backtick substitution is unknowable, even past a literal `id` decoy' \
  "$(bash_in "$SCRATCH" 'cd "`id`" && gh pr comment 3 --body-file clean.md')"
reason 'names the path as spelled'   'clean.md cannot be read'
check deny  'pushd +1 rotates to somewhere unseen' \
  "$(bash_in "$SCRATCH" 'pushd +1 >/dev/null; gh pr comment 3 --body-file clean.md')"
check deny  'cd - makes a relative path unknowable' \
  "$(bash_in "$SCRATCH" 'cd - && gh pr comment 3 --body-file clean.md')"
check allow 'cd - then an absolute path is still fine' \
  "$(bash_in "$PUB" "cd - && gh pr comment 3 --body-file $SCRATCH/clean.md")"
check allow 'cd inside sh -c does not move the outer command' \
  "$(bash_in "$SCRATCH" "sh -c 'cd /nowhere'; gh pr comment 3 --body-file clean.md")"
# A cd that runs in a pipeline, a subshell or the background does not move
# the shell that runs the gh: its place is unknown, so a relative path denies.
check deny  'cd in a pipeline does not move the later gh' \
  "$(bash_in "$SCRATCH" "cd $SCRATCH/proj | cat; gh pr comment 3 -F clean.md")"
check deny  'cd in a background job does not move the later gh' \
  "$(bash_in "$SCRATCH" "cd $SCRATCH/proj & gh pr comment 3 -F clean.md")"
check deny  'cd in a ( ) subshell, then a relative path' \
  "$(bash_in "$SCRATCH" "(cd $SCRATCH/proj); gh pr comment 3 -F clean.md")"
check deny  'a CDPATH prefix on the cd sends it somewhere unseen' \
  "$(bash_in "$SCRATCH" "CDPATH=/elsewhere cd proj && gh pr comment 3 -F clean.md")"
check allow 'cd after && still moves the shell' \
  "$(bash_in "$PUB" "true && cd $SCRATCH/proj && gh pr comment 3 -F clean.md")"
check allow 'a cd in a pipeline is fine when the path is absolute' \
  "$(bash_in "$PUB" "cd $SCRATCH/proj | cat; gh pr comment 3 -F $SCRATCH/clean.md")"
# A ( ) subshell inherits the cwd and its cd dies at the ): a paren that
# belongs to a neighbouring statement, or encloses both the cd and the gh,
# moves nothing. Only an unmatched ) means the shell is somewhere unseen.
check allow 'a ( ) statement before the cd does not touch it' \
  "$(bash_in "$PUB" "(true); cd $SCRATCH/proj; gh pr comment 3 -F clean.md")"
check allow 'a & ending the previous command does not background the cd' \
  "$(bash_in "$PUB" "true & cd $SCRATCH/proj && gh pr comment 3 -F clean.md")"
check allow 'the gh in a ( ) subshell inherits the cd before it' \
  "$(bash_in "$PUB" "cd $SCRATCH/proj; (gh pr comment 3 -F clean.md)")"
check allow 'cd and gh inside the same ( ) subshell' \
  "$(bash_in "$PUB" "true; (cd $SCRATCH/proj && gh pr comment 3 -F clean.md)")"
check allow 'a cd inside ( ) dies at the ), restoring the cwd before it' \
  "$(bash_in "$PUB" "cd $SCRATCH/proj; (cd /); gh pr comment 3 -F clean.md")"
check deny  'nested ( ): the inner ) restores, the outer ) loses the cd' \
  "$(bash_in "$PUB" "(cd $SCRATCH/proj; (cd /)); gh pr comment 3 -F clean.md")"
# Slice 3: a variable this same command assigns before the gh is expanded
# in the path (88 of the measured denials). One it never assigned, or a
# prefix assignment on the gh itself, stays a $ and is denied. A path
# inside sh -c is read as spelled: literal and absolute, or denied.
mkdir -p "$SCRATCH/sp"; cp "$SCRATCH/clean.md" "$SCRATCH/body.md" "$SCRATCH/sp/"
check allow '$VAR assigned in the same command, clean file' \
  "$(bash_in "$PUB" "SP=$SCRATCH/sp; gh pr create -t x --body-file \"\$SP/clean.md\"")"
check deny  '$VAR assigned in the same command, file still scanned' \
  "$(bash_in "$PUB" "SP=$SCRATCH/sp; gh pr create -t x --body-file \"\$SP/body.md\"")"
reason 'names the term'              'Wanderlust'
check allow '${VAR} via $HOME, chained through a second assignment' \
  "$(bash_in "$PUB" 'export SP="$HOME"; S=$SP; gh issue create -t x --body-file ${S}/b.md')"
check allow '$VAR assigned, heredoc writes the file in the same command' \
  "$(bash_in "$PUB" "SP=$SCRATCH/sp
cat > \"\$SP/new.md\" <<'EOF'
all public
EOF
gh pr create -t x --body-file \"\$SP/new.md\"")"
check allow 'cd to a $VAR, then a relative path' \
  "$(bash_in "$PUB" "D=$SCRATCH; cd \$D/sp && gh pr comment 3 -F clean.md")"
check allow 'a later assignment wins' \
  "$(bash_in "$PUB" "SP=/nowhere; SP=$SCRATCH/sp; gh pr comment 3 -F \$SP/clean.md")"
check deny  '$VAR not assigned in this command' \
  "$(bash_in "$PUB" 'gh pr create -t x --body-file "$SP/clean.md"')"
reason 'names the path as spelled'   '$SP/clean.md'
reason 'says earlier commands are invisible' 'earlier command is invisible'
check deny  'prefix assignment on the gh does not feed its own path' \
  "$(bash_in "$PUB" "SP=$SCRATCH/sp gh pr create -t x --body-file \"\$SP/clean.md\"")"
check deny  'a quoted word leading a segment is not an assignment list' \
  "$(mkdir -p "$SCRATCH/decoy"; cp "$SCRATCH/clean.md" "$SCRATCH/decoy/notes.md"; cp "$SCRATCH/body.md" "$SCRATCH/sp/notes.md"; bash_in "$PUB" "SP=$SCRATCH/sp
\"touch x\" SP=$SCRATCH/decoy
gh pr create -t x --body-file \"\$SP/notes.md\"")"
reason 'reads the real path, not the decoy' 'Wanderlust'
check deny  'a single-quoted $ in a value is literal, so the path is unknowable' \
  "$(bash_in "$PUB" "SP='\$HOME'; gh pr create -t x --body-file \"\$SP/b.md\"")"
check deny  'a quoted ~ in a value is literal, so the path is unknowable' \
  "$(mkdir -p "$PUB/~"; cp "$SCRATCH/body.md" "$PUB/~/b.md"; bash_in "$PUB" "X='~'; gh pr create -t x --body-file \"\$X/b.md\"")"
check deny  'a double-quoted ~ is literal too' \
  "$(bash_in "$PUB" 'X="~/d"; gh pr create -t x --body-file "$X/../b.md"')"
check allow 'SP=~ unquoted expands at assignment' \
  "$(bash_in "$PUB" 'SP=~; gh pr comment 3 -F $SP/b.md')"
check deny  '$VAR from $(...) stays unknowable' \
  "$(bash_in "$PUB" 'SP=$(mktemp -d); gh pr create -t x --body-file "$SP/clean.md"')"
check deny  'a $VAR inside sh -c is not fed by the outer assignment' \
  "$(bash_in "$PUB" "SP=$SCRATCH/sp; sh -c 'gh pr create -t x --body-file \$SP/clean.md'")"
check deny  'a ~ path inside sh -c is not expanded' \
  "$(bash_in "$PUB" "sh -c 'gh pr create -t x --body-file ~/b.md'")"
check allow 'an absolute path inside sh -c is read as spelled' \
  "$(bash_in "$PUB" "sh -c 'gh pr create -t x --body-file $SCRATCH/sp/clean.md'")"

# The exemption is the gate's weakest point: it says "that file will hold the
# heredoc body I read". Two ways that stops being true, both denied.
# 1. `<<` inside a heredoc BODY is body text, not a redirect: content the
#    command merely quotes must never be able to name a path as vouched for.
check deny 'decoy <<  inside a heredoc body' "$(bash_in "$PUB" "cat > $SCRATCH/dummy.txt <<'EOF'
noop > $SCRATCH/payload.md <<X
EOF
printf 'aboard Wanderlust' > $SCRATCH/payload.md
gh issue create -t test --body-file $SCRATCH/payload.md")"
reason 'names the file'              'payload.md'
# 2. A genuine heredoc write, then mutated again before the post: the gate
#    read the body, not the append.
check deny 'heredoc write then appended to' "$(bash_in "$PUB" "cat > $SCRATCH/mut.md <<'EOF'
public safe text
EOF
echo 'seen on Wanderlust' >> $SCRATCH/mut.md
gh pr comment 5 --body-file $SCRATCH/mut.md")"
reason 'names the file'              'mut.md'

# terms file set but missing: deny, naming the option; set to nothing: inert
EMPTY="$SCRATCH/no-such-terms.txt"
out=$(bash_in "$PUB" 'gh issue create -t x -b "all public"' | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE=$EMPTY sh "$HOOK" 2>&1); LAST=$out
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: terms file missing should deny: $out"; fi
reason 'says the terms file is unreadable' 'is unreadable'
reason 'names the option'            'private_terms_file'
reason 'offers private_repos'         'private_repos'
out=$(bash_in "$PUB" "gh issue create --repo $PRIVATE -t x -b Wanderlust" | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE=$EMPTY sh "$HOOK" 2>&1)
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: private repo needs no terms file: $out"; fi
out=$(bash_in "$PUB" 'gh issue list' | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE=$EMPTY sh "$HOOK" 2>&1)
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: a read needs no terms file: $out"; fi

# Option unset or empty: inert. The guard allows a post that names a term it
# was never told about, and never touches jq or awk (a bare PATH proves it).
# Unset is not the same as set-but-unreadable above, which denies.
for v in unset empty; do
  if [ "$v" = unset ]; then
    out=$(bash_in "$PUB" 'gh issue create -t x -b "seen on Wanderlust"' | env -u CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE PATH=/nonexistent /bin/sh "$HOOK" 2>&1)
  else
    out=$(bash_in "$PUB" 'gh issue create -t x -b "seen on Wanderlust"' | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE='' PATH=/nonexistent /bin/sh "$HOOK" 2>&1)
  fi
  if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: option $v should be inert: $out"; fi
done

# terms file present but empty: a readable file with no terms matches nothing,
# which would let every post through looking exactly like a check that ran.
BLANK="$SCRATCH/blank.txt"
printf '# comments only\n\n   \n' > "$BLANK"
out=$(bash_in "$PUB" 'gh issue create -t x -b "all public"' | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE=$BLANK sh "$HOOK" 2>&1); LAST=$out
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: empty terms file should deny: $out"; fi
reason 'says the terms file has no terms' 'no terms in it'
out=$(bash_in "$PUB" "gh issue create --repo $PRIVATE -t x -b Wanderlust" | CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE=$BLANK sh "$HOOK" 2>&1)
if [ -z "$out" ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: private repo needs no terms: $out"; fi

# comment and blank lines in the denylist are not terms
check allow 'comment line is not a term' "$(bash_in "$PUB" 'gh issue create -t x -b "private terms -- lines starting"')"

# --- narrow scan: a path in the command is read, never posted -------------------
# Three false positives found in transcripts (2026-09-12): a `cd` prefix, a
# --body-file under a scratchpad path, and an unrecognised --comment-file --
# all denied because the raw command line, not just what gets posted, used
# to be scanned wholesale, and a scratchpad path under $HOME collides with
# the home-directory denylist term. A denylist naming the real $HOME proves
# the fix -- without it these commands never would have tripped either way.
HOMETERMS="$SCRATCH/hometerms.txt"
printf '%s\n' "$HOME" > "$HOMETERMS"

check allow 'cd prefix: the path is not posted text' \
  "$(bash_in "$PUB" "cd $HOME/worktrees/xyz && gh issue comment 3 -b 'ready for review'")" "$HOMETERMS"

printf 'a clean scratchpad body\n' > "$HOME/scratch-body.md"
check allow '--body-file under a scratchpad path: content is read, path is not' \
  "$(bash_in "$PUB" "gh issue create -t x --body-file $HOME/scratch-body.md")" "$HOMETERMS"

printf 'a clean scratchpad comment\n' > "$HOME/scratch-comment.md"
check allow '--comment-file is now a recognised file flag' \
  "$(bash_in "$PUB" "gh issue comment 3 --comment-file $HOME/scratch-comment.md")" "$HOMETERMS"
check deny '--comment-file with a term in its content still denies' \
  "$(printf 'seen aboard Wanderlust\n' > "$SCRATCH/comment-term.md"; bash_in "$PUB" "gh issue comment 3 --comment-file $SCRATCH/comment-term.md")"
reason 'names the term' 'Wanderlust'

# --- fail closed: an unrecognised flag that looks like it carries text ----------
check deny 'unrecognised body/comment/message-shaped flag refuses loudly' \
  "$(bash_in "$PUB" 'gh issue comment 3 --response-body-file /tmp/x')"
reason 'names the flag' '--response-body-file'
reason 'says it does not recognise the shape' "doesn't recognise its shape"
check deny 'unrecognised flag, gh api'          "$(bash_in "$PUB" 'gh api repos/o/r/issues -f title=x --long-comment-blob=hi')"
check allow 'a boolean flag with no text is not "unrecognised"' \
  "$(bash_in "$PUB" 'gh pr merge 12 --squash --delete-branch')"
check allow 'an unrecognised text-shaped flag on the private repo is not scanned' \
  "$(bash_in "$PUB" "gh issue comment 3 --repo $PRIVATE --response-body-file /tmp/x")"

# --- home path in genuinely-posted text: sanitize and allow, not deny -----------
check allow 'home path in a posted body is rewritten to ~, not denied' \
  "$(bash_in "$PUB" "gh issue comment 3 -b 'repro: cd $HOME/project && make'")" "$HOMETERMS"
newcmd=$(updated_field '.command')
case "$newcmd" in
  *"$HOME"*) fail=$((fail + 1)); echo "FAIL: updatedInput still carries the literal home path: $newcmd" ;;
  *'~/project'*) pass=$((pass + 1)) ;;
  *) fail=$((fail + 1)); echo "FAIL: updatedInput missing the ~ substitution: $newcmd" ;;
esac

check allow 'MCP: home path in a posted body is rewritten to ~' \
  "$(mcp_in mcp__github__add_issue_comment "{\"owner\":\"o\",\"repo\":\"r\",\"issue_number\":3,\"body\":\"repro under $HOME/project\"}")" "$HOMETERMS"
newbody=$(updated_field '.body')
case "$newbody" in
  *"$HOME"*) fail=$((fail + 1)); echo "FAIL: MCP updatedInput still carries the literal home path: $newbody" ;;
  *'~/project'*) pass=$((pass + 1)) ;;
  *) fail=$((fail + 1)); echo "FAIL: MCP updatedInput missing the ~ substitution: $newbody" ;;
esac

# a body-file's own content is not fixable by rewriting the command -- the
# file on disk still carries the real path -- so that stays a denial.
printf 'repro under %s/project\n' "$HOME" > "$SCRATCH/home-in-file.md"
check deny 'home path inside a --body-file stays a denial' \
  "$(bash_in "$PUB" "gh issue create -t x --body-file $SCRATCH/home-in-file.md")" "$HOMETERMS"

# a longer path that merely starts with $HOME is not $HOME: a substring
# replace would corrupt it (~2 resolves to a different user at execution
# time). Scar: caught in PR review on dotfiles#184.
check deny 'a longer path starting with $HOME is not sanitized' \
  "$(bash_in "$PUB" "gh issue comment 3 -b 'see ${HOME}2/notes for details'")" "$HOMETERMS"
reason 'still cites the term, unfixed -- ~2 is a different user, not $HOME' "$HOME"

# same failure mode with a hyphenated sibling directory instead of a digit --
# '-' must be in the "still part of the same name" class too, not just
# alnum/underscore. Scar: caught in PR review on dotfiles#184, round 2.
check deny 'a hyphenated sibling path starting with $HOME is not sanitized' \
  "$(bash_in "$PUB" "gh issue comment 3 -b 'see ${HOME}-backup/notes for details'")" "$HOMETERMS"
reason 'still cites the term, unfixed -- a hyphenated sibling is not $HOME' "$HOME"

# home path plus an unrelated real private term: still denied -- fixing the
# home path alone would not make the post safe.
MIXEDTERMS="$SCRATCH/mixedterms.txt"
printf '%s\nWanderlust\n' "$HOME" > "$MIXEDTERMS"
check deny 'home path plus another private term: still denied' \
  "$(bash_in "$PUB" "gh issue comment 3 -b 'seen aboard Wanderlust, path $HOME/x'")" "$MIXEDTERMS"
reason 'still names the other term' 'Wanderlust'

# no awk: deny, do not crash quiet
mkdir -p "$SCRATCH/noawk"; for b in jq cat dirname mktemp rm sed grep tr git head; do ln -s "$(command -v $b)" "$SCRATCH/noawk/$b"; done
out=$(bash_in "$PUB" 'gh issue create -t x -b hi' | PATH="$SCRATCH/noawk" /bin/sh "$HOOK" 2>&1); LAST=$out
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: awk absent should deny: $out"; fi
reason 'names awk as missing'        'awk missing'

printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
