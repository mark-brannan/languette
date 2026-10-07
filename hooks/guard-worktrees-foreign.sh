#!/bin/sh
# Refuses to let a session reach into a git worktree that is not its own.
#
# The scar (2026-09): a session was handed nothing but "continue
# <issue> see <PR>". It found the branch already checked out in a sibling
# worktree, decided that working there with `git -C <that path>` was the
# clean move, and did. When the session that actually owned that worktree
# was archived -- correctly, by its own git state -- the directory went
# away underneath the second session mid-turn. It survived only because its
# commit happened to already be pushed.
#
# The mistake was not the pickup skill and not the archival check. It was
# treating another session's working directory as a place to work. A
# hand-off carries a branch, an issue and a PR; it does not carry a
# directory. Everything a leaving session wants handed over is on the
# remote -- if it isn't pushed, it isn't handed over, and reaching into
# their worktree to get it is racing a process that is still running.
#
# So: any path inside a linked worktree other than this session's own is
# refused, in any command, read or write. The alternatives are all local:
#
#   inspect a branch      git log/diff/show <branch>, git show <branch>:<path>
#                         -- every worktree of a repo shares its objects and
#                         refs, so nothing about another branch requires
#                         standing in another directory.
#   work on a branch      your own worktree under the scratchpad (one
#                         command, any repo, survives a subagent's cwd
#                         reset; recipe() prints it), or EnterWorktree(name=...)
#                         in this repo, then `git merge
#                         --ff-only <branch>` inside it -- this hook's
#                         recovery text used to say `git checkout <branch>`,
#                         but the auto-mode classifier denies that outright
#                         as irreversible local destruction even on a clean
#                         tree (dotfiles#233). If `--ff-only` fails, the
#                         histories have diverged: report it and stop,
#                         rather than falling back to checkout.
#   worktree hygiene      the user's, not a session's.
#
# `EnterWorktree(path=...)` is refused outright: the tool enters an existing
# worktree with no ownership check of any kind (verified in its own
# documentation -- the only requirement is that the path appear in `git
# worktree list`), and every legitimate use of it is reachable via
# `EnterWorktree(name=...)` plus a fast-forward merge.
#
# What counts as foreign: git is asked, nothing is assumed from the path.
# A candidate resolves to a toplevel (`rev-parse --show-toplevel`) that
#   - differs from this session's own toplevel, and
#   - is a LINKED worktree -- its `.git` is a file, not a directory.
# The second test is what keeps `~/dotfiles`, `$HOME` (yadm's own worktree)
# and every other clone allowed: those are main worktrees, shared by every
# session on the machine and no session's private space. Sibling worktrees
# of the current repo sit *inside* the repo root by path
# (`<repo>/.claude/worktrees/<name>`), so a textual "is it under my
# toplevel" shortcut would wrongly allow exactly the case this exists for.
# There is no shortcut here for that reason: every candidate path gets asked.
#
# One exception, measured not assumed (2026-09-30, 187 denials over 584
# sessions, 25 of them this case): a worktree the session created itself
# under its own scratchpad directory. It is linked, and its toplevel is not
# the session's cwd toplevel, so the two tests above call it foreign -- but
# nobody else can own a directory that lives under
# `.../claude-tmpdir/claude-<uid>/<project>/<session-id>/...`. So a linked
# worktree whose canonical toplevel has a whole path component equal to the
# payload's `session_id` is this session's own, wherever the scratchpad
# lives (`$TMPDIR` when Claude Code has pointed it there, the state dir
# otherwise). No session id in the payload means nothing newly allowed; a
# bare `/tmp` never qualifies because no component of it is a session id.
#
# "This session's own" is sticky (dotfiles#455). The cwd's toplevel alone
# was the answer through #166, and it moves: one `cd` into the state repo
# and the session's own linked worktree was foreign, the `cd` back denied,
# its uncommitted work stranded. So each session (and each subagent, keyed
# on the payload's `agent_id`) keeps a record of its own linked toplevels in
# `${TMPDIR:-/tmp}/languette-guard-worktrees.<session>[.<agent>]`, a
# per-session file. It is named apart from the claude plugin's own copy of
# this hook (`claude-no-foreign-worktree.*`): the arrival a call leaves is
# consumed exactly once, so with one shared file whichever copy ran first
# would spend it and the other would deny the session's new worktree.
# Own is the cwd's toplevel now plus every recorded one. A toplevel is
# recorded only when the session reaches it by a route this hook vouches for:
#   - the first call of the session: wherever it starts is its own;
#   - the call after EnterWorktree(name=...), which makes a fresh worktree;
#   - a `cd` this hook allowed into a path that did not exist yet when it
#     was checked (`git worktree add X && cd X`): nobody else's worktree can
#     be at a path that was not there.
# A cwd reached any other way (`cd "$VAR"`, which cannot be resolved) is own
# while the shell stands in it, as before, and never recorded -- so an
# unchecked route cannot be laundered into a lasting allow. Each record line
# carries the inode of the worktree's `.git` file, so a worktree removed and
# re-created at the same path by someone else is not inherited. A record
# not owned by this user, or a symlink, is ignored (a shared /tmp); any
# failure to read or write it leaves the rule exactly as strict as the cwd
# alone. No session id in the payload: no record, no change.
#
# A `cd` target is checked whatever its spelling: a one-component `cd
# <name>` from the worktrees directory used to pass unseen, and a chain of
# them reached any sibling. Within one command the scanner follows `cd`, so
# words after it resolve against where the shell will be, and against the
# payload cwd too (a subshell's `cd` does not outlive it; checking both is
# the over-approximation). The word after `-C` is a path whatever its
# spelling, for the same reason (`git -C <name>`).
#
# Known gap, deliberate: the shared scanner drops redirections, so
# `cmd > /other/worktree/file` is not seen. Words are seen, redirection
# targets are not. Closing it means reimplementing redirection tracking for
# one exotic spelling; the ordinary routes (a cd, a `-C`, an Edit, a
# `sed -i`, a `cp`) are all words.
#
# Prose is not a command: a path mentioned inside a quoted string that holds
# whitespace stays one unresolvable word, and the scanner only queues such a
# string for a nested scan when its segment could execute it -- so a commit
# message, an issue body or a card that names a worktree path passes.
#
# Scanning is shared with guard-git-work-loss.sh/guard-worktrees-checkout-home.sh/
# guard-recursive-delete.sh: lib-shell-words.awk (read its header).
#
# This is a GATE, so it fails closed: no jq, no awk, no sed, no git, no
# library, unreadable payload -> deny.
set -u

