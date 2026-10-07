#!/bin/sh
# Refuses to delete a remote branch that an open pull request still points at.
#
# The scar: GitHub retargets a stacked PR only when its base branch
# disappears *because the base PR merged*. A base branch deleted any other
# way -- by hand, by a cleanup pass, by a rebase that recreates it under a
# new name -- closes every PR based on it. The closure is silent, the diff
# then reads as conflicting because the base ref is gone, and the recovery
# is reopen-and-retarget, one PR at a time. Deleting the *head* branch of an
# open PR closes that PR the same way.
#
# So this hook fires on remote-branch deletion only, and asks GitHub whether
# any open PR names that branch as its base or its head. The safe path is
# never blocked: `gh pr merge --delete-branch` is the deletion GitHub
# retargets around, and it names no branch, so it never reaches the
# scanner. Local deletion (`git branch -d/-D`) is not a trigger at all --
# it takes nothing away from a PR.
#
# Not a stack? Then there is nothing here to hit. Several small changes in
# flight belong on parallel branches off main; this hook only has something
# to say once one branch is another PR's base.
#
# Decisions, and why they are not symmetric:
#   an open PR found     -> DENY. This is the destructive case and it is
#                           known, not guessed.
#   GitHub not reachable -> ASK. The real case is `gh` absent or signed
#   (no gh, no auth,        out while git itself can still push (an SSH
#    API error)             key, a credential helper): a deny there would
#                           refuse every remote deletion on a machine that
#                           can make them. The prompt carries the branch
#                           name and the one command that settles it.
#   another repository   -> ASK. `git -C`, `--git-dir`, `GIT_DIR=` point
#                           git at a repo that is not the session's cwd,
#                           so the PR list read here says nothing about
#                           it. (`gh api` names its repo in the endpoint,
#                           and that repo is the one queried.)
#   gh hangs, or cannot -> ASK. `gh pr list` runs under `timeout 20`; a
#   be bounded (no          stalled network or a login prompt exits 124,
#   timeout/gtimeout)       which reads like any other failure. Without
#                           timeout (macOS lacking coreutils) the call is
#                           not made at all: an unbounded gh would stall the
#                           hook until the harness kills it, and a killed
#                           hook is not a decision.
#   command unparseable  -> DENY. Inspection failing is not the same as
#   (no jq/awk/library)     inspection coming back empty.
#
# Scanning is shared with guard-git-work-loss.sh/guard-worktrees-checkout-home.sh:
# lib-shell-words.awk (read its header). That is what makes the trigger
# survive a quoted argument, an absolute-path invocation, a nested
# `sh -c '...'`, and a trailing shell comment.
#
# What counts as a remote-branch deletion:
#   git push [<remote>] --delete|-d <ref>...   every ref after the remote
#   git push <remote> :<ref>                   the colon-prefixed refspec
#   gh api -X DELETE .../git/refs/heads/<ref>  the REST spelling
# `refs/heads/` is stripped.
#
# Known gap, deliberate: a deletion spelled through a variable
# (`git push origin --delete "$b"`) resolves to an unexpandable word, so the
# branch cannot be looked up -- it routes to ASK, not to a silent allow.
set -u

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"

decide() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg d "$1" --arg r "$2" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:$d,permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-git-stacked-base: jq is missing, so the command cannot be inspected."}}\n'
  fi
  exit 0
}
deny() { decide deny "$1"; }
ask()  { decide ask  "$1"; }

command -v jq  >/dev/null 2>&1 || deny "guard-git-stacked-base: jq is missing, so the command can't be inspected."
command -v awk >/dev/null 2>&1 || deny "guard-git-stacked-base: awk is missing, so the command can't be inspected."
[ -r "$LIB" ] || deny "guard-git-stacked-base: $LIB missing, so the command can't be inspected."
payload=$(cat) || deny "guard-git-stacked-base: could not read the hook payload."
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny "guard-git-stacked-base: unreadable hook payload."
[ -n "$cmd" ] || exit 0

