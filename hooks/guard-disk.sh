#!/bin/sh
# Blocks the commands that overwrite a disk. No coding task has a use for
# any of them; a user who wants one runs it.
#
# Denied outright:
#   - `dd` with of= under /dev (except /dev/null, zero, full, stdout, stderr,
#     tty and /dev/fd/N), however the path is spelled: /dev/../dev/sda too
#   - a redirection or `tee` onto a disk device: /dev/sd*, hd*, vd*, xvd*,
#     nvme*, disk*, rdisk*, mmcblk*, mtdblock*, loop*, md*, dm-*, mapper/*, sr*
# Denied unless every target is the agent's own area (the scratchpad, an
# agent worktree or /tmp, resolved as guard-recursive-delete.sh resolves a target, through
# symlinks too): mkfs and mkfs.* (mke2fs, mkswap, mkdosfs), wipefs and shred.
# An image file in /tmp passes; a device node does not. An unresolvable
# target -- a glob, brace, variable, `..`, a quoted string with whitespace, a
# relative path after a `cd` in the same command -- or no visible target at all
# is denied on sight, with a reason naming what it saw.
#
# Out of scope, by design (an accident guard, not a sandbox): `cp` or `cat`
# straight onto a device by argument, a symlink to a device that dd writes
# through, and what a script or an interpreter one-liner does.
#
# Scanning is shared with
# guard-recursive-delete.sh: lib-shell-words.awk (read its header). This is a GATE, so it
# fails closed: no jq/awk, no library, no resolver, unreadable payload ->
# deny. The hook configuration adds one more layer: if this file is missing or
# crashes, the wrapper there denies.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-disk: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-disk: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-disk: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-disk: $LIB missing, cannot inspect the command"

payload=$(cat) || deny 'guard-disk: unreadable hook payload'
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-disk: unreadable hook payload'
[ -n "$cmd" ] || exit 0

cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
case $cwd in
  /*) : ;;
  *) cwd=$PWD ;;
esac
case $HOME in
  /*) : ;;
  *) deny 'guard-disk: $HOME is not an absolute path, cannot resolve targets' ;;
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

# awk parses and normalises; it prints either one "DENY<tab>reason" line, or
# one "T<tab>abs<tab>what<tab>raw" line per mkfs/wipefs/shred target for the
# allowlist check below. abs never holds a tab (a control character in a
# target is denied).
out=$(printf '%s\n' "$cmd" | awk -v cwd="$cwd" -v home="$HOME" "$(cat "$LIB")"'
function fail(r) { print "DENY\t" r; exit }
function refuse(what, why) {
  fail("`" what "` is blocked: " why ". Work on an image file in /tmp or the scratchpad instead; a real disk is the user'\''s to write, so hand them the exact command.")
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
# normalize, with `..` applied as text.
function lexical(p,   n, parts, i, m, stack, out) {
  n = split(p, parts, "/"); m = 0
  for (i = 1; i <= n; i++) {
    if (parts[i] == "" || parts[i] == ".") continue
    if (parts[i] == "..") { if (m) m--; continue }
    stack[++m] = parts[i]
  }
  out = ""
  for (i = 1; i <= m; i++) out = out "/" stack[i]
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

# A cd (or env -C, sudo -D) in a..b that may leave the working directory under /dev, or whose
# target the hook cannot resolve.
function lands_dev(a, b,   g, i, j, x, p) {
  g = cmd_index(w, k, a, b, "^(cd|pushd|popd)$", 1, "")
  if (g) {
    j = 0
    for (i = g + 1; i <= b; i++) if (!(k[i] == "w" && w[i] ~ /^(-P|-L|-e|-@|--)$/)) { j = i; break }
    if (!j) return (w[g] != "cd")
    x = w[j]
    if (k[j] == "q" || x == "-" || x ~ /[$`*?\[{}]/ || x ~ /^~[^\/]/) return 1
    if (x == "~" || x ~ /^~\//) x = home substr(x, 2)
    p = lexical(x ~ /^\// ? x : cwd "/" x)
    if (p == "/dev" || p ~ /^\/dev\//) return 1
  }
  return chdirw(a, b)
}
# A written path is a disk device as the filesystem would see it: `..`, `.` and `//` applied.
function isdev(r, what) {
  if (r !~ /^\// && devmoved) refuse(what " " r, "a `cd` earlier in this command may move the working directory into /dev and the hook cannot follow it; use an absolute path")
  return lexical(r ~ /^\// ? r : cwd "/" r) ~ devre
}

# One target: refuse anything not resolvable to a single path, else print the
# normalised absolute path for the allowlist check in sh.
function target(idx, what,   t) {
  if (k[idx] == "q") refuse(what " " w[idx], "a quoted string with whitespace in it is not one path this hook can resolve")
  t = w[idx]
  if (t ~ /[*?\[{}]/) refuse(what " " t, "a glob or brace expansion could name anything")
  if (t ~ /[$`]/)     refuse(what " " t, "a variable or command substitution could expand to anything")
  if (t ~ /[\t\n\r]/)  refuse(what " " t, "it contains a tab or newline")
  if (t == ".." || t ~ /(^|\/)\.\.(\/|$)/) refuse(what " " t, "a `..` segment steps out of the directory the name suggests")
  if (t ~ /~/) {
    if (t == "~") t = home
    else if (t ~ /^~\//) t = home substr(t, 2)
    else refuse(what " " t, "only a leading `~/` is understood")
  }
  if (t !~ /^\//) {
    if (moved) refuse(what " " t, "a `cd` earlier in this command moves the working directory and the hook cannot follow it; use an absolute path")
    t = cwd "/" t
  }
  tl = tl "T\t" normalize(t) "\t" what "\t" w[idx] "\n"   # printed only if nothing is refused later
}

# operands(g, b, optsre, numeric): the words after the command at g that are
# neither options nor an option'\''s value, into ops[1..nops]; numeric drops a
# bare block count.
function operands(g, b, optsre, numeric,   i, x, dashdash) {
  nops = 0; dashdash = 0
  for (i = g + 1; i <= b; i++) {
    x = w[i]
    if (k[i] != "w") { ops[++nops] = i; continue }
    if (!dashdash && x == "--") { dashdash = 1; continue }
    if (!dashdash && length(x) > 1 && x ~ /^-/) { if (x ~ optsre) i++; continue }
    if (numeric && x ~ /^[0-9]+[A-Za-z]?$/) continue
    ops[++nops] = i
  }
}

# redirs(t, rt): the words an unquoted >, >>, &> or >| in t writes to, quotes
# removed; a dup like 2>&1 has none. Returns the count.
function redirs(t, rt,   i, L, c, j, d, word, nr) {
  delete rt; nr = 0; L = length(t); i = 1
  while (i <= L) {
    c = substr(t, i, 1)
    if (c == "\\") { i += 2; continue }
    if (c == "\047") { j = index(substr(t, i + 1), "\047"); i = j ? i + j + 1 : L + 1; continue }
    if (c == "\"") {
      for (i++; i <= L && substr(t, i, 1) != "\""; i += (substr(t, i, 1) == "\\" ? 2 : 1)) ;
      i++; continue
    }
    if (c == "#" && (i == 1 || index(" \t\n;|&()", substr(t, i - 1, 1)))) { j = index(substr(t, i), "\n"); i = j ? i + j - 1 : L + 1; continue }
    if (c == ">") {
      i++
      while (i <= L && index(">|", substr(t, i, 1))) i++
      if (i <= L && substr(t, i, 1) == "&") { i++; if (i <= L && index("0123456789-", substr(t, i, 1))) continue }
      while (i <= L && index(" \t", substr(t, i, 1))) i++
      word = ""
      while (i <= L) {
        d = substr(t, i, 1)
        if (index(" \t\n;|&()<>", d)) break
        if (d == "\\") { word = word substr(t, i + 1, 1); i += 2 }
        else if (d == "\047" || d == "\"") { j = index(substr(t, i + 1), d); if (!j) j = L - i + 1; word = word substr(t, i + 1, j - 1); i += j + 1 }
        else { word = word d; i++ }
      }
      if (word != "") rt[++nr] = word
      continue
    }
    i++
  }
  return nr
}

function segment(a, b, nested,   g, i, x, v, p, what) {
  g = cmd_index(w, k, a, b, "(^|/)dd$", nested, "")
  if (g) {
    for (i = g + 1; i <= b; i++) {
      x = w[i]
      if (k[i] == "q" && index(q[i], "of=")) refuse("dd", "a quoted string with whitespace in it is not one path this hook can resolve")
      if (k[i] != "w" || x !~ /^of=/) continue
      v = substr(x, 4)
      if (v !~ /^\// && devmoved) refuse("dd " x, "a `cd` earlier in this command may move the working directory into /dev and the hook cannot follow it; use an absolute path")
      if (v ~ /[*?\[{}$`]/) refuse("dd " x, "a glob, brace or variable could name a disk device")
      p = lexical(v ~ /^\// ? v : cwd "/" v)
      if ((p == "/dev" || p ~ /^\/dev\//) && !(p in devok) && p !~ /^\/dev\/fd\//) refuse("dd " x, p " is a device node, and dd overwrites whatever is on it")
    }
  }
  g = cmd_index(w, k, a, b, "(^|/)(mkfs([.][A-Za-z0-9]+)?|mke2fs|mkswap|mkdosfs)$", nested, "")
  if (g) {
    what = w[g]; sub(/.*\//, "", what)
    operands(g, b, "^(-t|-L|-U|-b|-i|-I|-N|-m|-E|-O|-d|-r|-T|-C|-g|-G|--type)$", 1)
    if (!nops) refuse(what, "no device or image file is visible to this hook")
    for (i = 1; i <= nops; i++) target(ops[i], what)
  }
  g = cmd_index(w, k, a, b, "(^|/)(wipefs|shred)$", nested, "")
  if (g) {
    what = w[g]; sub(/.*\//, "", what)
    operands(g, b, "^(-t|-o|-n|-s|--types|--offset|--iterations|--size|--random-source)$", 0)
    if (!nops) refuse(what, "no target is visible to this hook -- xargs and quoted lists look like this. Run it on the resolved paths directly")
    for (i = 1; i <= nops; i++) target(ops[i], what)
  }
  g = cmd_index(w, k, a, b, "(^|/)tee$", nested, "")
  if (g) for (i = g + 1; i <= b; i++) if (k[i] == "w" && isdev(w[i], "tee")) refuse("tee " w[i], "it writes onto a disk device")
}

BEGIN {
  devre = "^/dev/(sd|hd|vd|xvd|nvme|disk|rdisk|mmcblk|mtdblock|loop|md|dm-|mapper/|sr|mem|kmem|port|ram|nbd|zram)"
  split("/dev/null /dev/zero /dev/full /dev/stdout /dev/stderr /dev/tty", ok, " ")
  for (i in ok) devok[ok[i]] = 1
}
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  nt = texts_of(buf, texts, nested)
  # Any cd anywhere makes every relative target in the command unresolvable.
  moved = 0; devmoved = 0
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) {
        if (cmd_index(w, k, a, i - 1, "^(cd|pushd|popd)$", 1, "") || chdirw(a, i - 1)) moved = 1
        if (lands_dev(a, i - 1)) devmoved = 1
      }
      a = i + 1
    }
  }
  for (x = 1; x <= nt; x++) {
    nr = redirs(texts[x], rt)
    for (j = 1; j <= nr; j++) if (isdev(rt[j], ">")) refuse("> " rt[j], "it writes onto a disk device")
    n = scan(texts[x], w, k, q)
    a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a < i) segment(a, i - 1, nested[x])
      a = i + 1
    }
  }
  printf "%s", tl
}') || deny 'guard-disk: awk failed, cannot inspect the command'

[ -n "$out" ] || exit 0
tab=$(printf '\t')
case $out in
  "DENY$tab"*) deny "guard-disk: $(printf '%s\n' "$out" | head -n 1 | cut -f 2-)" ;;
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
  is_under "$1" /tmp "$scratch" "$worktrees" "$tmp_p" "$scratch_p" "$worktrees_p"
}

way="Work on an image file in /tmp or the scratchpad instead; a real disk is the user's to write, so hand them \
the exact command."
while IFS=$tab read -r tag abs what raw; do
  [ "$tag" = T ] || continue
  if ! allowed "$abs"; then
    case $abs in
      /dev/*) kind="a device node" ;;
      *) kind="outside the scratchpad, /tmp and agent worktrees" ;;
    esac
    deny "guard-disk: \`$what $raw\` is blocked: $abs is $kind. $way"
  fi
  phys=$(physical "$abs") || deny "guard-disk: cannot resolve $abs through the filesystem (no \
readlink -f or realpath here), so \`$what $raw\` is blocked. Install coreutils or ask the user."
  [ "$phys" = "$abs" ] || allowed "$phys" || deny "guard-disk: \`$what $raw\` is blocked: $abs resolves \
through a symlink to $phys, which is not the scratchpad, /tmp or an agent worktree. $way"
done <<EOF
$out
EOF
exit 0