# Parameter expansion, not `dirname`: this hook must still emit valid JSON
# when PATH is broken, and that is when an external tool is least available.
HERE=${0%/*}
[ "$HERE" = "$0" ] && HERE=.
LIB="$HERE/lib-shell-words.awk"
# Asking git costs two processes per candidate path; a command with hundreds
# of path-shaped words is pathological, not a use case. Cap and move on.
MAX_CANDIDATES=48

# jq escapes every control character a path can carry, so the reason is
# always valid JSON; deny runs only after the jq check below.
deny() { jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'; exit 0; }
# The reasons that fire when a tool this hook needs is missing cannot go
# through jq, which is what may be missing.
# printf is a shell builtin, so this one always emits valid JSON. Keep the
# message free of double quotes, backslashes and newlines.
deny_literal() { printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-worktrees: %s This is a gate and fails closed."}}\n' "$1"; exit 0; }

# recipe <dir> -- one command giving this session its own worktree of <dir>'s
# repo under its scratchpad (own by the session-id rule, any repo, survives a
# subagent's cwd reset). `--git-dir=`, not `-C`: yadm's $HOME has no `-C`
# directory, only `~/.local/share/yadm/repo.git`. Placeholders when unknown.
recipe() {
  gitdir='<git-dir>'; scratch='<scratchpad>'
  gcd=$(git -C "$1" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  [ -n "$gcd" ] && gitdir=$gcd
  if [ -n "${session_id:-}" ]; then
    for d in "${CLAUDE_CODE_TMPDIR:-/nonexistent}"/claude-*/*/"$session_id"/scratchpad \
             "${TMPDIR:-/nonexistent}"/claude-*/*/"$session_id"/scratchpad \
             "$HOME"/.local/state/claude-tmpdir/claude-*/*/"$session_id"/scratchpad; do
      [ -d "$d" ] && { scratch=$d; break; }
    done
  fi
  printf 'git --git-dir=%s worktree add %s/<name> && cd %s/<name>' "$gitdir" "$scratch" "$scratch"
}

