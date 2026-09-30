#!/usr/bin/env bash
# Tests for no-git-footguns.sh. Run: bash hooks/no-git-footguns.test.sh
# shellcheck disable=SC2016  # the commands under test contain $(...) on purpose
set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/no-git-footguns.sh"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
pass=0; fail=0

check() {
  local want=$1 desc=$2 cmd=$3 out got
  out=$(jq -n --arg c "$cmd" '{tool_name:"Bash",tool_input:{command:$c}}' | timeout 5 sh "$HOOK" 2>&1; [ "${PIPESTATUS[1]}" = 124 ] && echo TIMEOUT)
  if grep -q '"permissionDecision":"deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [ "$got" = "$want" ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); printf 'FAIL (want %s, got %s): %s\n  cmd: %s\n' "$want" "$got" "$desc" "$cmd"
    [ -n "$out" ] && printf '  hook output: %s\n' "$out"
  fi
}

# --- blanket staging ---
check deny  'add -A'                    'git add -A'
check deny  'add --all'                 'git add --all'
check deny  'add .'                     'git add .'
check deny  'add :/'                    'git add :/'
check deny  'add -u no path'            'git add -u'
check deny  'add cluster -Av'           'git add -Av'
check deny  'yadm add -A'               'yadm add -A'
check deny  'add -A in compound'        'cd foo && git add -A && git commit -m x'
check deny  'git -C dir add -A'         'git -C /some/dir add -A'
check deny  'commit -a'                 'git commit -a -m "x"'
check deny  'commit -am'                'git commit -am "x"'
check deny  'commit --all'              'git commit --all -m x'
check allow 'add by path'               'git add hooks/foo.sh README.md'
check allow 'add -u with path'          'git add -u src/'
check allow 'add -p'                    'git add -p foo'
check allow 'commit -m'                 'git commit -m "add -A everything"'
check allow 'commit --amend'            'git commit --amend --no-edit'
check allow 'commit message mentions -a' "git commit -m 'block git commit -a'"
check allow 'commit -S signed'          'git commit -S -m x'

# --- stash ---
check deny  'stash pop'                 'git stash pop'
check deny  'stash pop ref'             'git stash pop stash@{2}'
check allow 'stash push'                'git stash push -u -m tag'
check allow 'stash apply'               'git stash apply abc123'
check allow 'stash list'                'git stash list --format="%H %gs"'
check allow 'stash drop'                'git stash drop stash@{0}'

# --- force push ---
check deny  'push --force'              'git push --force origin foo'
check deny  'push -f'                   'git push -f origin foo'
check deny  'push -fu'                  'git push -fu origin foo'
check deny  'push +refspec'             'git push origin +foo'
check deny  'lease to main'             'git push --force-with-lease origin main'
check deny  'lease to HEAD:main'        'git push --force-with-lease origin HEAD:main'
check deny  'lease to refs/heads/main'  'git push --force-with-lease origin foo:refs/heads/main'
check deny  'lease to master'           'git push --force-with-lease=master origin master'
check allow 'lease to branch'           'git push --force-with-lease origin claude/foo'
check allow 'lease to branch HEAD:'     'git push --force-with-lease origin HEAD:claude/foo'
check allow 'lease from main to branch' 'git push --force-with-lease origin main:backup'
check allow 'plain push main'           'git push origin HEAD:main'
check allow 'push -u'                   'git push -u origin claude/foo'
check allow 'push --force-if-includes'  'git push --force-with-lease --force-if-includes origin claude/foo'

# --- discard ---
check deny  'checkout .'                'git checkout .'
check deny  'checkout -- .'             'git checkout -- .'
check deny  'restore .'                 'git restore .'
check deny  'restore --worktree .'      'git restore -SW .'
check deny  'clean -f'                  'git clean -f'
check deny  'clean -fdx'                'git clean -fdx'
check allow 'checkout branch'           'git checkout main'
check allow 'checkout -b'               'git checkout -b foo'
check allow 'checkout one path'         'git checkout -- src/foo.ts'
check allow 'restore one path'          'git restore src/foo.ts'
check allow 'restore --staged .'        'git restore --staged .'
check allow 'clean -n'                  'git clean -n'
check allow 'clean -fdn'                'git clean -fdn'

# --- branch ---
check deny  'branch -D'                 'git branch -D foo'
check deny  'branch --delete --force'   'git branch --delete --force foo'
check deny  'branch -df'                'git branch -df foo'
check allow 'branch -d'                 'git branch -d foo'
check allow 'branch list'               'git branch -a'
check allow 'branch -D in string'       'git commit -m "hooks: block git branch -D"'

# --- not git at all ---
check allow 'grep for the flag'         'grep -rn "git add -A" .'
check allow 'gitleaks'                  'gitleaks protect --staged'
check deny  'add -A in $(...)'           'x=$(git add -A)'
check deny  'checkout . in $(...)'       'x=$(git checkout .)'
check deny  'clean -f in subshell'       '(git clean -fd)'
check deny  'stash pop in braces'        '{ git stash pop; }'
check deny  'force push in backticks'    'x=`git push -f origin foo`'
check allow 'empty'                     ''
check allow 'echo prose'                'echo "run git push --force later"'

