#!/bin/sh
# Blocks the commands that take the machine down. No coding task has a use
# for any of them; a user who wants one runs it.
#
# Denied outright:
#   - shutdown, reboot, halt, poweroff -- at command position, behind sudo, env,
#     nohup ... and their options, and as the one-word script of `sh -c`
#   - the fork-bomb shape: a function that pipes itself into itself in the
#     background (`:(){ :|:& };:`, under any name)
#
# Out of scope, by design (an accident guard, not a sandbox): `systemctl
# reboot`, `init 6`, a power command behind a wrapper option that takes a
# value (`sudo -u root reboot`), and what a script or an interpreter one-liner
# does.
#
# The fork-bomb pattern reads raw text, so a quoted string that mentions it
# (`git commit -m "..."`, `echo '...'`) passes: it is read only in a text that
# has a segment not led by a prose consumer. Scanning is shared with
# guard-recursive-delete.sh: lib-shell-words.awk (read its header). This is a
# GATE, so it fails closed: no jq/awk, no library, unreadable payload -> deny.
# The hook configuration adds one more layer: if this file is missing or
# crashes, the wrapper there denies.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-host-availability: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-host-availability: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-host-availability: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-host-availability: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'guard-host-availability: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-host-availability: unreadable hook payload'
[ -n "$cmd" ] || exit 0

# awk prints one deny reason, or nothing.
out=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function refuse(what, why) {
  print "`" what "` is blocked: " why ". That is the user'\''s to run, not an agent'\''s: say what you need and hand them the exact command."
  exit
}

# A function that pipes itself into itself in the background: name(){ name|name&
function forkbomb(t,   s, n1, n2, n3, r) {
  while (match(t, /[A-Za-z_:][A-Za-z0-9_:]*[ \t\n]*[(][ \t\n]*[)][ \t\n]*[{][ \t\n]*[A-Za-z_:][A-Za-z0-9_:]*[ \t\n]*[|][ \t\n]*[A-Za-z_:][A-Za-z0-9_:]*[ \t\n]*&/)) {
    s = substr(t, RSTART, RLENGTH)
    n1 = s; sub(/[ \t\n]*[(].*/, "", n1)
    r = s; sub(/^[^{]*[{][ \t\n]*/, "", r)
    n2 = r; sub(/[ \t\n]*[|].*/, "", n2)
    n3 = r; sub(/^[^|]*[|][ \t\n]*/, "", n3); sub(/[ \t\n]*&.*/, "", n3)
    if (n1 == n2 && n1 == n3) return 1
    t = substr(t, RSTART + 1)
  }
  return 0
}

function segment(a, b,   g, i, what) {
  g = cmd_index(w, k, a, b, "(^|/)(shutdown|reboot|halt|poweroff)$", 1, "")
  if (!g) for (i = a + 1; i <= b; i++) if (k[i] == "w" && w[i] ~ /(^|\/)(shutdown|reboot|halt|poweroff)$/ && w[i - 1] ~ /^-[A-Za-z]*c$/) { g = i; break }   # `sh -c reboot`
  if (g) { what = w[g]; sub(/.*\//, "", what); refuse(what, "it takes the machine down, with the user'\''s session on it") }
}

{ buf = buf $0 "\n" }
END {
  nt = texts_of(strip_heredocs(buf), texts, nested)
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    a = 1; readraw = 0
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) {
        segment(a, i - 1)
        c = seg_cmd(w, k, a, i - 1)
        if (!c || !sw_prose(w[c]) || SW_shellseg) readraw = 1
      }
      a = i + 1
    }
    # The fork bomb is raw text: read only a text with a segment that is not led by a prose consumer.
    if (readraw && forkbomb(texts[x])) refuse(":(){ :|:& };:", "that is the fork-bomb shape, a function that pipes itself into itself in the background, and it freezes the machine")
  }
}') || deny 'guard-host-availability: awk failed, cannot inspect the command'

[ -z "$out" ] || deny "guard-host-availability: $out"
exit 0
