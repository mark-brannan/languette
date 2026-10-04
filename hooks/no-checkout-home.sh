#!/bin/sh
# Refuses a `git`/`yadm` `checkout`/`switch` that would switch the branch
# checked out in $HOME.
#
# Opt-in: hooks.json runs this only when the plugin option
# `no_checkout_home` is true. For a $HOME that is itself a worktree (a yadm
# or bare-repo setup), a session that checks its branch out there
# leaves it checked out for every shell and session on the machine until
# someone checks the old branch back out. Branch work belongs in a worktree.
# This has no bearing on editing files in $HOME: the guard only fires on a
# `checkout`/`switch` invocation, never on an edit.
#
# `yadm` and `git` are not symmetric. yadm hardcodes `--work-tree=$HOME`
# into every invocation regardless of cwd, so `yadm checkout <branch>` is
# dangerous from ANY directory, including a worktree under $HOME. Any `yadm
# checkout`/`yadm switch` that isn't a file-restore is a hit, cwd ignored.
# Plain `git` only touches $HOME's worktree if the repo it discovers from
# cwd (or a `-C`/`--git-dir`/`--work-tree` target, flag or `GIT_DIR=`/
# `GIT_WORK_TREE=` inline env) actually resolves to $HOME. That is checked
# by asking git (`rev-parse --show-toplevel`), not by testing whether the
# path sits textually under $HOME: a nested repo under $HOME stops git's
# upward search at its own `.git`, so a prefix check would wrongly deny it.
#
# `switch` is covered alongside `checkout` and has no file-restore form, so
# it denies unconditionally. `checkout`'s file-restore forms (`checkout --
# <file>`, `checkout <ref> -- <file>`) stay allowed; `-b`/`-B` counts as a
# branch switch. `checkout .` is denied too (also caught by
# no-git-footguns.sh): it is no pathspec-restore this guard can single out.
#
# Scanning is shared with the other guards: lib-shell-words.awk (read its
# header). Heredoc bodies are dropped; quotes are removed and escapes
# applied; the text is split into segments on shell separators, and the body
# of a quoted string with whitespace (`sh -c '...'`, `eval "..."`) is
# scanned too. `checkout`/`switch` is looked for ANYWHERE after the git/yadm
# command word, and `-C`/`--git-dir`/`--work-tree` anywhere in the segment,
# so an unparsed leading option can never push the subcommand out of reach.
# The cost is a false deny on a bare word "checkout" passed as a value to
# another flag, never a false allow. Quoting inside a path value (`-C
# '$HOME'`, which the shell would NOT expand) isn't distinguished from the
# unquoted form: it only ever adds denials.
#
# GATE, fails closed: no jq/awk, no library, unreadable payload -> deny.
set -u

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

json_str() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk 'BEGIN{ORS="\\n"} {print}' | sed 's/\\n$//; s/^/"/; s/$/"/'; }
deny() { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$(json_str "$1")"; exit 0; }
# $1 is the command that hit: yadm or git, named in the worktree advice.
deny_generic() {
  deny "no-checkout-home: \`checkout\`/\`switch\` in \$HOME switches the branch every shell and session on this machine sees until someone checks the old branch back out. Use a worktree instead:
  $1 worktree add -b <branch> <path> main
then cd into it and work there."
}
command -v jq  >/dev/null 2>&1 || deny "no-checkout-home: jq is missing, so the command can't be inspected."
command -v awk >/dev/null 2>&1 || deny "no-checkout-home: awk is missing, so the command can't be inspected."
[ -r "$LIB" ] || deny "no-checkout-home: $LIB missing, so the command can't be inspected."
payload=$(cat) || deny "no-checkout-home: could not read the hook payload."
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny "no-checkout-home: unreadable hook payload."
[ -n "$cmd" ] || exit 0

payload_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$payload_cwd" ] || exit 0
home=$(cd "$HOME" 2>/dev/null && pwd -P) || exit 0
cwd=$(cd "$payload_cwd" 2>/dev/null && pwd -P) || exit 0

# True if plain `git` run from directory $1 would actually operate on
# $HOME's worktree -- not "is $1 textually under $HOME", which a nested
# repo (a worktree, any other
# clone under $HOME) would wrongly trip: git stops walking up at the
# nearest .git, so it never reaches $HOME's from inside one of those. Ask
# git directly what it would resolve to.
git_targets_home() {
  [ "$1" = "$home" ] && return 0
  t=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)
  [ -n "$t" ] && [ "$t" = "$home" ]
}

