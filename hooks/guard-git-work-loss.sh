#!/bin/sh
# Blocks the git moves that have bitten users, or sit in the same class as
# ones that have, and that an agent session never has a good reason to make:
#
#   blanket staging   git add -A / --all / . / ./ / -u with no path,
#                     git commit -a  -> where the worktree is $HOME it stages
#                     the home directory; elsewhere it sweeps in a parallel
#                     session's files.
#   stash pop/drop    the stash stack is shared across worktrees, so a pop,
#                     a bare drop or a clear can take another session's
#                     entry. apply/drop by sha pass.
#   force push        bare --force / -f / +refspec anywhere; --force-with-lease
#                     to main or master; deleting main. Rebasing a session
#                     branch is the one legitimate force, and it is
#                     --force-with-lease to that branch.
#   discard           git checkout . / git restore . / git clean -f: throws
#                     away uncommitted work, same as reset --hard.
#   branch -D         throws away unmerged work; -d refuses, use that.
#
# Each rule has its own switch, read here from the environment: the plugin
# options guard_git_work_loss_blanket_staging, _stash, _force_push, _discard and
# _branch_delete (env CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<NAME>). A rule is
# skipped only when its option is exactly `false`. The whole-guard option
# guard_git_work_loss=false is read by hooks.json and skips all five.
#
# `yadm` (a git wrapper for managing dotfiles) is treated as `git`.
#
# Scanning is shared with guard-recursive-delete.sh: lib-shell-words.awk (read its
# header). Heredoc bodies are dropped (a doc that *mentions* `git add -A` is
# not a git command); quotes are removed and escapes applied, so `\git` and
# 'git' are git; redirections vanish; the text is split on shell separators,
# and git/yadm counts as the command wherever it stands in a segment (after
# sudo, env, VAR=x, timeout, xargs, `do`, `then` ...) with git's global
# options skipped. The body of a quoted string with whitespace (`sh -c
# '...'`, `eval "..."`) is scanned as well, there by command position only,
# so a commit message that mentions a flag mid-sentence does not trip it.
#
# This is a GATE, so it fails closed: no jq, no awk, no library, unreadable
# payload -> block. `git reset --hard` is checked structurally here, so an
# escaped or wrapped spelling still stops.
set -uf

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-git-work-loss: jq missing, cannot inspect the command"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'guard-git-work-loss: jq missing, cannot inspect the command'
command -v awk >/dev/null 2>&1 || deny 'guard-git-work-loss: awk missing, cannot inspect the command'
[ -r "$LIB" ] || deny "guard-git-work-loss: $LIB missing, cannot inspect the command"
cmd=$(jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'guard-git-work-loss: unreadable hook payload'
[ -n "$cmd" ] || exit 0

reason=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function has(t, ch) { return t ~ ("^-[A-Za-z0-9]*" ch "[A-Za-z0-9]*$") }
# git takes any unambiguous prefix of a long option: --har is --hard, --al is --all.
function pfx(t, full) { return length(t) >= 3 && index(full, t) == 1 }
function dst(t,  i) { sub(/^\+/, "", t); i = index(t, ":"); if (i) t = substr(t, i + 1); return t }
function ismain(t) { return t ~ /^(refs\/heads\/)?(main|master)$/ }
function whole(t) { return t ~ /^(\.|\.\/|\.\/\*|:\/|:\/\.|\*)$/ }
function fail(r) { print r; exit }
# Per-rule switch: CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_<RULE> exactly "false"
# turns that rule off. Unset, empty or anything else leaves it on.
function off(rule) { return ENVIRON["CLAUDE_PLUGIN_OPTION_GUARD_GIT_WORK_LOSS_" rule] == "false" }
function rule_of(s) {
  if (s == "add" || s == "commit") return "BLANKET_STAGING"
  if (s == "stash") return "STASH"
  if (s == "push") return "FORCE_PUSH"
  if (s == "checkout" || s == "restore" || s == "clean" || s == "reset") return "DISCARD"
  if (s == "branch") return "BRANCH_DELETE"
  return ""
}
{ buf = buf $0 "\n" }
END {
  buf = strip_heredocs(buf)
  ntexts = texts_of(buf, texts, nested)
  for (x = 1; x <= ntexts; x++) {
    n = scan(texts[x], w, k, q)
    a0 = 1
    for (i = 1; i <= n + 1; i++) {
      if (i <= n && k[i] != ";") continue
      if (a0 < i) segment(a0, i - 1, nested[x])
      a0 = i + 1
    }
  }
}
function segment(lo, hi, nested,   r_, g, i, na, sub_, a, paths, upd, op, refs, force, lease, tomain, del, staged, wt, wh, dry) {
    g = cmd_index(w, k, lo, hi, "(^|/)(git|yadm)$", nested, "")
    if (!g) return
    # Skip global options; -C/-c/--git-dir/--work-tree take a value.
    i = g + 1
    while (i <= hi && w[i] ~ /^-/) {
      if (w[i] ~ /^(-C|-c|--git-dir|--work-tree|--namespace)$/) i++
      i++
    }
    if (i > hi) return
    sub_ = w[i]
    r_ = rule_of(sub_)
    if (r_ != "" && off(r_)) return
    na = 0
    for (i++; i <= hi; i++) a[++na] = w[i]

    if (sub_ == "add") {
      paths = 0; upd = 0
      for (i = 1; i <= na; i++) {
        if (a[i] == "-A" || pfx(a[i],"--all") || pfx(a[i],"--no-ignore-removal") || has(a[i], "A"))
          fail("`git add -A` is blocked: stage by path. Where the worktree is $HOME it stages the home directory; " \
               "elsewhere it sweeps in files a parallel session is working on.")
        if (whole(a[i])) fail("`git add " a[i] "` is blocked: stage by path, not the whole tree.")
        if (a[i] == "-u" || pfx(a[i],"--update") || has(a[i], "u")) upd = 1
        else if (a[i] !~ /^-/) paths++
      }
      if (upd && !paths) fail("`git add -u` with no path is blocked: stage by path.")
    }
    else if (sub_ == "commit") {
      for (i = 1; i <= na; i++)
        if (pfx(a[i],"--all") || has(a[i], "a")) fail("`git commit -a` is blocked: it is `git add -u` in disguise. Stage by path, then commit.")
    }
    else if (sub_ == "stash") {
      op = ""; refs = 0
      for (i = 1; i <= na; i++) if (a[i] !~ /^-/) { if (op == "") op = a[i]; else refs++ }
      if (op == "pop")
        fail("`git stash pop` is blocked: the stash stack is shared across worktrees and pop can " \
             "take another session'\''s entry. Use `git stash apply <sha>` and drop the entry afterwards.")
      if (op == "clear") fail("`git stash clear` is blocked: the stash stack is shared across worktrees; it is not all yours to clear.")
      if (op == "drop" && !refs)
        fail("bare `git stash drop` drops stash@{0}, which may be another session'\''s. " \
             "Name the entry: `git stash drop stash@{n}` after finding it by tag.")
    }
    else if (sub_ == "push") {
      force = 0; lease = 0; tomain = 0; del = 0
      for (i = 1; i <= na; i++) {
        if (a[i] ~ /^--force-with-lease=/ || (a[i] ~ /^--force-/ && (pfx(a[i],"--force-with-lease") || pfx(a[i],"--force-if-includes")))) { lease = 1; continue }
        if (pfx(a[i],"--force") || has(a[i], "f")) force = 1
        else if (pfx(a[i],"--delete") || has(a[i], "d")) del = 1
        else if (a[i] ~ /^\+/) force = 1
        else if (a[i] ~ /^:/ && ismain(dst(a[i]))) { del = 1; tomain = 1 }
        else if (a[i] !~ /^-/ && ismain(dst(a[i]))) tomain = 1
      }
      if (force)
        fail("bare `git push --force` is blocked. Rebasing a session branch is the one legitimate " \
             "force: use `--force-with-lease origin <branch>`, never to main.")
      if (tomain && (lease || del)) fail("force-pushing or deleting main is blocked. Main takes rebased branches through a PR.")
    }
    else if (sub_ == "checkout" || sub_ == "restore") {
      staged = 0; wt = 0; wh = ""
      for (i = 1; i <= na; i++) {
        if (a[i] == "-S" || pfx(a[i],"--staged") || has(a[i], "S")) staged = 1
        if (a[i] == "-W" || pfx(a[i],"--worktree") || has(a[i], "W")) wt = 1
        if (whole(a[i])) wh = a[i]
      }
      if (wh != "" && !(sub_ == "restore" && staged && !wt))
        fail("`git " sub_ " " wh "` is blocked: it discards every uncommitted change, same as " \
             "reset --hard. Restore one path at a time, or ask the user.")
    }
    else if (sub_ == "clean") {
      force = 0; dry = 0
      for (i = 1; i <= na; i++) {
        if (pfx(a[i],"--force") || has(a[i], "f")) force = 1
        if (pfx(a[i],"--dry-run") || has(a[i], "n")) dry = 1
      }
      if (force && !dry)
        fail("`git clean -f` is blocked: it deletes untracked files, unrecoverably. " \
             "`git clean -n` to list them, then remove by path.")
    }
    else if (sub_ == "branch") {
      del = 0; force = 0
      for (i = 1; i <= na; i++) {
        if (a[i] == "-D" || has(a[i], "D"))
          fail("`git branch -D` is blocked: it deletes unmerged work. `git branch -d` refuses " \
               "when there is something to lose; if it refuses, that is the answer.")
        if (a[i] == "-d" || pfx(a[i],"--delete") || has(a[i], "d")) del = 1
        if (a[i] == "-f" || pfx(a[i],"--force") || has(a[i], "f")) force = 1
      }
      if (del && force) fail("`git branch --delete --force` is blocked: same as -D.")
    }
    else if (sub_ == "reset") {
      for (i = 1; i <= na; i++)
        if (pfx(a[i],"--hard"))
          fail("`git reset --hard` is blocked at user scope. It discards uncommitted work, and on " \
               "a shared checkout that work may not be yours. Ask the user to run it themselves, or reach " \
               "for a reversible move: `git revert`, a new branch off the good commit, `git stash`, " \
               "`git reset --soft`/`--mixed`.")
    }
}') || deny 'guard-git-work-loss: awk failed, cannot inspect the command'

[ -n "$reason" ] && deny "$reason"
exit 0