# claim-stamp.sh, optional: `$CLAIM_STAMP_BIN` when set, else a
# `claim-stamp.sh` on PATH, else none. With none, every foreign worktree gets
# the "unknown" message below, which is the strict one: the rule itself never
# depends on it. Tests point it at a stub instead of shelling out to gh
# against a fixture repo with no real remote.
CLAIM_STAMP_BIN=${CLAIM_STAMP_BIN:-$(command -v claim-stamp.sh 2>/dev/null)}

# Same preconditions claim-stamp.sh's own usable() checks (dotfiles#287) --
# kept separate rather than sourced, because the only thing this hook needs
# from claim-stamp.sh is its `read` output, and duplicating four cheap
# `command -v`/env checks costs less than trusting a silent, unversioned
# convention to keep agreeing with a file this script does not source.
usable_claim() {
  [ -z "${GITHUB_ACTIONS:-}" ] || return 1
  [ -z "${CI:-}" ] || return 1
  [ "${CLAUDE_CLAIM_STAMP:-on}" != off ] || return 1
  [ -n "$CLAIM_STAMP_BIN" ] && [ -x "$CLAIM_STAMP_BIN" ] || return 1
  command -v gh >/dev/null 2>&1 || return 1
  return 0
}

# claim_read <foreign-worktree-root> -- sets claim_state to one of live,
# stale, unknown, and claim_live to the first live stamp line (tab-separated:
# state, session, machine, age, card url) when the state is live.
#
# "live" -- claim-stamp.sh read (dotfiles#307) shows a fresh stamp from some
# session on the branch's card: another session is genuinely working there.
# "stale" -- the card was found and every stamp on it is stale: a session
# claimed this worktree and then died without releasing it.
# "unknown" -- everything else: claim-stamp.sh could not be asked (no gh,
# CI, the switch is off), answered "no card" or "unverified", or printed
# nothing. Nothing is deliberately not stale: claim-stamp.sh's read prints
# nothing both for a card with no stamp and for a gh call that failed, and
# a session on a machine without gh leaves no stamp at all. A false "stale"
# here is exactly how an agent once lost a worktree (the scar above): this hook would be
# recommending the destructive step instead of merely failing to prevent
# it. One read, not two: the state and the line it is reported from must
# come from the same answer.
claim_read() {
  claim_state=unknown; claim_live=""
  usable_claim || return 0
  out=$(sh "$CLAIM_STAMP_BIN" read -C "$1" 2>/dev/null) || return 0
  case "$out" in ''|'no card'|unverified*) return 0 ;; esac
  claim_live=$(printf '%s\n' "$out" | awk -F'\t' '$1 == "live" { print; exit }')
  if [ -n "$claim_live" ]; then claim_state=live
  elif printf '%s\n' "$out" | awk -F'\t' '$1 == "stale" { f = 1 } END { exit !f }'; then claim_state=stale
  fi
}

deny_path() {
  word=$1; ft=$2
  branch=$(git -C "$ft" symbolic-ref -q --short HEAD 2>/dev/null)
  claim_state=unknown; claim_live=""
  [ -n "$branch" ] && claim_read "$ft"

  case "$claim_state" in
    live)
      who=$(printf '%s' "$claim_live" | awk -F'\t' '{ printf "session `%s` on `%s`, claimed %s ago", $2, $3, $4 }')
      deny "guard-worktrees: \`$word\` is inside $ft, a git worktree this session does not own. ${who:+$who -- }another session is live in there (claim-stamp.sh); it may be archived out from under you mid-turn if you reach in (an agent once lost a worktree that way).