# Resolves a raw -C/--git-dir/--work-tree/GIT_DIR/GIT_WORK_TREE value (as it
# appeared, unquoted by the scanner) against $home/$payload_cwd, the same
# way the shell would if the literal text were left unquoted. Echoes the
# resolved absolute path, or nothing if it doesn't exist.
resolve_path_arg() {
  cpath=$1
  # These are case patterns matching a literal leading "~"/"$HOME", not
  # quoted strings -- nothing here expands it.
  # shellcheck disable=SC2088
  case "$cpath" in
    '$HOME'|'${HOME}'|'~') resolved="$home" ;;
    '$HOME'/*) resolved="$home/${cpath#\$HOME/}" ;;
    '${HOME}'/*) resolved="$home/${cpath#\$\{HOME\}/}" ;;
    '~/'*) resolved="$home/${cpath#\~/}" ;;
    /*) resolved="$cpath" ;;
    *) resolved="$payload_cwd/$cpath" ;;
  esac
  (cd "$resolved" 2>/dev/null && pwd -P)
}

# awk tokenises with the shared scanner and prints one line per segment that
# is a real git/yadm checkout/switch and isn't exempted by a `--` pathspec
# separator:
#   "DENY"                    -- a yadm invocation: always a hit, decided
#                                 here since it needs no path resolution.
#   "G\t<KIND>\t<value>"      -- a git invocation: sh resolves KIND (C, a
#                                 `-C` target; WORKTREE/GITDIR, a
#                                 --work-tree/--git-dir or
#                                 GIT_WORK_TREE=/GIT_DIR= value; CWD, the
#                                 payload cwd with no value, emitted only
#                                 when the segment carries none of the
#                                 other three -- a `-C`/`--work-tree`/
#                                 `--git-dir` already pins where the
#                                 command resolves, so the payload cwd is
#                                 irrelevant once one is present) and
#                                 denies if any of them targets $HOME.
out=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function segment(a, b, nested,   g, i, sidx, kind, is_yadm, dashdash, found_target) {
  g = cmd_index(w, k, a, b, "(^|/)(git|yadm)$", nested, "")
  if (!g) return
  is_yadm = (w[g] ~ /(^|\/)yadm$/)

  kind = ""
  for (i = g + 1; i <= b; i++) {
    if (k[i] != "w") continue
    if (w[i] == "checkout") { kind = "CO"; sidx = i; break }
    if (w[i] == "switch")   { kind = "SW"; sidx = i; break }
  }
  if (kind == "") return

  # A bare `--` pathspec separator after the subcommand means a file
  # restore (checkout only -- switch has no such form).
  if (kind == "CO") {
    dashdash = 0
    for (i = sidx + 1; i <= b; i++) if (k[i] == "w" && w[i] == "--") { dashdash = 1; break }
    if (dashdash) return
  }

  if (is_yadm) { print "DENY"; return }

  found_target = 0
  for (i = a; i <= b; i++) {
    if (k[i] != "w") continue
    if (w[i] == "-C") { if (i + 1 <= b && k[i + 1] == "w") { print "G\tC\t" w[i + 1]; found_target = 1 }; continue }
    if (w[i] == "--git-dir")        { if (i + 1 <= b && k[i + 1] == "w") { print "G\tGITDIR\t" w[i + 1]; found_target = 1 }; continue }
    if (w[i] ~ /^--git-dir=/)       { print "G\tGITDIR\t" substr(w[i], index(w[i], "=") + 1); found_target = 1; continue }
    if (w[i] == "--work-tree")      { if (i + 1 <= b && k[i + 1] == "w") { print "G\tWORKTREE\t" w[i + 1]; found_target = 1 }; continue }
    if (w[i] ~ /^--work-tree=/)     { print "G\tWORKTREE\t" substr(w[i], index(w[i], "=") + 1); found_target = 1; continue }
    if (w[i] ~ /^GIT_DIR=/)         { print "G\tGITDIR\t" substr(w[i], index(w[i], "=") + 1); found_target = 1; continue }
    if (w[i] ~ /^GIT_WORK_TREE=/)   { print "G\tWORKTREE\t" substr(w[i], index(w[i], "=") + 1); found_target = 1; continue }
  }
  if (!found_target) print "G\tCWD\t"
}
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  nt = texts_of(buf, texts, nested)
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) segment(a, i - 1, nested[x])
      a = i + 1
    }
  }
}') || deny "no-checkout-home: awk failed, cannot inspect the command"

[ -n "$out" ] || exit 0
tab=$(printf '\t')
while IFS="$tab" read -r tag kind value; do
  case "$tag" in
    DENY) deny_generic yadm ;;
    G)
      case "$kind" in
        CWD) git_targets_home "$cwd" && deny_generic git ;;
        C)
          r=$(resolve_path_arg "$value")
          [ -n "$r" ] && git_targets_home "$r" && deny_generic git
          ;;
        WORKTREE)
          r=$(resolve_path_arg "$value")
          [ -n "$r" ] && [ "$r" = "$home" ] && deny_generic git
          ;;
        GITDIR)
          r=$(resolve_path_arg "$value")
          [ -n "$r" ] && [ "$r" = "$home/.git" ] && deny_generic git
          ;;
      esac
      ;;
  esac
done <<EOF
$out
EOF
exit 0
