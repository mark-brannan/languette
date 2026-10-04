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
# The command can move git before it runs: a `cd`/`pushd`, an exported
# `GIT_DIR`, chained `-C`s (cumulative, as git applies them). Each is
# followed; a `--git-dir` counts when it is $HOME's repo or any repo whose
# work tree is $HOME (yadm keeps its repo elsewhere).
#
# GATE, fails closed: no jq/awk, no library, unreadable payload, or a git
# checkout/switch whose directory can't be resolved (a variable, `cd -`, a
# stale session cwd) -> deny.
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
# A missing $HOME or cwd does not end the check: yadm needs neither, and a
# git command that needs one it can't have is denied below, not waved through.
home=$(cd "$HOME" 2>/dev/null && pwd -P) || home=""
cwd=""
[ -n "$payload_cwd" ] && cwd=$(cd "$payload_cwd" 2>/dev/null && pwd -P)

# True if plain `git` run from directory $1 would actually operate on
# $HOME's worktree -- not "is $1 textually under $HOME", which a nested
# repo (a worktree, any other clone under $HOME) would wrongly trip: git
# stops walking up at the nearest .git, so it never reaches $HOME's from
# inside one of those. Ask git directly what it would resolve to.
git_targets_home() {
  [ "$1" = "$home" ] && return 0
  t=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)
  [ -n "$t" ] && [ "$t" = "$home" ]
}

# True if git dir $1 is $HOME's: the repo git finds from $HOME (a .git
# directory or gitfile), or any repo whose core.worktree is $HOME (yadm's
# repo under ~/.local/share, a bare-repo setup). Either way a checkout
# through it moves the HEAD that $HOME's shells see, whatever --work-tree says.
gitdir_is_home() {
  d=$(cd / && git --git-dir="$1" rev-parse --absolute-git-dir 2>/dev/null) || return 1
  [ -n "$home_gitdir" ] && [ "$d" = "$home_gitdir" ] && return 0
  t=$(cd / && git --git-dir="$1" rev-parse --show-toplevel 2>/dev/null)
  [ -n "$t" ] && [ "$t" = "$home" ]
}
home_gitdir=""
[ -n "$home" ] && home_gitdir=$(git -C "$home" rev-parse --absolute-git-dir 2>/dev/null)

