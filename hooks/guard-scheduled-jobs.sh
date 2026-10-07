#!/bin/sh
# Blocks `crontab -r`, which deletes the whole crontab with no undo: at
# command position, behind sudo, env, nohup ..., and with r in a short-option
# cluster (`crontab -ir`). Listing it (`-l`) and replacing it from a file pass.
#
# Out of scope, by design (an accident guard, not a sandbox): `crontab` fed an
# empty file, `systemctl disable` of a timer, `atrm`, and what a script or an
# interpreter one-liner does.
#
# Scanning is shared with guard-recursive-delete.sh: lib-shell-words.awk (read
# its header). This is a GATE, so it fails closed: no jq/awk, no library,
# unreadable payload -> deny. The hook configuration adds one more layer: if
# this file is missing or crashes, the wrapper there denies.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-scheduled-jobs: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-scheduled-jobs: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-scheduled-jobs: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-scheduled-jobs: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'guard-scheduled-jobs: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-scheduled-jobs: unreadable hook payload'
[ -n "$cmd" ] || exit 0

# awk prints one deny reason, or nothing.
out=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
{ buf = buf $0 "\n" }
END {
  nt = texts_of(strip_heredocs(buf), texts, nested)
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) {
        g = cmd_index(w, k, a, i - 1, "(^|/)crontab$", nested[x], "")
        if (g) for (j = g + 1; j < i; j++) if (k[j] == "w" && w[j] ~ /^-[A-Za-z]*r[A-Za-z]*$/) {
          print "`crontab -r` is blocked: it deletes the whole crontab with no undo. That is the user'\''s to run, not an agent'\''s: say what you need and hand them the exact command."
          exit
        }
      }
      a = i + 1
    }
  }
}') || deny 'guard-scheduled-jobs: awk failed, cannot inspect the command'

[ -z "$out" ] || deny "guard-scheduled-jobs: $out"
exit 0
