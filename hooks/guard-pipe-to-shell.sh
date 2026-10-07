#!/bin/sh
# Blocks a download that is run as it arrives: curl, wget or fetch piped into
# an interpreter that reads its program from stdin.
#
# Three shapes, one reason (the script is run before anyone has seen it):
#   1. piped:       curl u | sh   curl u | sudo bash -s   wget -qO- u | python3 -
#                   (a download earlier in the same pipeline, `curl u | tee f | sh`
#                   included -- `curl u; sh` and `curl u && sh f` are not pipes)
#   2. as a file:   sh <(curl u)   source <(curl u)   . <(wget -qO- u)
#   3. as text:     eval "$(curl u)"   eval `curl u`   bash -c "$(curl u)"
#
# Interpreters: sh bash dash zsh ksh ash fish, python (python3, python3.12 ...),
# perl, node, ruby. One that is handed a program of its own is not reading the
# download as code and passes: `curl u | python3 -c ...`, `| python3 -m
# json.tool`, `| node -e ...`, `| perl -pe ...`, `| sh install.sh`, `| bash -c
# cat`. A shell reads stdin as its program with no operand or with -s; python,
# perl, node and ruby with no operand or a lone `-`.
#
# The denial names the safe way: download to a file, read it, run the file.
#
# Out of scope, by design (an accident guard, not a sandbox): a here-string
# (`bash <<< "$(curl u)"`), a download kept in a variable and then run
# (`x=$(curl u); eval "$x"`), a download by another tool (`aria2c`, `http`, a
# python or node one-liner), and a script that does the piping itself.
#
# A quoted string that mentions a pipe-to-shell as text (`git commit -m "..."`,
# `echo '...'`) is prose and passes, unless some segment of the command is a
# shell. Scanning is shared with guard-recursive-delete.sh: lib-shell-words.awk (read its
# header). This is a GATE, so it fails closed: no jq/awk, no library,
# unreadable payload -> deny. The hook configuration adds one more layer: if
# this file is missing or crashes, the wrapper there denies.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-pipe-to-shell: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-pipe-to-shell: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-pipe-to-shell: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-pipe-to-shell: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'guard-pipe-to-shell: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-pipe-to-shell: unreadable hook payload'
[ -n "$cmd" ] || exit 0

