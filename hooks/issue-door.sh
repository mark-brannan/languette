#!/bin/sh
# One GitHub issue create, transfer or delete per human turn; never two in
# one call, never one in a loop. An issue number is an identifier things link
# to where no agent can see, so minting or moving one is a one-way door
# (Solace, 2026-09-30). `issue-door.sh prompt` on UserPromptSubmit opens the
# door; the next identifier write spends it.
#
# Counts as an identifier write: `gh issue create|new|transfer|delete`; `gh
# api` POST to repos/o/r/issues; a graphql createIssue, transferIssue or
# deleteIssue; the MCP create_issue, transfer_issue, delete_issue, and
# issue_write with method create. The command is read with lib-shell-words,
# so `sh -c`, `eval` and `xargs` bodies are seen; a script file is not.
#
# The door file is named apart from the claude plugin's own copy of this
# hook (`claude-issue-door.<session>`) -- the same session_id can run both
# plugins, and if the two shared a name, one plugin's UserPromptSubmit would
# spend the other's door, denying the first identifier write of a turn that
# never got to open it.
#
# GATE, fails closed: no jq, awk or library -> deny any call that mentions
# an issue.
set -uf

LIB="$(dirname "$0")/lib-shell-words.awk"
p=$(cat)
deny() { jq -cn --arg r "issue-door: $1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'; exit 0; }
if ! command -v jq >/dev/null 2>&1 || ! command -v awk >/dev/null 2>&1 || [ ! -r "$LIB" ]; then
  case $p in *[Ii]ssue*) printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"issue-door: jq, awk or lib-shell-words.awk is missing, so this call could not be checked"}}' ;; esac
  exit 0
fi
door="${TMPDIR:-/tmp}/languette-issue-door.$(printf '%s' "$p" | jq -r '.session_id // "none"' | tr -c 'A-Za-z0-9_\n-' _)"
[ "${1:-}" = prompt ] && { : > "$door"; exit 0; }

loop=0
case $(printf '%s' "$p" | jq -r '.tool_name // ""') in
  Bash)
    # W per identifier write; LOOP when one sits in a loop body or after xargs.
    out=$(printf '%s' "$p" | jq -r '.tool_input.command // ""' | awk "$(cat "$LIB")"'
      function wv(i) { return (k[i] == "q") ? q[i] : w[i] }
      function mutations(t,   c) { c = 0; while (match(t, /(create|transfer|delete)Issue[[:space:]]*\(/)) { c++; t = substr(t, RSTART + RLENGTH) } return c }
      { buf = buf $0 "\n" }
      END {
        nb = heredoc_bodies(buf, body)
        for (h = 1; h <= nb; h++) hd = hd body[h] "\n"
        nt = texts_of(strip_heredocs(buf), texts, nested)
        for (x = 1; x <= nt; x++) {
          n = scan(texts[x], w, k, q)
          a0 = 1; depth = 0
          for (i = 1; i <= n + 1; i++) {
            if (i <= n && k[i] != ";") continue
            if (a0 < i) segment(a0, i - 1, nested[x])
            a0 = i + 1
          }
        }
      }
      function emit() { print "W"; if (depth > 0 || rep) print "LOOP" }
      # skip_r(lo, hi): index of the first word at or after lo that is not
      # a flag -- skipping -R/--repo and the value it takes, and any other
      # dash-prefixed flag. `gh issue -R o/r create` and `gh -R o/r issue
      # create` both put -R before the subcommand it names; without this a
      # flag in that position reads as the subcommand and the write is
      # never seen. Or 0 if the segment runs out first.
      function skip_r(lo, hi,   i, t) {
        for (i = lo; i <= hi; i++) {
          t = wv(i)
          if (t == "-R" || t == "--repo") { i++; continue }
          if (t ~ /^-/) continue
          return i
        }
        return 0
      }
      function segment(lo, hi, nested,   g, i, t, path, method, fields, m, sub1, sub2) {
        # A loop word after do/then/else counts too: `do for s in x y` opens one.
        for (i = lo; i <= hi && k[i] == "w"; i++) {
          if (w[i] ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue
          if (w[i] ~ /^(for|while|until|select)$/) { depth++; break }
          if (w[i] !~ /^(do|then|else|elif|!|time|\{|\()$/) break
        }
        if (k[lo] == "w" && w[lo] == "done" && depth > 0) depth--
        rep = 0
        g = cmd_index(w, k, lo, hi, "(^|/)gh$", nested, "")
        if (!g || g + 1 > hi) return
        for (i = lo; i < g; i++) if (k[i] == "w" && w[i] ~ /(^|\/)(xargs|parallel|find)$/) rep = 1
        sub1 = skip_r(g + 1, hi)
        if (!sub1) return
        if (w[sub1] == "issue") {
          sub2 = skip_r(sub1 + 1, hi)
          if (sub2 && w[sub2] ~ /^(create|new|transfer|delete)$/) emit()
          return
        }
        if (w[sub1] != "api") return
        path = ""; method = ""; fields = 0; m = 0
        for (i = sub1 + 1; i <= hi; i++) {
          t = wv(i)
          m += mutations(t)
          if (t == "-X" || t == "--method") { if (i < hi) method = toupper(w[++i]) }
          else if (t ~ /^--method=/) method = toupper(substr(t, 10))
          else if (t ~ /^-X./) method = toupper(substr(t, 3))
          else if (t ~ /^(-f|-F|--field|--raw-field|--input)$/) { fields = 1; if (i < hi) m += mutations(wv(++i)) }
          else if (t ~ /^(-[fF].|--(field|raw-field|input)=)/) fields = 1
          else if (t ~ /^(-H|--header|-q|--jq|-t|--template|-p|--preview|--hostname|--cache)$/) i++
          else if (t !~ /^-/ && path == "") path = t
        }
        sub(/^https?:\/\/[^\/]+\//, "", path); sub(/^\/+/, "", path)
        if (path ~ /^repos\/[^\/]+\/[^\/]+\/issues\/?$/ && (method == "POST" || (method == "" && fields))) emit()
        if (path == "graphql") { m += mutations(hd); hd = ""; while (m-- > 0) emit() }
      }') || deny "awk failed, so this call could not be checked"
    n=$(printf '%s\n' "$out" | grep -c '^W$')
    printf '%s\n' "$out" | grep -q '^LOOP$' && loop=1 ;;
  mcp__*__create_issue|mcp__*__transfer_issue|mcp__*__delete_issue) n=1 ;;
  mcp__*__issue_write) n=$(printf '%s' "$p" | jq -r 'if .tool_input.method == "create" then 1 else 0 end') ;;
  *) n=0 ;;
esac
[ "$n" -gt 0 ] || exit 0
[ "$n" -gt 1 ] && deny "$n issue creates, transfers or deletes in one call. One per human turn, never a batch."
[ "$loop" = 1 ] && deny "an issue create, transfer or delete inside a loop. One per human turn, never a batch."
rm "$door" 2>/dev/null || deny "the door is shut. One issue create, transfer or delete per human turn, and this turn's is spent or the human has not spoken since. Show the human the draft and wait for their yes."