To read that branch, stay here: \`git log/diff/show $branch\`, \`git show $branch:<path>\` -- worktrees of a repo share objects and refs.
Report it and stop. Do not take the worktree away from them."
      ;;
    stale)
      deny "guard-worktrees: \`$word\` is inside $ft, a git worktree this session does not own. claim-stamp.sh finds no live claim on \`$branch\` -- the session that held this worktree looks dead, not merely between turns.
That does not make it yours to clear: reaching in and archiving it out from under an owner who turns out to still be there is how an agent once lost a worktree. Report this to the user with the cleanup command: \`git worktree remove $ft\` (run from a worktree other than this one) -- git itself refuses if anything uncommitted is left inside, and the branch survives the removal either way, so nothing is lost if the stale read was wrong.
To read that branch meanwhile, stay here: \`git log/diff/show $branch\`, \`git show $branch:<path>\`."
      ;;
    *)
      deny "guard-worktrees: \`$word\` is inside $ft, a git worktree this session does not own. A hand-off carries a branch, an issue and a PR -- never a directory; another session may still be running in there, and it may be archived out from under you mid-turn (an agent once lost a worktree that way).
To read that branch, stay here: \`git log/diff/show <branch>\`, \`git show <branch>:<path>\` -- worktrees of a repo share objects and refs.
To work on it, take your own worktree, one command, from anywhere: \`$(recipe "$ft")\`, then \`git merge --ff-only ${branch:-<branch>}\` inside it. If --ff-only fails, the histories have diverged: report that and stop.
If you made this worktree yourself in an earlier call, that is why: a worktree is yours only when the command that creates it also \`cd\`s into it, or it lives under your scratchpad. The recipe above does both.
Worktree hygiene is the user's call, not a session's."
      ;;
  esac
}

command -v jq  >/dev/null 2>&1 || deny_literal 'jq is missing, so the command cannot be inspected.'
command -v awk >/dev/null 2>&1 || deny_literal 'awk is missing, so the command cannot be inspected.'
command -v sed >/dev/null 2>&1 || deny_literal 'sed is missing, so the command cannot be inspected.'
command -v git >/dev/null 2>&1 || deny_literal 'git is missing, so worktree ownership cannot be checked.'
[ -r "$LIB" ] || deny_literal 'lib-shell-words.awk is missing from the hooks directory, so the command cannot be inspected. Reinstall the plugin and retry.'
payload=$(cat) || deny_literal 'the hook payload could not be read.'
tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null) || deny_literal 'the hook payload is unreadable.'

payload_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$payload_cwd" ] || exit 0
home=$(cd "$HOME" 2>/dev/null && pwd -P) || exit 0

# This session's own worktree root. Empty when the cwd is not in a repo at
# all -- then every linked worktree is someone else's, which is the answer
# this hook would give anyway.
own_top=$(git -C "$payload_cwd" rev-parse --show-toplevel 2>/dev/null)

# This session's id, or empty. Empty keeps every rule below exactly as
# strict as before; only a non-empty id allows anything new.
session_id=$(printf '%s' "$payload" | jq -r '.session_id // empty' 2>/dev/null)
agent_id=$(printf '%s' "$payload" | jq -r '.agent_id // empty' 2>/dev/null)

# The per-session record of own linked toplevels (see the header), or empty
# when there is no session id to key it on.
rec=""
if [ -n "$session_id" ]; then
  tag=$(printf '%s' "$session_id" | tr -c 'A-Za-z0-9_-' '_')
  [ -n "$agent_id" ] && tag="$tag.$(printf '%s' "$agent_id" | tr -c 'A-Za-z0-9_-' '_')"
  [ -n "$tag" ] && rec="${TMPDIR:-/tmp}/languette-guard-worktrees.$tag"
fi

# mine <file> -- a regular file owned by this user, not a symlink. Anything
# else in a shared TMPDIR could have been planted, and is ignored.
mine() { [ -f "$1" ] && [ ! -L "$1" ] && [ -O "$1" ]; }

# inode_of <toplevel> -- the inode of a linked worktree's `.git` file.
inode_of() { ls -di "$1/.git" 2>/dev/null | awk '{ print $1; exit }'; }

# recorded_own <canonical toplevel> -- succeeds when the record names it,
# with the inode it has now.
recorded_own() {
  [ -n "$rec" ] && mine "$rec" || return 1
  ino=$(inode_of "$1")
  [ -n "$ino" ] || return 1
  grep -qxF "$1	$ino" "$rec" 2>/dev/null
}

# write_new <file> <text> -- create the file afresh, private, refusing to
# follow a link someone else left at that name. Failure is silent: the
# record only ever widens what is allowed, so not writing it is the strict
# outcome.
write_new() {
  rm -f "$1" 2>/dev/null
  { [ -e "$1" ] || [ -L "$1" ]; } && return 0
  (set -C; umask 077; printf '%s\n' "$2" > "$1") 2>/dev/null
}

# under_own_scratch <canonical-dir> -- succeeds when some whole path
# component of the directory equals this session's id. Whole component
# only: an id that is merely a substring of a directory name is not that
# session's directory.
under_own_scratch() {
  [ -n "$session_id" ] || return 1
  case "/$1/" in */"$session_id"/*) return 0 ;; esac
  return 1
}

# This call's cwd toplevel, recorded when it was reached by a vouched route.
# Runs on every call, before any decision, so the arrival a previous call
# left is consumed exactly once.
own_linked=""
[ -n "$own_top" ] && [ -f "$own_top/.git" ] && own_linked=1
if [ -n "$rec" ]; then
  adopt=""
  if [ ! -e "$rec" ] && [ ! -L "$rec" ]; then
    # noclobber: two first calls racing must not truncate each other.
    (set -C; umask 077; : > "$rec") 2>/dev/null && adopt=1
  fi
  if ! mine "$rec"; then
    rec=""
  else
    if [ -z "$adopt" ] && [ -n "$own_linked" ] && mine "$rec.arrive"; then
      while IFS= read -r a; do
        case "$a" in
          enter) adopt=1 ;;
          ?*) case "$a/" in "$own_top"/*) adopt=1 ;; esac ;;
        esac
      done < "$rec.arrive"
    fi
    rm -f "$rec.arrive" 2>/dev/null
    if [ -n "$adopt" ] && [ -n "$own_linked" ] && ! under_own_scratch "$own_top" \
       && ! recorded_own "$own_top"; then
      ino=$(inode_of "$own_top")
      [ -n "$ino" ] && printf '%s\t%s\n' "$own_top" "$ino" >> "$rec" 2>/dev/null
    fi
  fi
fi

# EnterWorktree with a `path` is refused whatever the path: the tool does no
# ownership check, and `name` plus a fast-forward merge covers every honest
# use.
case "$tool" in
  EnterWorktree)
    p=$(printf '%s' "$payload" | jq -r '.tool_input.path // empty' 2>/dev/null)
    if [ -z "$p" ]; then
      # A fresh worktree of the session's own making: the next call's cwd
      # toplevel is recorded as own.
      [ -n "$rec" ] && write_new "$rec.arrive" enter
      exit 0
    fi
    deny "guard-worktrees: EnterWorktree(path=...) enters a worktree that already exists, with no check on whose it is -- the tool only requires that the path appear in \`git worktree list\`. That is how an agent once lost a worktree mid-turn: the session that owned it was archived and the directory went away underneath the session that had attached to it.
Take your own instead, one command, from anywhere: \`$(recipe "$p")\`, then \`git merge --ff-only <branch>\` inside it to bring the branch you are resuming into your own directory. If --ff-only fails, the histories have diverged: report that and stop.
Nothing needs the other directory -- worktrees of a repo share objects and refs, so \`git log/diff/show <branch>\` and \`git show <branch>:<path>\` read it from here."
    ;;
esac

# resolve_dir <raw word> <base dir> -- resolves one raw word against
# $home/<base> the way the shell would if the literal text were left
# unquoted, then walks up to its nearest existing directory (a write to a
# file that does not exist yet still names the worktree it would land in).
# Sets rd_dir to that canonical directory, or empty, and rd_rest to the
# part that did not exist yet (empty when the whole path exists).
resolve_dir() {
  raw=$1; rd_dir=""; rd_rest=""
  # These case patterns match a literal leading "~"/"$HOME" -- nothing here
  # expands one.
  # shellcheck disable=SC2088
  case "$raw" in
    '$HOME'|'${HOME}'|'~') r="$home" ;;
    '$HOME'/*) r="$home/${raw#\$HOME/}" ;;
    '${HOME}'/*) r="$home/${raw#\$\{HOME\}/}" ;;
    '~/'*) r="$home/${raw#\~/}" ;;
    /*) r="$raw" ;;
    *) [ -n "$2" ] || return 0; r="$2/$raw" ;;
  esac
  # An unexpandable word ($VAR, a brace expansion, a glob) can't be judged;
  # the walk up would land on a real ancestor and answer about the wrong
  # path, so refuse to resolve it at all.
  case "$r" in *'$'*|*'*'*|*'?'*|*'{'*) return 0 ;; esac
  while [ -n "$r" ] && [ "$r" != "/" ] && [ ! -d "$r" ]; do
    case "$r" in
      */*) rd_rest="${r##*/}${rd_rest:+/$rd_rest}"; r=${r%/*}; [ -n "$r" ] || r=/ ;;
      *) return 0 ;;
    esac
  done
  [ -d "$r" ] || return 0
  # A `..` after a directory that does not exist: the shell's cd drops
  # `nope/..` lexically and lands wherever the rest says, which the walk up
  # cannot see. Unresolvable, so denied.
  case "/$rd_rest/" in
    */../*) deny "guard-worktrees: \`$raw\` has a \`..\` after a directory that does not exist, so where it lands cannot be resolved. Spell the path without \`..\`." ;;
  esac
  rd_dir=$(cd "$r" 2>/dev/null && pwd -P)
}

# Prints the foreign worktree root a directory belongs to, or nothing.
foreign_top() {
  t=$(git -C "$1" rev-parse --show-toplevel 2>/dev/null)
  [ -n "$t" ] || return 0
  [ "$t" = "$own_top" ] && return 0
  # A linked worktree keeps a `.git` FILE pointing at its admin dir; a main
  # worktree (a clone, $HOME under yadm) keeps a directory. Only the former
  # is a session's private space.
  [ -f "$t/.git" ] || return 0
  # A linked worktree under this session's own scratchpad is this session's
  # (see the header). git's toplevel is already canonical.
  under_own_scratch "$t" && return 0
  # A linked worktree this session recorded as its own (see the header).
  recorded_own "$t" && return 0
  printf '%s' "$t"
}

# check_word <raw word> [<base dir>] -- deny when the word lands in a
# foreign worktree, resolved against the base (default: the payload cwd).
# Leaves rd_dir/rd_rest from the resolution for the caller.
check_word() {
  resolve_dir "$1" "${2-$payload_cwd}"
  [ -n "$rd_dir" ] || return 0
  ft=$(foreign_top "$rd_dir")
  [ -n "$ft" ] && deny_path "$1" "$ft"
}

case "$tool" in
  Edit|Write|MultiEdit|NotebookEdit)
    fp=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)
    [ -n "$fp" ] || exit 0
    check_word "$fp"
    exit 0
    ;;
  Bash) ;;
  *) exit 0 ;;
esac

cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -n "$cmd" ] || exit 0

# awk prints the command's path-shaped words, one per line, tagged:
#   T          a new text begins (the top level, or a quoted string the
#              scanner judges executable -- a `sh -c` body); its shell starts
#              in the payload cwd
#   C<TAB>w    the target of a `cd`/`pushd` in command position, whatever its
#              spelling (`~` for a bare `cd`)
#   W<TAB>w    any other word holding a "/", `~`/`$HOME` on its own, or the
#              word after `-C`; a leading `--flag=` or `VAR=` is stripped so
#              `--work-tree=<path>` and `GIT_WORK_TREE=<path>` are seen
# Every position counts, not just command position: the target of the move
# this hook exists to stop is always an argument (`cd <path>`, `git -C
# <path>`, `sed -i <path>`).
words=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function pathish(t) {
  sub(/^--?[A-Za-z0-9][A-Za-z0-9-]*=/, "", t)
  sub(/^[A-Za-z_][A-Za-z0-9_]*=/, "", t)
  if (t == "~" || t == "$HOME" || t == "${HOME}") return t
  return (index(t, "/") ? t : "")
}
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  nt = texts_of(buf, texts, nested)
  for (x = 1; x <= nt; x++) {
    n = scan(texts[x], w, k, q)
    print "T"
    ncd = 0; a = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      # Segment a..i-1. Past assignments and keywords to the command word.
      c = a
      while (c < i && k[c] == "w" && (w[c] ~ /^[A-Za-z_][A-Za-z0-9_]*=/ || w[c] ~ /^(builtin|command|if|then|else|elif|while|until|do|!)$/)) c++
      cdt = 0
      if (c < i && k[c] == "w" && w[c] ~ /^(cd|pushd)$/) {
        cdt = -1
        for (j = c + 1; j < i; j++) {
          if (k[j] == "w" && (w[j] == "--" || w[j] ~ /^-[A-Za-z@]+$/)) continue
          cdt = j; break
        }
        if (cdt == -1) { print "C\t~"; ncd++ }
      }
      for (j = a; j < i; j++) {
        # A quoted target is "$Q": unresolvable, which is what it should be.
        if (j == cdt) { print "C\t" w[j]; ncd++; continue }
        if (k[j] != "w") continue
        t = (j > a && k[j - 1] == "w" && w[j - 1] == "-C") ? w[j] : pathish(w[j])
        if (t == "" || (x SUBSEP ncd SUBSEP t) in seen) continue
        seen[x, ncd, t] = 1
        print "W\t" t
      }
      a = i + 1
    }
  }
}') || deny "guard-worktrees: awk failed, cannot inspect the command"