# awk prints one "DENY<tab>what" line for the first pipe-to-shell it finds, else nothing.
out=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function base(p) { sub(/.*\//, "", p); return p }
function fam(p,   n) {
  n = base(p)
  if (n ~ /^(sh|bash|dash|zsh|ksh|ash|fish)$/) return "sh"
  if (n ~ /^python/) return "python"
  if (n ~ /^perl/) return "perl"
  return n
}
function valueopt(f, x) {
  if (f == "sh") return x ~ /^(-o|-O|\+o|\+O|--rcfile|--init-file)$/
  if (f == "python") return x ~ /^(-W|-X)$/
  if (f == "perl") return x == "-I"
  if (f == "ruby") return x ~ /^(-I|-r)$/
  return x ~ /^(-r|--require|--import|--loader)$/
}
function dlseg(ww, kk, a, b, nest) { return cmd_index(ww, kk, a, b, "(^|/)(curl|wget|fetch)$", nest, "") }

# program(g, b): how the interpreter at g (segment ends at b) gets its program.
# Sets given (a -c, -e or -m the interpreter runs instead of stdin), nops and
# ops[] (the words that are neither options nor their values).
function program(g, b,   f, i, j, x, letters) {
  f = fam(w[g]); given = 0; nops = 0; delete ops
  letters = (f == "sh") ? "c" : (f == "python") ? "cm" : (f == "perl") ? "eE" : "e"
  for (i = g + 1; i <= b; i++) {
    x = w[i]
    if (k[i] != "w") { ops[++nops] = x; continue }
    if (x == "--") { for (i++; i <= b; i++) ops[++nops] = w[i]; break }
    if (valueopt(f, x)) { i++; continue }
    if (x == "-" || (length(x) > 1 && x ~ /^[-+]/)) {
      if (f == "node") { if (x ~ /^(-e|--eval|-p|--print|-pe|-ep|-c|--check)$/) given = 1 }
      else if (x ~ /^-[A-Za-z]+$/ && !(f == "perl" && substr(x, 2, 1) ~ /[MmIiFd]/))
        for (j = 1; j <= length(letters); j++) if (index(x, substr(letters, j, 1))) given = 1
      continue
    }
    ops[++nops] = x
  }
}
# The interpreter at g takes its program from stdin: no -c/-e/-m and no script
# operand (a lone - is stdin).
function reads_stdin(g, b,   i, sflag) {
  program(g, b)
  if (fam(w[g]) == "sh") {
    sflag = 0
    for (i = g + 1; i <= b; i++) if (w[i] ~ /^-[A-Za-z]*s[A-Za-z]*$/) sflag = 1
    return !given && (sflag || !nops)
  }
  return !given && (!nops || ops[1] == "-")
}
# A quoted word'\''s text runs a download inside a substitution.
function text_dl(raw,   n2, a2, i2) {
  if (!index(raw, "$(") && !index(raw, "`")) return 0
  n2 = scan(raw, w2, k2, q2)
  a2 = 1
  for (i2 = 1; i2 <= n2 + 1; i2++) {
    if (i2 <= n2 && k2[i2] != ";") continue
    if (a2 < i2 && dlseg(w2, k2, a2, i2 - 1, 0)) return 1
    a2 = i2 + 1
  }
  return 0
}

# judge(nest): the scanned text in w/k/q, as the reason it is a pipe-to-shell, or "".
function judge(nest,   n, i, j, a, b, c, g, fed, sep, name, carried, shell0, nseg, sa, segend) {
  n = SW_n; shell0 = SW_shellseg
  delete op; delete qdl; delete segend; nseg = 0
  for (i = 1; i <= n; i++) op[i] = SW_sepc[i]          # text_dl scans again and clobbers SW_*
  for (i = 1; i <= n; i++) if (k[i] == "q") qdl[i] = text_dl(q[i])
  SW_shellseg = shell0
  a = 1
  for (i = 1; i <= n + 1; i++) {
    if (i <= n && k[i] != ";") continue
    if (a < i) { sa[++nseg] = a; segend[a] = i - 1 }
    a = i + 1
  }
  carried = 0
  for (i = 1; i <= nseg; i++) {
    a = sa[i]; b = segend[a]
    sep = (a > 1) ? op[a - 1] : ""
    gsub(/\|\||&&/, "", sep)
    if (sep !~ /\|/) carried = 0
    c = seg_cmd(w, k, a, b)
    g = cmd_index(w, k, a, b, "(^|/)(sh|bash|dash|zsh|ksh|ash|fish|python[0-9.]*|perl[0-9.]*|node|ruby)$", nest, "")
    fed = (b + 1 <= n && op[b + 1] ~ /^[(`]/ && (b + 2) in segend && dlseg(w, k, b + 2, segend[b + 2], nest))
    if (g) {
      name = base(w[g])
      if (carried && reads_stdin(g, b)) return "a download piped into `" name "`"
      program(g, b)
      if (fed && (given || !nops)) return "`" name "` run on a download substituted into its command line"
      if (given) for (j = g + 1; j <= b; j++) if (k[j] == "q" && qdl[j]) return "`" name " -c` run on a download substituted into its command line"
    }
    if (c && w[c] == "eval") {
      if (fed) return "`eval` of a download"
      for (j = c + 1; j <= b; j++) if (k[j] == "q" && qdl[j]) return "`eval` of a download"
    }
    if (c && (w[c] == "source" || w[c] == ".") && fed && b == c) return "`" w[c] "` of a download"
    if (dlseg(w, k, a, b, nest)) carried = 1
  }
  return ""
}

{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  nt = texts_of(buf, texts, nested)
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    why = judge(nested[x])
    if (why != "") { print "DENY\t" why; exit }
  }
}') || deny 'guard-pipe-to-shell: awk failed, cannot inspect the command'

tab=$(printf '\t')
case $out in
  "DENY$tab"*)
    why=$(printf '%s\n' "$out" | head -n 1 | cut -f 2-)
    deny "guard-pipe-to-shell: $why runs whatever the server sends, unread. Download it to a file, read it, then run the file: \`curl -fsSLo install.sh <url>\`, read install.sh, \`sh install.sh\`. The same install, one more command, and the script has been seen before it ran." ;;
esac
exit 0