# Resolves a raw -C/--git-dir/--work-tree/GIT_DIR/GIT_WORK_TREE/cd value (as
# it appeared, unquoted by the scanner) against $home and base directory $2,
# the same way the shell would if the literal text were left unquoted.
# Echoes the absolute path, or nothing if it can't be resolved.
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
    *) [ -n "$2" ] || return 0; resolved="$2/$cpath" ;;
  esac
  case "$resolved" in /*) ;; *) return 0 ;; esac
  # A git dir may be a gitfile, which `cd` can't enter: resolve its parent.
  if [ -d "$resolved" ]; then (cd "$resolved" 2>/dev/null && pwd -P)
  elif [ -e "$resolved" ]; then
    pd=$(cd "$(dirname "$resolved")" 2>/dev/null && pwd -P) && printf '%s/%s\n' "$pd" "$(basename "$resolved")"
  fi
}

# awk tokenises with the shared scanner and prints, in command order:
#   "DENY"                -- a yadm checkout/switch: always a hit, decided
#                            here since it needs no path resolution.
#   "CD\t<value>"         -- a cd/pushd/popd. Subshell parentheses don't
#                            survive the scanner, so a cd's reach can't be
#                            bounded: every directory any cd may have left
#                            the shell in stays a candidate for the rest of
#                            the command, alongside the payload cwd.
#   "ENV\t<KIND>\t<value>" -- a GIT_DIR=/GIT_WORK_TREE= outside a git
#                            segment (`export GIT_DIR=~/.git; git ...`):
#                            it applies to every later git segment.
#   "G" ... "E"           -- one git checkout/switch, with its targets in
#                            order between: "C\t<v>" (-C, cumulative, as git
#                            applies them), "GITDIR\t<v>" and
#                            "WORKTREE\t<v>" (flag or inline env).
out=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function segment(a, b, nested,   g, i, sidx, kind, is_yadm, c, v) {
  c = cmd_index(w, k, a, b, "^(cd|pushd|popd)$", nested, "")
  if (c) {
    v = ""
    for (i = c + 1; i <= b; i++) if (k[i] == "w" && (w[i] !~ /^-/ || w[i] == "-")) { v = w[i]; break }
    if (w[c] == "popd") v = "-"
    print "CD\t" v
    return
  }
  g = cmd_index(w, k, a, b, "(^|/)(git|yadm)$", nested, "")
  if (!g) {
    for (i = a; i <= b; i++) {
      if (k[i] != "w") continue
      if (w[i] ~ /^GIT_DIR=/)       print "ENV\tGITDIR\t" substr(w[i], 9)
      if (w[i] ~ /^GIT_WORK_TREE=/) print "ENV\tWORKTREE\t" substr(w[i], 15)
    }
    return
  }
  is_yadm = (w[g] ~ /(^|\/)yadm$/)

  kind = ""
  for (i = g + 1; i <= b; i++) {
    if (k[i] != "w") continue
    if (w[i] == "checkout") { kind = "CO"; sidx = i; break }
    if (w[i] == "switch")   { kind = "SW"; sidx = i; break }
  }
  if (kind == "") return

  # A `--` pathspec separator with a path after it means a file restore
  # (checkout only -- switch has no such form). A bare trailing `--`
  # (`checkout other --`) is still a branch switch.
  if (kind == "CO") {
    for (i = sidx + 1; i < b; i++) if (k[i] == "w" && w[i] == "--" && k[i + 1] == "w") return
  }

  if (is_yadm) { print "DENY"; return }

  print "G"
  for (i = a; i <= b; i++) {
    if (k[i] != "w") continue
    if (w[i] == "-C")               { if (i + 1 <= b && k[i + 1] == "w") print "C\t" w[i + 1]; continue }
    if (w[i] == "--git-dir")        { if (i + 1 <= b && k[i + 1] == "w") print "GITDIR\t" w[i + 1]; continue }
    if (w[i] ~ /^--git-dir=/)       { print "GITDIR\t" substr(w[i], index(w[i], "=") + 1); continue }
    if (w[i] == "--work-tree")      { if (i + 1 <= b && k[i + 1] == "w") print "WORKTREE\t" w[i + 1]; continue }
    if (w[i] ~ /^--work-tree=/)     { print "WORKTREE\t" substr(w[i], index(w[i], "=") + 1); continue }
    if (w[i] ~ /^GIT_DIR=/)         { print "GITDIR\t" substr(w[i], 9); continue }
    if (w[i] ~ /^GIT_WORK_TREE=/)   { print "WORKTREE\t" substr(w[i], 15); continue }
  }
  print "E"
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
nl='
'
tab=$(printf '\t')
# cands: every directory the shell may be in, one per line. lost: some cd
# went somewhere that can't be resolved (a variable, `cd -`, popd).
cands=$cwd lost=0
[ -n "$cwd" ] || lost=1
env_targets=""

# Resolves $1 against every line of $2 into $res, one per line. Sets miss=1
# if any base gave nothing. No subshell, so both reach the caller.
resolve_all() {
  miss=0 res=""
  # shellcheck disable=SC2088
  case "$1" in
    /*|'~'|'~/'*|'$HOME'|'$HOME/'*|'${HOME}'|'${HOME}/'*) set -- "$1" "/" ;;
  esac
  while IFS= read -r base; do
    r=$(resolve_path_arg "$1" "$base")
    if [ -n "$r" ]; then res="$res$r$nl"; else miss=1; fi
  done <<B
$2
B
}

judge() {
  [ -n "$home" ] || deny "no-checkout-home: \$HOME does not resolve, so a git checkout/switch can't be checked against it."
  bases=$cands blind=$lost
  pinned=0
  for line in $env_targets$seg; do
    IFS="$tab" read -r tk tv <<L
$line
L
    case "$tk" in
      C)
        resolve_all "$tv" "$bases"; bases=$res
        [ "$miss" = 0 ] && [ -n "$bases" ] || blind=1
        ;;
      GITDIR|WORKTREE)
        pinned=1
        resolve_all "$tv" "$bases"
        while IFS= read -r r; do
          [ -n "$r" ] || continue
          if [ "$tk" = GITDIR ]; then gitdir_is_home "$r" && deny_generic git
          else [ "$r" = "$home" ] && deny_generic git; fi
        done <<R
$res
R
        ;;
    esac
  done
  # -C, --git-dir or --work-tree pin where the command resolves, so the
  # directories only matter when none of the latter two is present.
  [ "$pinned" = 1 ] && return 0
  [ "$blind" = 0 ] || deny "no-checkout-home: can't tell which directory this git checkout/switch runs in (a cd, -C or session cwd that doesn't resolve), so it can't be checked against \$HOME. Use an absolute path with git -C."
  while IFS= read -r d; do
    [ -n "$d" ] && git_targets_home "$d" && deny_generic git
  done <<D
$bases
D
  return 0
}

seg=""
IFS_SAVE=$IFS
while IFS="$tab" read -r tag f1 f2; do
  case "$tag" in
    DENY) deny_generic yadm ;;
    CD)
      case "$f1" in
        '') cands="$cands$nl$home" ;;
        -) lost=1 ;;
        *)
          resolve_all "$f1" "$cands"
          [ "$miss" = 0 ] && [ -n "$res" ] || lost=1
          cands="$cands$nl$res"
          ;;
      esac
      ;;
    ENV) env_targets="$env_targets$f1$tab$f2$nl" ;;
    G) seg="" ;;
    C|GITDIR|WORKTREE) seg="$seg$tag$tab$f1$nl" ;;
    E) IFS=$nl; judge; IFS=$IFS_SAVE ;;
  esac
done <<EOF
$out
EOF
exit 0