# Cheap pre-filter: every spelling this hook cares about contains one of
# these. Skips the scanner (and the awk process) on the overwhelming
# majority of commands, which delete no branch at all.
case "$cmd" in
  *push*|*refs/heads/*) ;;
  *) exit 0 ;;
esac

payload_cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$payload_cwd" ] || payload_cwd=$PWD

# awk prints one line per remote-branch deletion it finds: `<repo> <branch>`,
# where <repo> is `-` for the cwd's repository or `owner/name` when the
# command named one. A branch of `?` is a ref it could not resolve to a
# literal name (a variable, a glob); a repo of `?` is git pointed somewhere
# other than the cwd. Both route to ASK rather than being dropped.
branches=$(printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
function emit(repo, ref) {
  sub(/^refs\/heads\//, "", ref)
  if (ref == "" || ref == "HEAD") return
  if (ref ~ /[$`*?\[]/) ref = "?"
  print repo " " ref
}

function git_push(a, b, nested,   g, i, p, del, seen_remote, wv, repo) {
  g = cmd_index(w, k, a, b, "(^|/)(git|yadm)$", nested, "")
  if (!g) return
  p = 0
  for (i = g + 1; i <= b; i++) if (k[i] == "w" && w[i] == "push") { p = i; break }
  if (!p) return

  # Pointed at another repository: the cwd PR list cannot answer for it.
  repo = "-"
  for (i = a; i < g; i++) if (k[i] == "w" && w[i] ~ /^GIT_DIR=/) repo = "?"
  for (i = g + 1; i < p; i++)
    if (k[i] == "w" && (w[i] == "-C" || w[i] ~ /^--git-dir/)) repo = "?"

  del = 0
  for (i = p + 1; i <= b; i++)
    if (k[i] == "w" && (w[i] == "--delete" || w[i] == "-d")) { del = 1; break }

  seen_remote = 0
  for (i = p + 1; i <= b; i++) {
    if (k[i] != "w") continue
    wv = w[i]
    # A colon-prefixed refspec is a deletion whether or not --delete is
    # given, and it is never the remote, so it is read before the
    # remote-skipping below.
    if (substr(wv, 1, 1) == ":") { emit(repo, substr(wv, 2)); continue }
    if (substr(wv, 1, 1) == "-") continue
    if (!seen_remote) { seen_remote = 1; continue }   # the remote name
    if (del) emit(repo, wv)
  }
}

function gh_api(a, b, nested,   g, i, is_api, is_del, wv, m, repo, rest, sl) {
  g = cmd_index(w, k, a, b, "(^|/)(gh|glab)$", nested, "")
  if (!g) return
  is_api = 0; is_del = 0
  for (i = g + 1; i <= b; i++) {
    if (k[i] != "w") continue
    wv = w[i]
    if (wv == "api") is_api = 1
    if (wv == "-X" || wv == "--method") { if (i + 1 <= b && k[i + 1] == "w" && toupper(w[i + 1]) == "DELETE") is_del = 1 }
    if (toupper(wv) == "-XDELETE" || toupper(wv) == "--METHOD=DELETE") is_del = 1
  }
  if (!is_api || !is_del) return
  for (i = g + 1; i <= b; i++) {
    if (k[i] != "w") continue
    m = index(w[i], "refs/heads/")
    if (!m) continue
    # The endpoint names its repository: repos/<owner>/<name>/git/refs/...
    # A `{owner}/{repo}` placeholder is the cwd; anything unresolvable asks.
    repo = "?"
    if (index(w[i], "{owner}/{repo}/")) repo = "-"
    else if (match(w[i], /(^|\/)repos\/[^\/]+\/[^\/]+\//)) {
      rest = substr(w[i], RSTART, RLENGTH); sub(/^\/?repos\//, "", rest); sub(/\/$/, "", rest)
      if (rest !~ /[$`*?\[]/) repo = rest
    }
    emit(repo, substr(w[i], m + 11))
  }
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
      if (a < i) {
        git_push(a, i - 1, nested[x])
        gh_api(a, i - 1, nested[x])
      }
      a = i + 1
    }
  }
}') || deny "guard-git-stacked-base: awk failed, cannot inspect the command"

[ -n "$branches" ] || exit 0

advice() {
  printf '%s' "A stacked PR is retargeted only when its base disappears because the base PR merged. Merge bottom-up with \`gh pr merge --delete-branch\` (which this hook never fires on), or retarget the dependents to their next base first:
  gh pr list --base $1 --json number,title
  gh pr edit <n> --base <new-base>"
}

if printf '%s\n' "$branches" | grep -q ' ?$'; then
  ask "guard-git-stacked-base: this deletes a remote branch named by a variable or a glob, so the branch can't be resolved and checked for open PRs stacked on it. Confirm no open PR names it as base or head:
  gh pr list --state open --json number,baseRefName,headRefName"
fi
if printf '%s\n' "$branches" | grep -q '^? '; then
  ask "guard-git-stacked-base: this deletes a remote branch in a repository other than the current directory's (\`git -C\`, \`--git-dir\`, \`GIT_DIR=\`), so its open PRs can't be checked from here. Confirm none names the branch as base or head:
  gh -R <owner>/<repo> pr list --state open --json number,baseRefName,headRefName"
fi

command -v gh >/dev/null 2>&1 || ask "guard-git-stacked-base: this deletes a remote branch, but \`gh\` is not installed, so open PRs based on it can't be checked. Deleting a branch an open PR points at closes that PR silently."

# Bound every gh call (see the header). GNU coreutils names it `timeout`;
# Homebrew's coreutils installs it as `gtimeout`.
TIMEOUT=""
for t in timeout gtimeout; do
  if command -v "$t" >/dev/null 2>&1; then TIMEOUT=$t; break; fi
done
[ -n "$TIMEOUT" ] || ask "guard-git-stacked-base: this deletes a remote branch, but neither \`timeout\` nor \`gtimeout\` is installed (macOS: \`brew install coreutils\`), so the open-PR list can't be read without risking a hang. Deleting a branch an open PR points at closes that PR silently. Confirm by hand first:
  gh pr list --state open --json number,baseRefName,headRefName"

# Server-side filter per branch, so the answer does not depend on how many
# open PRs the repository has. The jq select is a belt for the same braces.
pr_list() {  # pr_list <repo|-> <--base|--head> <branch>
  if [ "$1" = "-" ]; then set -- "$2" "$3"; else set -- -R "$1" "$2" "$3"; fi
  (cd "$payload_cwd" 2>/dev/null && "$TIMEOUT" 20 gh pr list --state open "$@" --json number,title,baseRefName,headRefName 2>/dev/null)
}
unreadable() {
  ask "guard-git-stacked-base: this deletes remote branch \`$1\`, but the open-PR list could not be read (no auth, no network, a 20s timeout, or not a GitHub repo), so PRs stacked on it can't be checked. Confirm by hand first:
  gh pr list --state open --json number,baseRefName,headRefName"
}

seen=""
while read -r repo b; do
  [ -n "$b" ] || continue
  case " $seen " in *" $repo/$b "*) continue ;; esac
  seen="$seen $repo/$b"

  out=$(pr_list "$repo" --base "$b") || out=""
  [ -n "$out" ] || unreadable "$b"
  based=$(printf '%s' "$out" | jq -r --arg b "$b" '.[] | select(.baseRefName == $b) | "#\(.number) \(.title)"' 2>/dev/null) \
    || ask "guard-git-stacked-base: deleting remote branch \`$b\`, but the open-PR list could not be parsed, so PRs stacked on it can't be checked."
  if [ -n "$based" ]; then
    deny "guard-git-stacked-base: \`$b\` is the base branch of open PR(s):
$based
Deleting it closes every one of them -- GitHub does not retarget a PR whose base is deleted outside a merge, and each has to be reopened and retargeted by hand.

$(advice "$b")"
  fi

  out=$(pr_list "$repo" --head "$b") || out=""
  [ -n "$out" ] || unreadable "$b"
  head=$(printf '%s' "$out" | jq -r --arg b "$b" '.[] | select(.headRefName == $b) | "#\(.number) \(.title)"' 2>/dev/null)
  if [ -n "$head" ]; then
    deny "guard-git-stacked-base: \`$b\` is the head branch of open PR(s):
$head
Deleting it closes them and throws the work away. Merge or close the PR first; \`gh pr merge --delete-branch\` deletes the branch the safe way."
  fi
done <<EOF
$branches
EOF
exit 0
