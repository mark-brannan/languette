#!/bin/sh
# Blocks a permission sweep -- recursive chown, chgrp and chmod (-R,
# --recursive, or any short cluster containing R), `chmod 777`, and
# `find ... -exec chown|chgrp|chmod` -- unless every target, resolved against
# the payload's cwd and then through the filesystem, is the agent's own.
#
# Allowlist, not a denylist, in the shape of guard-recursive-delete.sh. A target is
# allowed only when it is under the session scratchpad, an agent worktree or
# /tmp, or under an absolute path named in LANGUETTE_PERM_ALLOW. Never `/`,
# $HOME itself, or anything inside a .git, whatever the allow-list says: a
# `chmod -R` there breaks every repository's own store.
#
# What is judged: a recursive chown/chgrp/chmod, a `chmod` whose mode is
# 777 (0777, a+rwx, ugo+rwx), and the start paths of a find that runs one of
# the three with -exec, -execdir, -ok or -okdir. Any other chmod or chown
# (`chmod +x run.sh`, `chown me file`) is not a sweep and passes. A target
# this hook cannot resolve to one allowed path is denied on sight, with a
# reason naming what it saw: a glob, a brace, a shell variable or $(...), a
# `..` segment, a `~` other than a leading one, a quoted string with
# whitespace in it, a relative target after a `cd` in the same command, and a
# recursive command with NO visible target (what `xargs chmod -R` looks like).
# In each the fix is the same: run it on the resolved paths, spelled out.
#
# LANGUETTE_PERM_ALLOW adds absolute paths to the roots, colon-separated; it
# never replaces them. Entries use letters, digits and . _ @ + - only; a path
# may not hold a . or .. segment and may not be / or $HOME. A value that does
# not parse warns on every Bash call and denies only a judged command, naming
# the variable: a typo cannot stop unrelated commands, and cannot open the
# gate.
#
# Out of scope, by design (an accident guard, not a sandbox): flags arriving
# through a variable, `setfacl -R`, `install -m`, a permission change run
# through a program this hook does not know (`find . -exec ./fix.sh {} \;`), and the
# one a script or an interpreter one-liner makes. `xargs chmod 644` with a mode that
# is not 777 and no -R is not seen as a sweep.
#
# Scanning is shared with guard-recursive-delete.sh: lib-shell-words.awk (read its
# header). This is a GATE, so it fails closed: no jq/awk, no library, no
# resolver, unreadable payload -> deny. The hook configuration adds one more
# layer: if this file is missing or crashes, the wrapper there denies.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-permissions: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-permissions: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-permissions: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-permissions: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'guard-permissions: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-permissions: unreadable hook payload'
[ -n "$cmd" ] || exit 0

cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
case $cwd in
  /*) : ;;
  *) cwd=$PWD ;;
esac
case $HOME in
  /*) : ;;
  *) deny 'guard-permissions: $HOME is not an absolute path, cannot resolve targets' ;;
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

# LANGUETTE_PERM_ALLOW, parsed on every call so a malformed value is seen
# whether or not this command is a sweep. Fills extra_roots (as written and as
# the filesystem has them); on a bad value sets allow_err and stops at the
# first bad entry.
extra_roots=; allow_err=
home_p=$(physical "$HOME") || home_p=$HOME
bad_allow() { allow_err=$1; return 1; }
parse_allow() {
  rest=$LANGUETTE_PERM_ALLOW:
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
        ent_p=$(physical "$ent") || ent_p=$ent
        { [ -n "$ent_p" ] && [ "$ent_p" != "$HOME" ] && [ "$ent_p" != "$home_p" ]; } || { bad_allow "'$ent' resolves to / or \$HOME"; return; }
        extra_roots="$extra_roots $ent $ent_p" ;;
      *) bad_allow "'$ent' is not an absolute path"; return ;;
    esac
  done
}
[ -z "${LANGUETTE_PERM_ALLOW:-}" ] || parse_allow
allow_msg=
if [ -n "$allow_err" ]; then
  allow_msg="LANGUETTE_PERM_ALLOW is malformed ($allow_err). Recursive chown, chgrp and chmod, and chmod 777, are \
blocked until it is fixed or unset; other commands run. It must be a colon-separated list of absolute paths \
(/srv/scratch), using only letters, digits and . _ @ + - ; a path may not hold a . or .. segment \
and may not be / or \$HOME."
fi

# awk parses and normalises; it prints either one "DENY<tab>reason" line, or
# one "T<tab>abs<tab>what<tab>raw" line per judged target for the allowlist
# check below. abs never holds a tab (a control character in a target is denied).
out=$(printf '%s\n' "$cmd" | awk -v cwd="$cwd" -v home="$HOME" "$(cat "$LIB")"'
function fail(r) { print "DENY\t" r; exit }
function blocked(raw, why) {
  fail("`" what (raw == "" ? "" : " " raw) "` is blocked: " why ". Spell the files out: chmod or chown the paths " \
       "themselves, without -R (`git ls-files <dir>` lists what a sweep would touch), or sweep inside the " \
       "scratchpad, /tmp or an agent worktree. Anything else is the user'\''s; a sweep over a project tree is " \
       "theirs to run, or to allow with LANGUETTE_PERM_ALLOW.")
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

# A wrapper that runs its command in another directory: env -C dir, sudo -D dir, sudo -R dir (a
# chroot), in every spelling getopt takes: detached, attached (-C/etc), clustered (-nD /etc), a long
# option or any prefix of it. Only the options of the wrapper itself are read, up to the command it runs, so
# the -R of that command is not taken for one; a value-taking option (-u root, --user root) is
# stepped over. An option this does not know errs toward 1, which only denies a relative path.
function chdirw(a, b,   i, j, x, v, n, m, o) {
  for (i = a; i <= b; i++) {
    if (!(k[i] == "w" && w[i] ~ /(^|\/)(sudo|doas|env)$/)) continue
    v = 0
    for (j = i + 1; j <= b; j++) {
      x = w[j]
      if (k[j] != "w") break
      if (x ~ /^-[A-Za-z]*[CDR]/ || x ~ /^--c(h(d(ir?)?|r(o(ot?)?)?)?)?(=.*)?$/) return 1
      if (x ~ /^--./) {
        v = 0
        if (x !~ /=/) {
          n = split("unset split-string close-from group host prompt role type command-timeout user other-user", o, " ")
          for (m = 1; m <= n; m++) if (index(o[m], substr(x, 3)) == 1) v = 1
        }
      } else if (x ~ /^-./) v = (x ~ /[uSghprtTU]$/)
      else if (v || x ~ /^[A-Za-z_][A-Za-z0-9_]*=/) v = 0
      else break
    }
  }
  return 0
}

# One target: refuse anything not resolvable to a single path, else print the
# normalised absolute path for the allowlist check in sh.
function target(idx,   t, n, parts, i) {
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
  n = split(t, parts, "/")
  for (i = 1; i <= n; i++) if (parts[i] == ".git") blocked(w[idx], "it is inside a .git directory, the repository'\''s own store")
  tl = tl "T\t" t "\t" what "\t" w[idx] "\n"       # printed only if nothing is refused later
}

# chown, chgrp or chmod at g (segment ends at b); sweep: a find -exec runs it over a tree.
function perm(g, b, sweep,   name, recursive, ref, dashdash, nops, ops, i, x, mode, world) {
  name = w[g]; sub(/.*\//, "", name)
  recursive = 0; ref = 0; dashdash = 0; nops = 0
  for (i = g + 1; i <= b; i++) {
    x = w[i]
    if (k[i] != "w") { ops[++nops] = i; continue }
    if (!dashdash && x == "--") { dashdash = 1; continue }
    if (!dashdash && x ~ /^--/) {
      # GNU getopt_long takes any unambiguous prefix: --rec is --recursive.
      if (length(x) >= 3 && index("--recursive", x) == 1) recursive = 1
      else if (x == "--reference") { ref = 1; i++ }
      else if (x ~ /^--reference=/) ref = 1
      continue
    }
    if (!dashdash && length(x) > 1 && x ~ /^-/) {
      if (x ~ /^-[A-Za-z0-9]*R[A-Za-z0-9]*$/) recursive = 1
      # chmod'\''s mode may begin with a dash (-x, -w): it is the first operand, not an option.
      if (name == "chmod" && !ref && !nops && x !~ /^-[Rcfv]+$/) ops[++nops] = i
      continue
    }
    ops[++nops] = i
  }
  mode = ""
  if (!ref && nops) {
    mode = w[ops[1]]
    for (i = 1; i < nops; i++) ops[i] = ops[i + 1]
    delete ops[nops]; nops--
  }
  world = (name == "chmod" && mode != "" && mode ~ /^(0*777|a[+=]rwx|ugo[+=]rwx)$/)
  if (!(recursive || world || sweep)) return
  what = recursive ? name " -R" : world ? name " " mode : "find -exec " name
  if (!nops) {
    if (sweep) return
    blocked("", "no target is visible to this hook -- xargs, brace expansion and quoted lists all look like " \
                "this. Run it on the resolved paths directly")
  }
  for (i = 1; i <= nops; i++) target(ops[i])
}

# The chmod, chown or chgrp that the find at g runs with -exec, even behind a wrapper
# (-exec sudo chmod, -exec sh -c '\''chmod ..'\''), else "". Once the command after -exec
# is a wrapper, the rest of the clause is searched.
function exec_perm(g, b,   i, j, m, nm) {
  for (i = g + 1; i < b; i++) {
    if (k[i] != "w" || w[i] !~ /^-(exec|execdir|ok|okdir)$/) continue
    if (k[i + 1] == "w" && w[i + 1] ~ permre) { nm = w[i + 1]; sub(/.*\//, "", nm); return nm }
    nm = w[i + 1]; sub(/.*\//, "", nm)
    if (k[i + 1] != "w" || nm !~ /^(sudo|doas|env|nice|nohup|timeout|command|exec|time|ionice|stdbuf|sh|bash|dash|zsh|ksh)$/) continue
    for (j = i + 1; j <= b; j++) {
      if (k[j] == "w" && w[j] ~ permre) { nm = w[j]; sub(/.*\//, "", nm); return nm }
      if (k[j] == "q" && match(q[j], /(^|[^A-Za-z0-9_.\/-])(chmod|chown|chgrp)([^A-Za-z0-9_-]|$)/)) {
        nm = substr(q[j], RSTART, RLENGTH); sub(/^[^cC]*/, "", nm); sub(/[^a-z]+$/, "", nm); return nm
      }
    }
  }
  return ""
}

