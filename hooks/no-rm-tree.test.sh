#!/usr/bin/env bash
# Tests for no-rm-tree.sh. Run: bash hooks/no-rm-tree.test.sh
# Set AWK_PATH to a directory whose `awk` is another implementation (mawk,
# nawk, busybox) to check portability; CI runs it under mawk, gawk and original-awk.
# shellcheck disable=SC2016  # the commands under test contain $(...) on purpose
set -uo pipefail

HOOK="$(cd "$(dirname "$0")" && pwd)/no-rm-tree.sh"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
pass=0; fail=0
unset LANGUETTE_RM_ALLOW   # an ambient value would change every verdict below
CWD_A="$HOME/project"
CWD_B="$HOME/project/sub"

check() {
  local want=$1 desc=$2 cmd=$3 cwd=${4:-$CWD_A} out got
  out=$(jq -n --arg c "$cmd" --arg d "$cwd" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' \
    | timeout 5 sh "$HOOK" 2>&1; [ "${PIPESTATUS[1]}" = 124 ] && echo TIMEOUT)
  if grep -q '"permissionDecision":"deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [ "$got" = "$want" ]; then pass=$((pass + 1)); else
    fail=$((fail + 1)); printf 'FAIL (want %s, got %s): %s\n  cmd: %s\n  cwd: %s\n' "$want" "$got" "$desc" "$cmd" "$cwd"
    [ -n "$out" ] && printf '  hook output: %s\n' "$out"
  fi
}

# --- deny: misc/tracked directories, any recursive flag spelling ---
check deny  'rm -rf examples'                 'rm -rf examples'
check deny  'rm -r ./docs'                    'rm -r ./docs'
check deny  'rm -rf $HOME/foo'                'rm -rf "$HOME/foo"'
check deny  'rm -rf ~/Downloads'              'rm -rf ~/Downloads'
check deny  'rm -rf *'                        'rm -rf *'
check deny  'rm -rf dist/*'                   'rm -rf dist/*'
check deny  'rm -rf dist/../src'              'rm -rf dist/../src'
check deny  'rm -Rf src'                      'rm -Rf src'
check deny  'rm -rf public'                   'rm -rf public'
check deny  'rm -rf $DIR'                     'rm -rf "$DIR"'
check deny  'rm -rf .'                        'rm -rf .'
check deny  'rm -rf ~'                        'rm -rf ~'
check deny  'cd x && rm -rf y'                'cd x && rm -rf y'
check deny  'sudo rm -rf /srv/z'              'sudo rm -rf /srv/z'
check deny  'timeout 5 rm -r a'               'timeout 5 rm -r a'
check deny  'rm -rf node_modules examples'    'rm -rf node_modules examples'
check deny  '--recursive spelled out'         'rm --recursive build'
check deny  '--recursive abbreviated (GNU)'    'rm --rec build'
check deny  '--r abbreviated (GNU)'            'rm --r build'
check allow '--rec on generated'               'rm --rec node_modules'
check deny  'rm -rf .. segment bare'          'rm -rf ..'
check deny  'rm -rf tilde-user'               'rm -rf ~someone/foo'
check deny  'rm -rf repo root via .'          'rm -rf .'                          "$HOME"
check deny  'rm -rf -- examples'              'rm -rf -- examples'
check deny  'rm -r after multiline'           $'echo start\nrm -rf examples'
check deny  'rm -rf $(pwd)/x'                 'rm -rf "$(pwd)/examples"'
check deny  'backtick substitution'           'rm -rf `pwd`/examples'

# --- deny: rm reached through another command ---
check deny  'find -exec rm -rf {} +'          'find ~/precious -mindepth 1 -exec rm -rf {} +'
check deny  'find -exec rm -rf {} \;'         'find . -name x -type d -exec rm -rf {} \;'
check deny  'xargs rm -rf'                    'find ~/precious -type f | xargs rm -rf'
check deny  'for ... do rm -rf'               'for i in 1; do rm -rf ~/precious; done'
check deny  'if ...; then rm -rf'             'if true; then rm -rf examples; fi'
check deny  'time rm -rf'                     'time rm -rf examples'
check deny  'unknown wrapper'                 'chronic rm -rf examples'
check deny  'find -delete'                    'find examples -type f -delete'
check deny  'find -delete no start path'      'find -name "*.log" -delete'
check deny  'rm -rf after &'                  'rm -rf node_modules & rm -rf examples'
check deny  'rm -rf in subshell'              '(cd sub && rm -rf examples)'
check deny  'rm -rf in brace group'           '{ rm -rf examples; }'

# --- deny: quoting and escapes ---
check deny  'quoted path with space'          'rm -rf "/home/user/private dir"'           /tmp
check deny  'quoted path, cwd scratch'        'rm -rf "my dir"'                            "$HOME/.local/state/claude-tmpdir/x"
check deny  'sh -c with rm -rf'               "sh -c 'rm -rf examples'"
check deny  'bash -c with rm -rf'             'bash -c "cd ~/proj && rm -rf examples"'
check deny  'eval with rm -rf'                'eval "rm -rf examples"'
check deny  'xargs sh -c'                     "ls | xargs -I{} sh -c 'rm -rf {}'"
check deny  'escaped command word r\m'        'r\m -rf examples'
check deny  'alias-bypass \rm'                '\rm -rf examples'
check deny  'quoted command word'             "'rm' -rf examples"
check deny  'brace expansion glued'           'rm -rf node_modules{,/../examples}'
check deny  'brace list, no visible target'   'rm -rf {examples,docs}'
check deny  'escaped space in target'         'rm -rf my\ dir'
check deny  'line continuation'               $'rm -rf \\\nexamples'

# --- deny: cwd games ---
check deny  'cd then relative rm, cwd /tmp'   'cd ~/project && rm -rf examples'           /tmp
check deny  'cd then relative rm, cwd scratch' 'cd ~/project; rm -rf examples'            "$HOME/.local/state/claude-tmpdir/x"
check deny  'generated name directly under ~' 'rm -rf ~/dist'
check deny  'generated name under ~, cwd ~'   'rm -rf coverage'                            "$HOME"
check deny  'generated name at /, absolute'   'rm -rf /dist'
check deny  'generated name at /, cwd /'      'rm -rf coverage'                            /

# --- allow: generated dirs, Claude's own areas, non-recursive, non-rm ---
check allow 'rm -rf node_modules'             'rm -rf node_modules'
check allow 'rm -rf dist'                     'rm -rf dist'
check allow 'rm -rf ./dist coverage'          'rm -rf ./dist coverage'
check allow 'rm -rf dist/sub'                 'rm -rf dist/assets'
check allow 'rm -rf -- dist'                  'rm -rf -- dist'
check allow 'generated name nested under /'   'rm -rf dist'                                /opt/proj
check allow 'scratchpad'                      "rm -rf $HOME/.local/state/claude-tmpdir/anything"
check allow '/tmp'                            'rm -rf /tmp/whatever'
check allow 'agent worktree'                  'rm -rf ~/.claude/worktrees/foo'
check allow 'rm foo.txt'                      'rm foo.txt'
check allow 'rm -f a b'                       'rm -f a b'
check allow 'rm "$f" in a loop'               'for f in *.log; do rm "$f"; done'
check allow 'heredoc body'                    $'cat <<EOF\nnever run rm -rf x\nEOF'
check allow 'prose in a commit message'       'git commit -m "hooks: block rm -rf on examples"'
check allow 'prose in a quoted echo'          'echo "do not rm -rf examples"'
check allow 'comment mentioning rm -rf'       $'# rm -rf examples would be bad\nls'
check allow 'git rm -r examples'              'git rm -r examples'
check allow 'yadm rm -r examples'             'yadm rm -r examples'
check allow 'git rm -r --cached'              'git rm -r --cached examples && git commit -m x'
check allow 'docker rm -f'                    'docker rm -f mycontainer'
check allow 'generated dir, deeper cwd'       'rm -rf dist'                       "$CWD_B"
check allow 'absolute worktree, deeper cwd'   "rm -rf $HOME/.claude/worktrees/x"  "$CWD_B"
check allow 'redirection is not a target'     'rm -rf node_modules 2>/dev/null'
check allow 'redirection 2>&1'                'rm -rf node_modules > /dev/null 2>&1'
check allow 'find -exec rm without -r'        'find . -name "*.orig" -exec rm -f {} +'
check allow 'find -delete on generated'       'find dist -name "*.map" -delete'
check allow 'apostrophe in quoted prose'      'echo "it'"'"'s fine" && echo "don'"'"'t rm -rf examples"'
check allow 'cd then absolute generated'      "cd ~/project && rm -rf $HOME/project/node_modules"
check allow 'rm -rf inside /tmp with space'   'rm -rf /tmp/my\ dir'
check allow 'sh -c with allowed target'       "sh -c 'rm -rf node_modules'"
check allow 'grep for the string'             'grep -rn "rm -rf" .'
check allow 'grep for the command'            'grep -rn "rm -rf examples" . && git grep "rm -rf ."'
check allow 'echo prose unquoted'             'echo rm -rf examples'
check allow 'printf prose quoted'             'printf "%s\n" "rm -rf examples" > notes.txt'
check deny  'echo quoted piped to sh'         'echo "rm -rf examples" | sh'
check deny  'echo unquoted piped to bash'     'echo rm -rf examples | bash'
check deny  'python os.system'                'python3 -c "import os; os.system('"'"'rm -rf examples'"'"')"'
check deny  'unknown consumer, command lead'  'mytool --run "rm -rf examples"'

# --- symlinks: the physical path must be allowed too ---
S=$(mktemp -d /tmp/no-rm-tree-test.XXXXXX)
mkdir -p "$S/real"
ln -s "$HOME" "$S/escape"
ln -s "$S/real" "$S/inside"
check deny  'symlink under /tmp into $HOME'   "rm -rf $S/escape/Documents"
check deny  'symlink, trailing slash'         "rm -rf $S/escape/"
check allow 'symlink under /tmp into /tmp'    "rm -rf $S/inside/x"
check allow 'plain dir under /tmp'            "rm -rf $S/real"
check allow 'nonexistent under /tmp'          "rm -rf $S/not/yet/here"
rm -rf "$S"

# --- the denial names what the agent ran ---
# reason WANT DESC CMD NEEDLE [ALLOW]: verdict WANT, and when it denies the
# reason contains NEEDLE. ALLOW, when given, is LANGUETTE_RM_ALLOW (even "").
reason() {
  local want=$1 desc=$2 cmd=$3 needle=$4 out got why
  if [ $# -ge 5 ]; then export LANGUETTE_RM_ALLOW=$5; else unset LANGUETTE_RM_ALLOW; fi
  out=$(jq -n --arg c "$cmd" --arg d "$CWD_A" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' | timeout 5 sh "$HOOK" 2>&1)
  unset LANGUETTE_RM_ALLOW
  why=$(jq -r '.hookSpecificOutput.permissionDecisionReason // empty' <<<"$out" 2>/dev/null)
  if grep -q '"permissionDecision":"deny"' <<<"$out"; then got=deny; else got=allow; fi
  if [ "$got" != "$want" ]; then
    fail=$((fail + 1)); printf 'FAIL (want %s, got %s): %s\n  cmd: %s\n  hook output: %s\n' "$want" "$got" "$desc" "$cmd" "$out"
  elif [ -n "$needle" ] && [ "$got" = deny ] && ! grep -qF -- "$needle" <<<"$why"; then
    fail=$((fail + 1)); printf 'FAIL: %s\n  reason lacks "%s": %s\n' "$desc" "$needle" "$why"
  else pass=$((pass + 1)); fi
}
reason deny  'find -delete names find, not rm -r'   'find build -delete'               '`find build -delete` is blocked'
reason deny  'find -delete, no start path'          'find -name "*.log" -delete'       '`find -delete` is blocked'
reason deny  'find -delete, glob start path'        'find b* -delete'                  '`find b* -delete` is blocked'
reason deny  'find -delete under $HOME names find'  'find ~/Downloads -delete'         '`find ~/Downloads -delete` is blocked'
reason deny  'rm -r still names rm -r'              'rm -rf build'                     '`rm -r build` is blocked'
reason deny  'find -exec rm -rf still names rm -r'  'find . -exec rm -rf {} +'         '`rm -r` is blocked'

# --- LANGUETTE_RM_ALLOW: adds to the built-in lists, never replaces them ---
reason deny  'unset: a custom name is denied'       'rm -rf proj/build'                'is none of those'
reason deny  'empty is unset'                       'rm -rf proj/build'                'is none of those' ''
reason allow 'name added'                           'rm -rf proj/build'                ''  build
reason allow 'name added, deeper'                   'rm -rf proj/build/sub'            ''  build
reason allow 'name added, find -delete'             'find proj/build -delete'          ''  build
reason allow 'one of several names'                 'rm -rf proj/.next'                ''  build:.next:out
reason deny  'names not listed stay denied'         'rm -rf proj/examples'             'is none of those' build:.next
reason allow 'built-in names survive a value'       'rm -rf proj/node_modules'         ''  build
reason allow 'built-in roots survive a value'       "rm -rf $HOME/.claude/worktrees/x" ''  build
reason deny  'added name is not a direct child of $HOME' "rm -rf $HOME/build"         'is none of those' build
reason allow 'absolute path added as a root'        'rm -rf /srv/agent-area/x'         ''  /srv/agent-area
reason allow 'absolute path, trailing slash'        'rm -rf /srv/agent-area/x'         ''  /srv/agent-area/
reason deny  'outside the added root'               'rm -rf /srv/other/x'              'is none of those' /srv/agent-area
reason deny  'sibling sharing a prefix'             'rm -rf /srv/agent-area2/x'        'is none of those' /srv/agent-area

# --- LANGUETTE_RM_ALLOW: garbage denies, naming the variable ---
for bad in 'build:' ':build' 'a::b' ':' 'a b' 'dist*' '$X' 'a/b' 'rel/path' '.' '..' '/' '//' "$HOME" "$HOME/" \
           '/srv/../etc' '/srv/./x' '/srv//x' 'a;b' '"x"'; do
  reason deny  "garbage [$bad]"                     'rm -rf /tmp/ok'                   'LANGUETTE_RM_ALLOW' "$bad"
done
L=$(mktemp -d /tmp/no-rm-tree-link.XXXXXX); ln -s "$HOME" "$L/home"; ln -s / "$L/root"
reason deny  'symlink to $HOME as a root'          'rm -rf proj/x'                    'LANGUETTE_RM_ALLOW' "$L/home"
reason deny  'symlink to / as a root'              'rm -rf proj/x'                    'LANGUETTE_RM_ALLOW' "$L/root"
rm -rf "$L"
reason allow 'garbage does not touch a command with no recursive rm' 'ls -la'          '' 'a b'
reason allow 'garbage does not touch a single-file rm'               'rm build.log'    '' 'a b'

# --- fail closed ---
# A PATH holding only sh and the coreutils the hook needs: no jq, no awk.
BARE=$(mktemp -d /tmp/no-rm-tree-bare.XXXXXX)
for t in sh cat printf dirname head cut readlink; do p=$(command -v $t) && ln -s "$p" "$BARE/$t"; done
out=$(jq -n '{tool_name:"Bash",tool_input:{command:"rm -rf node_modules"},cwd:"/x"}' | PATH=$BARE sh "$HOOK" 2>&1)
rm -rf "$BARE"
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: no jq/awk on PATH should deny\n  hook output: %s\n' "$out"; fi
out=$(printf 'not json' | sh "$HOOK" 2>&1)
if grep -q '"permissionDecision":"deny"' <<<"$out"; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: unparseable payload should deny\n  hook output: %s\n' "$out"; fi
out=$(jq -n --arg d "$CWD_A" '{tool_name:"Bash",tool_input:{command:"rm -rf examples \"a b\""},cwd:$d}' | sh "$HOOK" 2>&1)
if printf '%s' "$out" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' >/dev/null 2>&1; then pass=$((pass + 1)); else
  fail=$((fail + 1)); printf 'FAIL: deny output is not valid JSON\n  hook output: %s\n' "$out"; fi

printf '%d passed, %d failed (awk: %s)\n' "$pass" "$fail" "$(command -v awk)"
[ "$fail" -eq 0 ]
