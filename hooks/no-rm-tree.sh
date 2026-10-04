#!/bin/sh
# Blocks recursive `rm` (-r, -R, --recursive, or any short cluster containing
# r/R: -rf, -fr, -rfv, -Rf) and `find ... -delete` unless every target,
# resolved against the payload's cwd and then through the filesystem, is
# Claude's to remove.
#
# The scar: an agent ran `rm -rf examples` to sweep the untracked leftovers
# of a refactor and destroyed captures and a watch log the user was using
# as an ongoing download area. `git rm --cached` had already handled the
# tracked files; the `rm -rf` existed only to sweep the rest, and the rest
# was the user's.
#
# Allowlist, not a denylist. A target is allowed only when it is:
#   1. under the session scratchpad, an agent worktree, or /tmp -- these are
#      Claude's areas, nothing of the user's lives there;
#   2. a directory named in GENERATED_NAMES below (its final path component,
#      or an ancestor component -- so `dist` and `dist/sub` both pass), and
#      not a direct child of $HOME or of the filesystem root: ~/proj/dist and
#      /opt/proj/dist are build output, ~/dist and /dist are directories that
#      happen to share the name.
# Everything else is denied: any other directory under $HOME (a misc
# directory in the home tree is the user's by default, whatever it holds), any
# repo's tracked or working directories, `public/` included -- one project's
# generated `public/` is another's tracked source, so the name stays off the
# list.
#
# Both the path as written and the path as the filesystem resolves it must be
# allowed: `rm -rf /tmp/x/` where /tmp/x is a symlink into a repo empties the
# repo directory (rm follows a trailing slash), so the physical path is
# checked too. Resolution needs `readlink -f` or `realpath`; without either
# the hook denies rather than guess.
#
# A target this hook cannot resolve to one allowed path is not allowed, and
# is denied on sight with a reason naming what it saw: a glob (*, ?, [), a
# brace ({}), a shell variable or $(...) or `...`, a `..` segment, a `~`
# other than a leading one, a quoted string with whitespace in it, a
# control character, a target that resolves to / or $HOME, a relative
# target after a `cd` anywhere in the same command (the hook cannot follow
# the cd), and a recursive rm with NO visible target -- which is what
# `find ... -exec rm -rf {} +`, `xargs rm -rf` and `rm -rf {a,b}` look like
# once the scanner is done with them. In every one of those the fix is the
# same: run `rm -rf` on the resolved paths, spelled out.
#
# `rm` on a single file (no recursive flag) passes -- where the file is
# tracked that is `git rm`'s job, and looking at the target before deleting
# it is the agent's job otherwise. `git rm` and `yadm rm` are untouched -- there rm
# is a subcommand, not the command.
#
# Out of scope, by design (this is an accident guard, not a sandbox): flags
# arriving through a variable (`rm $OPTS x`), `rmdir`, `rsync --delete`,
# deletion from inside python/node one-liners.
#
# Scanning is shared with no-git-footguns.sh: lib-shell-words.awk (read its
# header). Heredoc bodies are dropped; quotes are removed and escapes
# applied, so `r\m`, `\rm` and 'rm' are all rm; redirections vanish; the
# text is split on shell separators, and rm counts as the command wherever
# it stands in a segment (after find -exec, xargs, do, time ...) unless it
# is git's/yadm's subcommand. The body of a quoted string with whitespace
# (`sh -c '...'`, `eval "..."`) is scanned as well, there by command
# position only.
#
# This is a GATE, so it fails closed: no jq/awk, no library, no resolver,
# unreadable payload -> deny. The hook configuration adds one more layer: if
# this file is missing or crashes, the wrapper there denies.
set -uf

# Generated directories -- recursive rm on a target whose final path
# component (or an ancestor component) is one of these is allowed. Adding a
# name is a PR, not a judgment call in a session.
#   node_modules   npm/yarn/pnpm install output, most JS repos
#   dist           tsc/vite/webpack build output
#   coverage       test coverage reports (nyc/jest/vitest)
#   .pio           PlatformIO build cache
GENERATED_NAMES="node_modules dist coverage .pio"