function segment(a, b, nested,   g, i, starts, sweep) {
  sweep = 0
  g = cmd_index(w, k, a, b, "(^|/)find$", nested, "")
  if (g) {
    what = exec_perm(g, b)
    if (what != "") {
      sweep = 1; what = "find -exec " what
      starts = 0
      for (i = g + 1; i <= b && w[i] !~ /^[-!]/; i++) { starts++; target(i) }
      if (!starts) blocked("", "with no start path find sweeps the working directory")
    }
  }
  g = cmd_index(w, k, a, b, permre, nested, "")
  if (g) perm(g, b, sweep)
}

BEGIN { homeN = normalize(home); permre = "(^|/)(chown|chgrp|chmod)$" }
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
      if (a < i && (cmd_index(w, k, a, i - 1, "^(cd|pushd|popd)$", 1, "") || chdirw(a, i - 1))) moved = 1
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
  printf "%s", tl
}') || deny 'guard-permissions: awk failed, cannot inspect the command'

# Nothing judged in front of the guard: a malformed LANGUETTE_PERM_ALLOW only
# warns, on every Bash call, and the command runs.
if [ -z "$out" ]; then
  [ -z "$allow_msg" ] || jq -cn --arg m "guard-permissions: $allow_msg" '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$m}}'
  exit 0
fi
# A sweep is being judged: fail closed, before the allowlist is consulted.
[ -z "$allow_msg" ] || deny "guard-permissions: $allow_msg"
tab=$(printf '\t')
case $out in
  "DENY$tab"*) deny "$(printf '%s\n' "$out" | head -n 1 | cut -f 2-)" ;;
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

# The roots as the filesystem has them too: /tmp is /private/tmp on macOS.
tmp_p=$(physical /tmp) || tmp_p=/tmp
scratch_p=$(physical "$scratch") || scratch_p=$scratch
worktrees_p=$(physical "$worktrees") || worktrees_p=$worktrees
allowed() {
  is_under "$1" /tmp "$scratch" "$worktrees" "$tmp_p" "$scratch_p" "$worktrees_p" $extra_roots
}

way="Spell the files out: chmod or chown the paths themselves, without -R (\`git ls-files <dir>\` lists what a \
sweep would touch), or sweep inside the scratchpad, /tmp or an agent worktree. Anything else is the user's; a \
sweep over a project tree is theirs to run, or to allow with LANGUETTE_PERM_ALLOW."
while IFS=$tab read -r tag abs what raw; do
  [ "$tag" = T ] || continue
  allowed "$abs" || deny "\`$what $raw\` is blocked: only the scratchpad, /tmp, agent worktrees and paths named \
in LANGUETTE_PERM_ALLOW may be swept, and $abs is none of those. $way"
  phys=$(physical "$abs") || deny "guard-permissions: cannot resolve $abs through the filesystem (no \
readlink -f or realpath here), so \`$what $raw\` is blocked. Install coreutils or ask the user."
  [ "$phys" = "$abs" ] || allowed "$phys" || deny "\`$what $raw\` is blocked: $abs resolves through a symlink \
to $phys, which is not the scratchpad, /tmp or an agent worktree. $way"
done <<EOF
$out
EOF
exit 0
