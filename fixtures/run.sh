#!/usr/bin/env bash
# Runs the scanner and guard contract in fixtures/*.jsonl.
#
#   fixtures/run.sh            check every fixture; exit 1 on any mismatch
#   fixtures/run.sh --table    print the failure-mode table the README quotes
#
# One fixture per line. Three kinds:
#   tokens   {command, tokens}   scan() of the command, one entry per token:
#                                "w:<word>", "q:<raw text of a quoted word
#                                holding whitespace>", ";" (a separator)
#   texts    {command, texts}    texts_of() after strip_heredocs(), as the
#                                hooks call it: "<0|1>:<text>", 1 = nested
#   verdict  {guard, command, cwd, want[, reason_has, gap, table, note]}
#                                the named hooks/<guard>.sh fed the PreToolUse
#                                payload; want is deny, ask or allow. gap marks
#                                a documented known gap: the guard allows,
#                                silently, and that is the contract.
#
# It also checks the wiring in hooks/hooks.json (see below).
# AWK_PATH, as in the guard suites, is a directory whose `awk` is the
# implementation under test.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
LIB="$ROOT/hooks/lib-shell-words.awk"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
FIX="$ROOT/fixtures/scanner.jsonl $ROOT/fixtures/guards.jsonl"

if [ "${1:-}" = "--table" ]; then
  printf '| Command | Verdict | Why |\n|---|---|---|\n'
  jq -r 'select(.kind == "verdict" and .table) |
    "| `\(.command)` | \(if .want == "deny" then "DENY" else .want end) | \(.note)\(if .gap then " (known gap)" else "" end) |"' $FIX
  exit 0
fi

# scan_json <tokens|texts>: stdin is the command; prints a JSON array.
scan_json() {
  awk -v mode="$1" "$(cat "$LIB")"'
function js(s,   i, c, o) {
  o = ""
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "\\") o = o "\\\\"
    else if (c == "\"") o = o "\\\""
    else if (c == "\n") o = o "\\n"
    else if (c == "\t") o = o "\\t"
    else if (c == "\r") o = o "\\r"
    else o = o c
  }
  return "\"" o "\""
}
{ buf = buf (NR > 1 ? "\n" : "") $0 }
END {
  out = ""
  if (mode == "tokens") {
    n = scan(buf, w, k, q)
    for (i = 1; i <= n; i++) {
      v = (k[i] == ";") ? ";" : (k[i] == "q") ? "q:" q[i] : "w:" w[i]
      out = out (i > 1 ? "," : "") js(v)
    }
  } else {
    # exactly what the hooks feed texts_of: the text plus a newline, heredocs stripped
    nt = texts_of(strip_heredocs(buf "\n"), texts, nested)
    for (x = 1; x <= nt; x++) out = out (x > 1 ? "," : "") js(nested[x] ":" texts[x])
  }
  print "[" out "]"
}'
}

pass=0; fail=0
bad() { fail=$((fail + 1)); printf 'FAIL: %s\n' "$1"; shift; printf '  %s\n' "$@"; }

while IFS= read -r line; do
  kind=$(jq -r .kind <<<"$line")
  cmd=$(jq -j .command <<<"$line")
  case $kind in
    tokens | texts)
      want=$(jq -c ".$kind" <<<"$line")
      got=$(printf '%s' "$cmd" | scan_json "$kind" 2>&1 | jq -c . 2>&1)
      if [ "$got" = "$want" ]; then pass=$((pass + 1)); else
        bad "$kind of: $cmd" "want: $want" "got:  $got"; fi ;;
    verdict)
      guard=$(jq -r .guard <<<"$line"); want=$(jq -r .want <<<"$line")
      cwd=$(jq -r .cwd <<<"$line"); cwd=${cwd/#\$HOME/$HOME}
      rh=$(jq -r '.reason_has // empty' <<<"$line")
      out=$(jq -n --arg c "$cmd" --arg d "$cwd" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' \
        | timeout 5 sh "$ROOT/hooks/$guard.sh" 2>&1)
      got=$(jq -r '.hookSpecificOutput.permissionDecision // empty' <<<"$out" 2>/dev/null)
      [ -n "$got" ] || got=allow
      reason=$(jq -r '.hookSpecificOutput.permissionDecisionReason // empty' <<<"$out" 2>/dev/null)
      if [ "$got" != "$want" ]; then bad "$guard, want $want, got $got: $cmd" "hook output: $out"
      elif [ -n "$rh" ] && ! grep -qF -- "$rh" <<<"$reason"; then
        bad "$guard denied, but the reason does not name what it saw ($rh): $cmd" "reason: $reason"
      else pass=$((pass + 1)); fi ;;
    *) bad "unknown fixture kind: $kind" ;;
  esac
done < <(cat $FIX)

# Wiring: each command in hooks/hooks.json must fail closed. Run it the way
# Claude Code does, with CLAUDE_PLUGIN_ROOT set, three ways: the script is
# there and judges a payload; the script is missing; the script crashes.
# A plain `sh missing.sh` exits 127, which Claude Code reads as a non-blocking
# error, so both failures have to come out as a deny decision.
HJ="$ROOT/hooks/hooks.json"
CRASH=$(mktemp -d)
mkdir -p "$CRASH/hooks"
printf 'exit 3\n' > "$CRASH/hooks/crash.sh"
decision() { jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null; }
while IFS= read -r c; do
  name=$(sed -n 's|.*/hooks/\([a-z-]*\)\.sh".*|\1|p' <<<"$c" | head -n 1)
  case $name in
    no-git-footguns) cmd='git add -A' ;;
    no-rm-tree) cmd='rm -rf build' ;;
    no-delete-stacked-base) cmd='git push origin --delete "$b"' ;;
    *) bad "wiring: no payload known for $name"; continue ;;
  esac
  payload=$(jq -n --arg c "$cmd" --arg d "$HOME/project" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}')
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT="$ROOT" sh -c "$c" 2>&1 | decision)
  case $got in deny | ask) pass=$((pass + 1)) ;; *) bad "wiring: $name did not judge a payload through hooks.json (got: ${got:-nothing})" ;; esac
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT=/nonexistent sh -c "$c" 2>&1 | decision)
  if [ "$got" = deny ]; then pass=$((pass + 1)); else bad "wiring: $name is fail-open when the script is missing (got: ${got:-nothing})"; fi
  cp "$CRASH/hooks/crash.sh" "$CRASH/hooks/$name.sh"
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT="$CRASH" sh -c "$c" 2>&1 | decision)
  if [ "$got" = deny ]; then pass=$((pass + 1)); else bad "wiring: $name is fail-open when the script crashes (got: ${got:-nothing})"; fi
done < <(jq -r '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[].command' "$HJ")
[ "$(jq '[.hooks.PreToolUse[].hooks[]] | length' "$HJ")" = 3 ] || bad "wiring: hooks.json should wire exactly the three guards"
rm -rf "$CRASH"

printf 'fixtures: %d passed, %d failed (awk: %s)\n' "$pass" "$fail" "$(command -v awk)"
[ "$fail" -eq 0 ]