# LANGUETTE_RM_ALLOW adds to the lists -- the names above and the two
# agent-owned roots below -- and never replaces them. Colon-separated; an
# entry is a name (added to GENERATED_NAMES, same rules, including the
# direct-child-of-$HOME exclusion) or an absolute path (added as a root, like
# the scratchpad). Names and paths use letters, digits and . _ @ + - only; a
# path may not hold a . or .. segment and may not be / or $HOME. Unset or
# empty: the built-in lists, exactly. A value that does not parse warns on
# every Bash call (hookSpecificOutput.additionalContext) and denies only a
# recursive rm or find -delete, naming the variable, before the allowlist is
# consulted: a typo cannot stop unrelated commands, and cannot open the gate.

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"no-rm-tree: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'no-rm-tree: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'no-rm-tree: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "no-rm-tree: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'no-rm-tree: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'no-rm-tree: unreadable hook payload'
[ -n "$cmd" ] || exit 0

cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
case $cwd in
  /*) : ;;
  *) cwd=$PWD ;;
esac
case $HOME in
  /*) : ;;
  *) deny 'no-rm-tree: $HOME is not an absolute path, cannot resolve targets' ;;
esac

# physical PATH: the longest existing prefix resolved through symlinks, the
# rest appended as written. Fails when no resolver is available.
physical() {
  ph_p=$1 ph_rest=
  while [ "$ph_p" != / ] && ! [ -e "$ph_p" ] && ! [ -L "$ph_p" ]; do
    ph_rest="/${ph_p##*/}$ph_rest"; ph_p=${ph_p%/*}; [ -n "$ph_p" ] || ph_p=/
  done
  ph_r=$(readlink -f -- "$ph_p" 2>/dev/null) || ph_r=$(realpath -- "$ph_p" 2>/dev/null) || return 1
  [ "$ph_r" = / ] && ph_r=
  printf '%s%s\n' "$ph_r" "$ph_rest"
}

# The optional LANGUETTE_RM_ALLOW, parsed on every call, before the early exit,
# so a malformed value is seen whether or not this command is a recursive rm.
# Fills extra_roots (as written and as the filesystem has them) and appends to
# GENERATED_NAMES; on a value that does not parse it sets allow_err (and stops
# at the first bad entry). What to do about it is decided below: warn and allow
# when no recursive rm or find -delete is in front of the guard, deny when one is.
extra_roots=; allow_err=
home_p=$(physical "$HOME") || home_p=$HOME
bad_allow() { allow_err=$1; return 1; }
parse_allow() {
  rest=$LANGUETTE_RM_ALLOW:
  while [ -n "$rest" ]; do
    ent=${rest%%:*}; rest=${rest#*:}
    case $ent in
      '') bad_allow 'an empty entry'; return ;;
      *[!A-Za-z0-9._@+/-]*) bad_allow "unsupported character in '$ent'"; return ;;
      /*)
        case $ent in
          */.|*/./*|*/..|*/../*|*//*) bad_allow "'$ent' has an empty, . or .. segment"; return ;;
        esac
        ent=${ent%/}
        { [ -n "$ent" ] && [ "$ent" != "$HOME" ]; } || { bad_allow "'$ent' is / or \$HOME"; return; }
        # As the filesystem has it too: a symlink to $HOME or / is still $HOME or /.
        ent_p=$(physical "$ent") || ent_p=$ent
        { [ -n "$ent_p" ] && [ "$ent_p" != "$HOME" ] && [ "$ent_p" != "$home_p" ]; } || { bad_allow "'$ent' resolves to / or \$HOME"; return; }
        extra_roots="$extra_roots $ent $ent_p" ;;
      */*) bad_allow "'$ent' is neither a bare name nor an absolute path"; return ;;
      . | ..) bad_allow "'$ent' is not a name"; return ;;
      *) GENERATED_NAMES="$GENERATED_NAMES $ent" ;;
    esac
  done
}
[ -z "${LANGUETTE_RM_ALLOW:-}" ] || parse_allow
allow_msg=
if [ -n "$allow_err" ]; then
  allow_msg="LANGUETTE_RM_ALLOW is malformed ($allow_err). Recursive rm and find -delete are blocked until it is \
fixed or unset; other commands run. It must be a colon-separated list of directory names (dist) or absolute paths \
(/srv/scratch), using only letters, digits and . _ @ + - ; a path may not hold a . or .. segment \
and may not be / or \$HOME."
fi