[ -n "$words" ] || exit 0

# vcwd is where the shell will stand when the word runs: the payload cwd at
# the start of each text, moved by every `cd`; empty once a `cd` target
# cannot be resolved. A relative word is checked against it and against the
# payload cwd. A `cd` into a path that does not exist yet is an arrival the
# next call may record (see the header).
TAB=$(printf '\t')
arrivals=""
vcwd=$payload_cwd
seen_count=0
while IFS= read -r line; do
  case "$line" in
    T) vcwd=$payload_cwd; continue ;;
    "C$TAB"*) kind=C; word=${line#C"$TAB"} ;;
    "W$TAB"*) kind=W; word=${line#W"$TAB"} ;;
    *) continue ;;
  esac
  [ -n "$word" ] || continue
  seen_count=$((seen_count + 1))
  [ "$seen_count" -gt "$MAX_CANDIDATES" ] && break
  if [ -n "$vcwd" ] && [ "$vcwd" != "$payload_cwd" ]; then
    check_word "$word" "$vcwd"
    cd_dir=$rd_dir; cd_rest=$rd_rest
    check_word "$word" "$payload_cwd"
  else
    check_word "$word" "$payload_cwd"
    cd_dir=$rd_dir; cd_rest=$rd_rest
  fi
  [ "$kind" = C ] || continue
  if [ -z "$cd_dir" ]; then
    vcwd=""
  elif [ -n "$cd_rest" ]; then
    vcwd="$cd_dir/$cd_rest"
    arrivals="$arrivals$vcwd
"
  else
    vcwd=$cd_dir
  fi
done <<EOF
$words
EOF

# Allowed. Leave this command's arrivals for the next call to consume.
[ -n "$rec" ] && [ -n "$arrivals" ] && write_new "$rec.arrive" "${arrivals%?}"
exit 0