# --- bypasses found on second look ---
check deny  'add ./'                    'git add ./'
check deny  'add quoted .'              "git add -- '.'"
check deny  'add dquoted .'             'git add "."'
check deny  'add quoted star'           "git add '*'"
check deny  'checkout quoted ./'        "git checkout -- './'"
check deny  'stash drop bare'           'git stash drop'
check deny  'stash clear'               'git stash clear'
check deny  'push --delete main'        'git push --delete origin main'
check deny  'push -d main'              'git push -d origin main'
check deny  'push :main'                'git push origin :main'
check deny  'sudo git add -A'           'sudo git add -A'
check deny  'env var prefix'            'GIT_DIR=x git add -A'
check deny  'timeout wrapper'           'timeout 30 git push -f origin foo'
check deny  'full path git'             '/usr/bin/git add -A'
check deny  'after heredoc command'     $'cat <<EOF > x\nhi\nEOF\ngit add -A'
check allow 'push --delete branch'      'git push --delete origin claude/foo'
check allow 'push :branch'              'git push origin :claude/foo'
check allow 'stash drop by ref'         'git stash drop stash@{3}'
check allow 'stash drop by sha'         'git stash drop abc123'

# --- prose that names a footgun is not a footgun ---
check allow 'echo prose unquoted'       'echo git add -A'
check allow 'heredoc body'              $'cat > doc.md <<\'EOF\'\nnever run git add -A\nEOF'
check allow 'heredoc body unquoted tag' $'cat > doc.md <<EOF\n- `git push --force` is bad\nEOF'
check allow 'heredoc with dash'         $'cat <<-EOF\n\tgit stash pop\n\tEOF'
check deny  'footgun before heredoc'    $'git add -A\ncat <<EOF\nx\nEOF'
check deny  'footgun before long heredoc' $'git checkout .\ngit commit -F- <<\'EOF\'\nfix a bug in the thing\nsecond line\nEOF'
check allow 'clean cmd before heredoc'  $'git add foo.sh\ngit commit -F- <<\'EOF\'\nnever git add -A\nEOF'
check allow 'printf prose'              'printf "%s\n" git checkout .'

# --- git reached through another command, escapes, nested shells ---
check deny  'for ... do git add -A'     'for d in a b; do git add -A; done'
check deny  'if ...; then git add -A'   'if true; then git commit -am x; fi'
check deny  'xargs git add -A'          'ls | xargs git add -A'
check deny  'unknown wrapper'           'chronic git push --force origin foo'
check deny  'escaped command word'      '\git add -A'
check deny  'quoted command word'       "'git' add -A"
check deny  'sh -c with footgun'        "sh -c 'git add -A && git commit -m x'"
check deny  'eval with footgun'         'eval "git stash pop"'
check deny  'after a redirection'       'git add -A 2>/dev/null'
check deny  'after &'                   'sleep 1 & git add -A'
check deny  'in a brace group'          '{ git add -A; }'
check deny  'reset --hard structural'   'git reset --hard HEAD~1'
check deny  'reset --hard escaped'      'git re\set --hard'
check deny  'reset --hard wrapped'      'cd x && git -C y reset --hard origin/main'
check allow 'reset --soft'              'git reset --soft HEAD~1'
check deny  'reset --har abbreviated'    'git reset --har HEAD~1'
check allow 'reset --hard mentioned in heredoc' $'cat <<\'EOF\'\nnever run git reset --hard\nEOF'
check deny  'reset --hard after heredoc' $'cat <<EOF\nx\nEOF\ngit reset --hard HEAD~1'
check deny  'add --al abbreviated'       'git add --al'
check deny  'clean --forc abbreviated'   'git clean --forc'
check allow 'clean --forc --dry'         'git clean --forc --dry'
check deny  'branch --del --for'         'git branch --del --for topic'
check allow 'push --force-w lease'       'git push --force-w origin topic'
check deny  'push --force-w to main'     'git push --force-w origin main'
check allow 'prose mid-sentence'        'git commit -m "hooks: block git add -A everywhere"'
check allow 'prose in echo'             'echo "never run git add -A"'
check allow 'comment'                   $'# git add -A is banned\ngit status'
check allow 'apostrophes in prose'      'git commit -m "it'"'"'s done" && echo "don'"'"'t"'
check allow 'add -A in a heredoc'       $'git commit -F- <<EOF\nblock git add -A\nEOF'
check allow 'apt install git'           'sudo apt-get install -y git'
check allow 'git-lfs is not git'        'git-lfs install'

# --- fail closed ---
BARE=$(mktemp -d /tmp/no-git-footguns-bare.XXXXXX)
for tool in sh cat printf dirname; do p=$(command -v $tool) && ln -s "$p" "$BARE/$tool"; done
out=$(jq -n '{tool_name:"Bash",tool_input:{command:"git add -A"}}' | PATH=$BARE sh "$HOOK" 2>&1)
rm -rf "$BARE"
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: no jq/awk on PATH should deny\n  hook output: %s\n' "$out"; fi
out=$(jq -n '{tool_name:"Bash",tool_input:{command:"git add -A"}}' | sh "$HOOK" 2>&1)
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: deny output is not valid JSON\n  hook output: %s\n' "$out"; fi

printf '%d passed, %d failed (awk: %s)\n' "$pass" "$fail" "$(command -v awk)"
[ "$fail" -eq 0 ]