# awk parses and normalises; it prints either one "DENY<tab>reason" line, or
# one "T<tab>abs<tab>raw" line per recursive target for the allowlist check
# below. abs never holds a tab (a control character in a target is denied).
out=$(printf '%s\n' "$cmd" | awk -v cwd="$cwd" -v home="$HOME" "$(cat "$LIB")"'
function has(t, ch) { return t ~ ("^-[A-Za-z0-9]*" ch "[A-Za-z0-9]*$") }
function fail(r) { print "DENY\t" r; exit }
# What the agent ran, as the denial should name it: find -delete is not rm -r.
function lab(raw) {
  if (trig == "find") return "find" (raw == "" ? "" : " " raw) " -delete"
  return "rm -r" (raw == "" ? "" : " " raw)
}
function blocked(raw, why) {
  fail("`" lab(raw) "` is blocked: " why \
       ". Resolve the target yourself and spell it out: `rm -rf` on the absolute path of a " \
       "generated directory (node_modules, dist, coverage, .pio ...), the scratchpad, /tmp or an " \
       "agent worktree. Anything else in a repo or under $HOME is the user'\''s -- `git status --short` " \
       "/ `git clean -n` show what is there; `git rm` tracked files by path and hand the rest to the user.")
}

# Collapse "." segments and duplicate slashes. `..` never reaches here.
function normalize(p,   n, parts, i, out) {
  n = split(p, parts, "/")
  out = ""
  for (i = 1; i <= n; i++) {
    if (parts[i] == "" || parts[i] == ".") continue
    out = out "/" parts[i]
  }
  return (out == "") ? "/" : out
}

# One rm target: refuse anything not resolvable to a single path, else print
# the normalised absolute path for the allowlist check in sh.
function target(idx,   t) {
  if (k[idx] == "q") blocked(w[idx], "a quoted string with whitespace in it is not one path this hook can resolve")
  t = w[idx]
  if (t ~ /[*?\[{}]/) blocked(t, "a glob or brace expansion could name anything")
  if (t ~ /[$`]/)     blocked(t, "a variable or command substitution could expand to anything")
  if (t ~ /[\t\n\r]/)  blocked(t, "it contains a tab or newline")
  if (t == ".." || t ~ /(^|\/)\.\.(\/|$)/) blocked(t, "a `..` segment steps out of the directory the name suggests")
  if (t ~ /~/) {
    if (t == "~") t = home
    else if (t ~ /^~\//) t = home substr(t, 2)
    else blocked(t, "only a leading `~/` is understood")
  }
  if (t !~ /^\//) {
    if (moved) blocked(t, "a `cd` earlier in this command moves the working directory and the hook cannot follow it; use an absolute path")
    t = cwd "/" t
  }
  t = normalize(t)
  if (t == "/" || t == homeN) blocked(w[idx], "that is " (t == "/" ? "the root of the filesystem" : "$HOME itself"))
  print "T\t" t "\t" trig "\t" w[idx]
}

function segment(a, b, nested,   g, i, x, recursive, dashdash, ntgt, tgt, starts) {
  # find ... -delete: the start paths are removed recursively.
  g = cmd_index(w, k, a, b, "(^|/)find$", nested, "")
  if (g) {
    for (i = g + 1; i <= b; i++) if (w[i] == "-delete") break
    if (i <= b) {
      starts = 0; trig = "find"
      for (i = g + 1; i <= b && w[i] !~ /^[-!]/; i++) { starts++; target(i) }
      if (!starts) blocked("", "with no start path find deletes under the working directory")
      trig = "rm"
    }
  }
  g = cmd_index(w, k, a, b, "(^|/)rm$", nested, "^(git|yadm|svn|hg|jj|gsutil)$")
  if (!g) return
  recursive = 0; dashdash = 0; ntgt = 0
  for (i = g + 1; i <= b; i++) {
    x = w[i]
    if (!dashdash && x == "--") { dashdash = 1; continue }
    # GNU getopt_long takes any unambiguous prefix: --rec, --r are --recursive.
    if (!dashdash && k[i] == "w" && x ~ /^--/) { if (length(x) >= 3 && index("--recursive", x) == 1) recursive = 1; continue }
    if (!dashdash && k[i] == "w" && x ~ /^-./) { if (has(x, "r") || has(x, "R")) recursive = 1; continue }
    tgt[++ntgt] = i
  }
  if (!recursive) return
  if (!ntgt)
    blocked("", "no target is visible to this hook -- find -exec, xargs, brace expansion and " \
                "quoted lists all look like this. Run rm on the resolved paths directly")
  for (i = 1; i <= ntgt; i++) target(tgt[i])
}

BEGIN { homeN = normalize(home); trig = "rm" }
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  nt = texts_of(buf, texts, nested)
  # Any cd anywhere makes every relative target in the command unresolvable.
  moved = 0
  for (x = 1; x <= nt && !moved; x++) {
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i && cmd_index(w, k, a, i - 1, "^(cd|pushd|popd)$", 1, "")) moved = 1
      a = i + 1
    }
  }
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) segment(a, i - 1, nested[x])
      a = i + 1
    }
  }
}') || deny 'no-rm-tree: awk failed, cannot inspect the command'

# Nothing recursive in front of the guard: a malformed LANGUETTE_RM_ALLOW only
# warns, on every Bash call, and the command runs.
if [ -z "$out" ]; then
  [ -z "$allow_msg" ] || jq -cn --arg m "no-rm-tree: $allow_msg" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
  exit 0
fi
# A recursive rm or find -delete is being judged: fail closed, before the
# allowlist is consulted.
[ -z "$allow_msg" ] || deny "no-rm-tree: $allow_msg"
tab=$(printf '\t')
# The refusal is the awk's last line: targets judged before it come first, so
# the DENY is looked for on every line, not only the first. A target the awk
# refused on sight denies the whole command, whatever allowed targets precede it.
# Pure sh, no process to fail: an empty result must never read as "no refusal".
nl='
'
case $out in
  "DENY$tab"*) reason=${out#DENY"$tab"} ;;
  *"${nl}DENY$tab"*) reason=${out#*"${nl}DENY$tab"} ;;
  *) reason= ;;
esac
case $out in
  "DENY$tab"* | *"${nl}DENY$tab"*) deny "${reason%%"$nl"*}" ;;
esac

# --- allowlist, applied to the path as written and as the filesystem has it

scratch="$HOME/.local/state/claude-tmpdir"
worktrees="$HOME/.claude/worktrees"

# is_under PATH ROOT...: PATH is one of the ROOTs or inside one.
is_under() {
  iu_p=$1; shift
  for iu_r; do case $iu_p in "$iu_r" | "$iu_r"/*) return 0 ;; esac; done
  return 1
}

# is_generated PATH: some component is a GENERATED_NAMES entry, and that
# component is not a direct child of $HOME or of the filesystem root --
# ~/proj/dist and /opt/proj/dist are build output, ~/dist and /dist are a
# directory someone made that happens to share the name. Depth is counted
# from $HOME when the path is under it, from / otherwise -- either way, a
# depth-1 match is a bare top-level directory, never a build tool's output.
is_generated() {
  rest=$1; depth=0
  case $rest in "$HOME"/*) rest=${rest#"$HOME"/} ;; esac
  while [ -n "$rest" ]; do
    seg=${rest%%/*}
    if [ "$rest" = "$seg" ]; then rest=; else rest=${rest#*/}; fi
    [ -n "$seg" ] || continue
    depth=$((depth + 1))
    for g in $GENERATED_NAMES; do
      [ "$seg" = "$g" ] || continue
      [ "$depth" = 1 ] && return 1
      return 0
    done
  done
  return 1
}

# The roots as the filesystem has them too: /tmp is /private/tmp on macOS.
tmp_p=$(physical /tmp) || tmp_p=/tmp
scratch_p=$(physical "$scratch") || scratch_p=$scratch
worktrees_p=$(physical "$worktrees") || worktrees_p=$worktrees
allowed() {
  is_under "$1" /tmp "$scratch" "$worktrees" "$tmp_p" "$scratch_p" "$worktrees_p" $extra_roots || is_generated "$1"
}

while IFS=$tab read -r tag abs kind raw; do
  [ "$tag" = T ] || continue
  case $kind in
    find) what="find $raw -delete" ;;
    *) what="rm -r $raw" ;;
  esac
  allowed "$abs" || deny "\`$what\` is blocked: only the scratchpad, /tmp, agent worktrees and \
the generated directories named in no-rm-tree.sh (node_modules, dist, coverage, .pio ...) may be \
removed recursively, and $abs is none of those. \`git status --short $raw\` and \`git clean -n $raw\` \
show what is there; \`git rm\` tracked files by path, and hand anything untracked to the user -- a \
directory they own can hold downloads and logs no session knows about."
  phys=$(physical "$abs") || deny "no-rm-tree: cannot resolve $abs through the filesystem (no \
readlink -f or realpath here), so \`$what\` is blocked. Install coreutils or ask the user."
  [ "$phys" = "$abs" ] || allowed "$phys" || deny "\`$what\` is blocked: $abs resolves through \
a symlink to $phys, which is not a generated directory, the scratchpad, /tmp or an agent worktree. \
rm follows a trailing slash into the link's target."
done <<EOF
$out
EOF
exit 0
