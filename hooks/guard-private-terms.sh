#!/bin/sh
# Denies posting text that names a private term to a public GitHub repo.
#
# Why: a private repo or notes directory holds details (boat names, hostnames,
# service URLs, account identifiers) that must not reach the public code
# repos, and a rule kept as prose in CLAUDE.md has already failed at that.
# Once a term is in a public issue or PR comment
# it is in GitHub's history and every mirror of it; the undo is a support
# ticket, not an edit. So the check moves from the model's memory to the
# moment the text leaves the machine.
#
# Fires on PreToolUse for
#   - Bash: `gh issue|pr create|comment|edit|review|close|reopen|merge`, and
#     `gh api` writing to repos/*/*/issues|pulls or a graphql mutation that
#     comments on or opens an issue or PR;
#   - MCP: the GitHub tools that create or edit an issue, PR, comment or
#     review (matched on the tool name's tail).
# Nothing else: a body posted from `python -c`, `curl`, or a script file is
# not inspected. The scope is Bash `gh` and the GitHub MCP tools.
# The text judged is only what is genuinely posted: literal --body/--title/
# --comment/--subject/--label values (a value built from `$(...)` or an
# unfed `$VAR` is refused, not scanned around), gh api -f/-F/--field/
# --raw-field values, every heredoc body, and the contents of --body-file/
# --comment-file/-F/--input/-F key=@file -- never the path itself, since
# that is read, not posted. For MCP, every string in tool_input. A `cd` (or
# any other) path elsewhere in the command is not scanned at all: it was
# never going to be posted. It is grepped case-insensitively, as fixed
# substrings, against the terms file named by the private_terms_file option
# (env CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE), one term per line; comment
# and blank lines in that file are ignored. The reason names the
# term(s) that hit and nothing around them.
#
# A home-directory path found in that text is a sanitization job, not a
# denial job: if this Claude Code version's PreToolUse hooks support
# rewriting the call (`updatedInput`), the guard replaces it with `~` and
# allows; otherwise it stays a denial, with the reason naming the
# substitution to make by hand.
#
# The target repo is --repo/-R, GH_REPO=, a positional issue or PR URL or
# `owner/repo#n`, the `gh api` path, or MCP owner/repo; failing those, the
# origin of the payload's cwd -- unless the command also runs `cd`, in which
# case it is unknown. A graphql mutation names its target by node id, so its
# repo is always unknown, never the cwd's. Unknown is scanned. Only a repo
# listed in the private_repos option (env CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS,
# comma-separated owner/name, default empty) is allowed unscanned, and only
# when every target of the command is one.
#
# INERT without a terms file: with private_terms_file unset or empty the
# guard allows everything, as there is no list to judge against (a guard that
# denied every public post for want of a list would be unusable for anyone who
# has none). Once the option is set, the file is load-bearing: see GATE.
#
# A --body-file path is read as the shell would read it: ~, . and .. apply,
# and what the command does before the gh (a cd, an assignment) is replayed.
#
# GATE, fails closed: no jq, no awk, no library, unreadable payload, a body
# the hook cannot see (--body-file it cannot read, `-F -` with no heredoc,
# a body built from `$(...)` or `$VAR` that no heredoc feeds -- a heredoc
# elsewhere in the command does not vouch for it), a gh write whose flag
# shape isn't one this hook recognises as carrying text (so its content was
# never extracted at all), or a terms file that is set but unreadable or
# empty while a target is not a private repo -> deny, with the fix in the
# reason.
set -uf

# Inert until the user names a terms file; see the header.
TERMS_FILE=${CLAUDE_PLUGIN_OPTION_PRIVATE_TERMS_FILE-}
[ -n "$TERMS_FILE" ] || exit 0

HERE=$(dirname "$0")
LIB="$HERE/lib-shell-words.awk"
PRIVATE_REPOS=${CLAUDE_PLUGIN_OPTION_PRIVATE_REPOS-}
TO_PRIVATE="target a repo listed in the private_repos option"

deny() {
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg r "guard-private-terms: $1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  else
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"guard-private-terms: jq missing, cannot inspect the text about to be posted"}}\n'
  fi
  exit 0
}

command -v jq  >/dev/null 2>&1 || deny 'jq missing, cannot inspect the text about to be posted'
command -v awk >/dev/null 2>&1 || deny 'awk missing, cannot inspect the text about to be posted'
[ -r "$LIB" ] || deny "$LIB missing, cannot inspect the command"

payload=$(cat) || deny 'unreadable hook payload'
tool=$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null) || deny 'unreadable hook payload'
[ -n "$tool" ] || exit 0
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)
[ -n "$cwd" ] || cwd=$PWD

WORK=$(mktemp -d "${TMPDIR:-/tmp}/guard-private-terms.XXXXXX") || deny 'cannot create a scratch directory'
trap 'rm -rf "$WORK"' EXIT
TEXT="$WORK/text"      # everything that will be posted, one candidate per line
META="$WORK/meta"      # R repo (- = the cwd's, ? = unknown) | F file | CDTO dir | CDPUSH/CDPOP ( ) | HFED written here | STDIN | OPAQUE | HEREDOC | CD | UNSEEN flag
: > "$TEXT"; : > "$META"; : > "$WORK/text-cmd"; : > "$WORK/text-file"

# owner/name in lower case from any of the spellings gh and git accept.
norm_repo() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' \
    | sed -e 's#^[a-z]*://[^/]*/##' -e 's#^[^@/]*@[^:]*:##' -e 's#^github\.com/##' -e 's#\.git$##' -e 's#/*$##'
}

case "$tool" in
  Bash)
    cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null) || deny 'unreadable hook payload'
    [ -n "$cmd" ] || exit 0
    printf '%s\n' "$cmd" | awk "$(cat "$LIB")"'
      function wv(i) { return (k[i] == "q") ? q[i] : w[i] }
      function flat(t) { gsub(/\n/, " ", t); return t }
      function file(p) { if (p == "-") print "STDIN"; else print (SEG_NESTED ? "FX\t" : "F\t") flat(p) }
      # Opaque = built at run time. Allowed only when the heredoc feeding it is
      # on the value itself: `$(cat <<EOF ...)` inline, or `$VAR` whose
      # assignment carries `<<`. The heredoc body is in TEXT and gets scanned.
      function fed(v,   name) {
        name = v; sub(/^\$\{?/, "", name); sub(/[^A-Za-z0-9_].*$/, "", name)
        return name != "" && orig ~ ("(^|[;&|[:space:]])" name "=[\"\047]?\\$\\([^)]*<<")
      }
      # strip_heredocs has already turned an inline `$(cat <<EOF ...)` into
      # `$(cat  HEREDOC  )`; either spelling means a heredoc feeds the value.
      function val(v, live) {
        if (!live) { print "T\t" flat(v); return }   # single-quoted: posted verbatim
        if (v ~ /\$\(/ || v ~ /`/) { if (v !~ /<</ && v !~ / HEREDOC /) print "OPAQUE\t" flat(v) }
        else if (v ~ /^\$[A-Za-z_{]/) { if (!fed(v)) print "OPAQUE\t" flat(v) }
        else print "T\t" flat(v)
      }
      function lab(v,   n, a, i) {
        n = split(v, a, ",")
        for (i = 1; i <= n; i++) {
          gsub(/^[[:space:]]+/, "", a[i]); gsub(/[[:space:]]+$/, "", a[i])
          if (a[i] != "") print "T\t" flat(a[i])
        }
      }
      function field(v, live,   key) {
        key = v; sub(/=.*$/, "", key)
        sub(/^[^=]*=/, "", v)
        if (v ~ /^@/) { file(substr(v, 2)); return }
        if (key ~ /label/) lab(v)
        val(v, live)
      }
      { buf = buf $0 "\n" }
      END {
        orig = buf
        # A path is vouched for by a heredoc only when that heredoc is the
        # ONE write to it: `> f <<EOF ... EOF; echo private >> f` writes
        # twice and the gate has read only the first.
        nh = sw_writes(buf, hdt, 1); nw = sw_writes(buf, wrt, 0)
        for (i = 1; i <= nw; i++) nwrites[wrt[i]]++
        for (i = 1; i <= nh; i++) if (nwrites[hdt[i]] == 1) print "HFED\t" hdt[i]
        stripped = strip_heredocs(buf)
        if (stripped != buf) print "HEREDOC"
        # Heredoc bodies are genuinely-posted text (-F -, $(cat <<EOF), a
        # $VAR fed by one) -- strip_heredocs only cared about removing them
        # from buf for tokenising; recover the same bodies here to scan.
        nhd = heredoc_bodies(orig, hdbody)
        for (h = 1; h <= nhd; h++) {
          m = split(hdbody[h], hdl, "\n")
          for (l = 1; l <= m; l++) print "HDTXT\t" hdl[l]
        }
        buf = stripped
        ntexts = texts_of(buf, texts, nested)
        for (x = 1; x <= ntexts; x++) {
          n = scan(texts[x], w, k, q)
          for (i = 1; i <= n; i++) {
            if (k[i] == "w" && w[i] ~ /^(cd|pushd|popd)$/) print "CD"
          }
          a0 = 1
          for (i = 1; i <= n + 1; i++) {
            if (i <= n && k[i] != ";") continue
            if (a0 < i) segment(a0, i - 1, nested[x])
            # A ( ) subshell inherits the cwd and its cd dies at the ): push the
            # virtual cwd at each ( and pop it at each ), in the order written.
            if (!nested[x] && i <= n) for (j = 1; j <= length(SW_sepc[i]); j++) { sc = substr(SW_sepc[i], j, 1); if (sc == "(") print "CDPUSH"; else if (sc == ")") print "CDPOP" }
            a0 = i + 1
          }
        }
      }
      # CDTO <dir>: where a top-level cd/pushd goes. `cd -`, popd and a bare pushd land somewhere unseen: `-` = unknown.
      # A cd in a pipeline, in backticks or backgrounded by a trailing lone `&` runs in a subshell, and one under CDPATH lands wherever the
      # variable says: `-` too. (`&&`, `||` and a `&` ending the previous command are sequence, not background.) `( )` is CDPUSH/CDPOP below.
      function subshelled(lo, hi,   b, a) { b = SW_sepc[lo - 1]; a = SW_sepc[hi + 1]; gsub(/&&|\|\|/, "", b); gsub(/&&|\|\|/, "", a); return b ~ /[|`]/ || a ~ /[|&`]/ }
      function cdto(c, lo, hi,   i, t) {
        t = (w[c] == "cd") ? "~" : "-"
        if (subshelled(lo, hi) || orig ~ /CDPATH=/) { print "CDTO\t-"; return }
        for (i = c + 1; i <= hi && w[c] != "popd"; i++) {
          if (w[i] == "--") { if (i < hi) t = wv(i + 1); break }
          if (w[i] !~ /^[-+]./) { t = wv(i); break }
        }
        print "CDTO\t" flat(t)
      }
      # A NAME VALUE: a standalone or exported assignment (a prefix on the gh itself expands too late to count). FX: a path in nested text, which runs in a shell of its own: read as spelled, literal and absolute, or denied.
      function assign(a, live,   name) { name = a; sub(/=.*$/, "", name); if ((!live && a ~ /\$/) || orig ~ ("(^|[;&|[:space:]])" name "=[\"\047]~")) sub(/=.*$/, "=$", a); print "A\t" flat(a) }   # a single-quoted $, or a quoted ~, is literal: poison it, so the path stays unresolvable
      function segment(lo, hi, nested,   g, i, t, v, repo, posrepo, u, sub_, act, c) {
        SEG_NESTED = nested
        if (!nested) {
          c = seg_cmd(w, k, lo, hi); ok = !c   # seg_cmd is also 0 when a quoted word leads: only a segment of nothing but assignments counts
          for (i = lo; ok && i <= hi; i++) if (k[i] != "w" || w[i] !~ /^[A-Za-z_][A-Za-z0-9_]*=/) ok = 0
          if (ok || (c && w[c] ~ /^(export|local|readonly|declare|typeset)$/)) { for (i = lo; i <= hi; i++) if (k[i] == "w" && w[i] ~ /^[A-Za-z_][A-Za-z0-9_]*=/) assign(w[i], SW_live[i]) }
          else if (w[c] ~ /^(cd|pushd|popd)$/) cdto(c, lo, hi)
        }
        g = cmd_index(w, k, lo, hi, "(^|/)gh$", nested, "")
        if (!g || g + 1 > hi) return
        repo = ""; posrepo = ""
        for (i = lo; i < g; i++) if (k[i] == "w" && w[i] ~ /^GH_REPO=/) repo = substr(w[i], 9)
        sub_ = w[g + 1]
        if (sub_ == "api") { api(g, hi, repo); return }
        if ((sub_ != "issue" && sub_ != "pr") || g + 2 > hi) return
        act = w[g + 2]
        if (act !~ /^(create|comment|edit|review|close|reopen|merge)$/) return
        for (i = g + 3; i <= hi; i++) {
          t = wv(i)  # the real text: a glued flag+quoted-value token may not be kind "w"
          if (t == "--repo" || t == "-R") { if (i < hi) repo = wv(++i) }
          else if (t ~ /^--repo=/) repo = substr(t, 8)
          else if (t ~ /^-R./) repo = substr(t, 3)
          else if (t == "--body-file" || t == "--comment-file" || t == "-F") { if (i < hi) file(wv(++i)) }
          else if (t ~ /^--body-file=/) file(substr(t, 13))
          else if (t ~ /^--comment-file=/) file(substr(t, 16))
          else if (t ~ /^-F./) file(substr(t, 3))
          else if (t ~ /^(--body|--title|--comment|--subject|-b|-t|-c)$/) { if (i < hi) { i++; val(wv(i), SW_live[i]) } }
          else if (t ~ /^--(body|title|comment|subject)=/) { v = t; sub(/^[^=]*=/, "", v); val(v, SW_live[i]) }
          else if (t ~ /^-[btc]./) val(substr(t, 3), SW_live[i])
          else if (t ~ /^(--label|--add-label|-l)$/) { if (i < hi) lab(wv(++i)) }
          else if (t ~ /^--(add-)?label=/) { v = t; sub(/^[^=]*=/, "", v); lab(v) }
          else if (t ~ /^-l./) lab(substr(t, 3))
          # An unrecognised flag whose name says it carries posted text: the
          # value never reaches val()/file() above, so flag it instead of
          # dropping it silently.
          else if (t ~ /^--[A-Za-z-]*(body|comment|message)[A-Za-z-]*/) print "UNSEEN\t" flat(t)
          # A positional URL or owner/repo#n names the target itself: gh
          # posts there, not to the origin of the cwd.
          else if (t ~ /^https?:\/\/[^\/]+\/[^\/]+\/[^\/]+\/(issues|pull)\//) { split(t, u, "/"); posrepo = u[4] "/" u[5] }
          else if (t ~ /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+#[0-9]+$/) { posrepo = t; sub(/#.*$/, "", posrepo) }
        }
        if (posrepo != "") print "R\t" flat(posrepo)
        if (repo != "" || posrepo == "") print "R\t" (repo == "" ? "-" : flat(repo))
      }
      function api(g, hi, repo,   i, t, v, path, method, fields, p, parts, hit) {
        path = ""; method = ""; fields = 0
        for (i = g + 2; i <= hi; i++) {
          t = wv(i)  # the real text: a glued flag+quoted-value token may not be kind "w"
          if (t == "-X" || t == "--method") { if (i < hi) method = toupper(w[++i]) }
          else if (t ~ /^--method=/) method = toupper(substr(t, 10))
          else if (t ~ /^-X./) method = toupper(substr(t, 3))
          else if (t ~ /^(-f|-F|--field|--raw-field)$/) { fields = 1; if (i < hi) { i++; field(wv(i), SW_live[i]) } }
          else if (t ~ /^-[fF]./) { fields = 1; field(substr(t, 3), SW_live[i]) }
          else if (t ~ /^--(field|raw-field)=/) { fields = 1; v = t; sub(/^[^=]*=/, "", v); field(v, SW_live[i]) }
          else if (t == "--input") { fields = 1; if (i < hi) file(wv(++i)) }
          else if (t ~ /^--input=/) { fields = 1; file(substr(t, 9)) }
          else if (t ~ /^(-H|--header|-q|--jq|-t|--template|-p|--preview|--hostname|--cache)$/) i++
          else if (t ~ /^--[A-Za-z-]*(body|comment|message)[A-Za-z-]*/) print "UNSEEN\t" flat(t)
          else if (t ~ /^-/) continue
          else if (path == "") path = t
        }
        p = path; sub(/^https?:\/\/[^\/]+\//, "", p); sub(/^\/+/, "", p)
        if (p ~ /^repos\/[^\/]+\/[^\/]+\/(issues|pulls)(\/|$)/) {
          if (method == "GET" || method == "HEAD" || (method == "" && !fields)) return
          split(p, parts, "/")
          print "R\t" parts[2] "/" parts[3]
        } else if (p == "graphql") {
          hit = 0
          for (i = g; i <= hi; i++)
            if (wv(i) ~ /(addComment|createIssue|updateIssue|createPullRequest|updatePullRequest|addPullRequestReview|submitPullRequestReview|addDiscussionComment)/) hit = 1
          if (hit) print "R\t?"   # the target is a node id in the query, never the origin of the cwd
        }
      }' > "$META" || deny 'awk failed, cannot inspect the command'
    # The tokeniser can lose a segment behind an odd construct; the raw string
    # is the backstop, so a gh write it names is scanned with the repo unknown.
    if ! grep -q '^R	' "$META" && printf '%s' "$cmd" | grep -Eq '(^|[^A-Za-z0-9_./-])gh[[:space:]]+(issue|pr)[[:space:]]+(create|comment|edit|review|close|reopen|merge)([[:space:]]|$)'; then
      printf 'R\t-\n' >> "$META"
    fi
    grep -q '^R	' "$META" || exit 0
    # T (literal --body/--title/--comment/--label values) and HDTXT
    # (heredoc bodies) are already genuinely-posted text -- nothing here
    # ever carries a file-flag path, so nothing needs masking.
    sed -n 's/^T	//p; s/^HDTXT	//p' "$META" >> "$WORK/text-cmd"
    ;;
  mcp__*__create_issue|mcp__*__update_issue|mcp__*__issue_write|mcp__*__add_issue_comment| \
  mcp__*__create_pull_request|mcp__*__update_pull_request| \
  mcp__*__add_pull_request_review_comment|mcp__*__create_pull_request_review| \
  mcp__*__pull_request_review_write|mcp__*__add_comment_to_pending_review| \
  mcp__*__create_and_submit_pull_request_review|mcp__*__submit_pending_pull_request_review)
    repo=$(printf '%s' "$payload" | jq -r 'if (.tool_input.owner? // "") != "" and (.tool_input.repo? // "") != "" then "\(.tool_input.owner)/\(.tool_input.repo)" else "-" end' 2>/dev/null)
    printf 'R\t%s\n' "${repo:--}" >> "$META"
    printf '%s' "$payload" | jq -r '[.tool_input | .. | strings] | join("\n")' 2>/dev/null >> "$WORK/text-cmd" || deny 'unreadable hook payload'
    ;;
  *) exit 0 ;;
esac

# is_private <owner/name, normalised>: listed in private_repos (set -f is on,
# so the unquoted split never globs).
is_private() {
  [ -n "$1" ] || return 1
  ip_ifs=$IFS; IFS=,
  for ip_r in $PRIVATE_REPOS; do
    IFS=$ip_ifs
    ip_r=$(printf '%s' "$ip_r" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
    [ -n "$ip_r" ] && [ "$(norm_repo "$ip_r")" = "$1" ] && return 0
  done
  IFS=$ip_ifs; return 1
}

# Every target must be a private repo for the text to go unscanned; one
# unknown or public target among several means the scan runs.
all_private=1
# shellcheck disable=SC2094  # META is only read here
while IFS="$(printf '\t')" read -r kind repo; do
  [ "$kind" = R ] || continue
  if [ "$repo" = "?" ]; then repo=""
  elif [ "$repo" = "-" ]; then
    if grep -q '^CD$' "$META"; then repo=""
    else repo=$(git -C "$cwd" remote get-url origin 2>/dev/null) || repo=""
    fi
  fi
  is_private "$(norm_repo "$repo")" || all_private=0
done < "$META"
[ "$all_private" = 1 ] && exit 0

# An unrecognised flag that looks like it carries posted text is a hole,
# not a pass: its value never reached val()/file() above, so refuse loudly
# instead of posting text this hook never saw.
if grep -q '^UNSEEN	' "$META"; then
  unseen=$(sed -n 's/^UNSEEN	//p' "$META" | head -1)
  deny "the flag \`$unseen\` looks like it carries text to post, but this hook doesn't recognise its shape and cannot see what it holds. Recognised: --body/--title/--comment/--subject (or -b/-t/-c), --body-file/--comment-file/-F/--input <path>, --label/--add-label, gh api -f/-F/--field/--raw-field. Use one of those, or $TO_PRIVATE."
fi

denylist=$TERMS_FILE
[ -r "$denylist" ] || deny "the private-terms file ($denylist), set as the private_terms_file option, is unreadable, so text bound for a public repo cannot be checked. Fix the path in the plugin's private_terms_file option (/plugin configure languette@languette), or clear the option to turn the check off. To post without the check, $TO_PRIVATE."
sed -e 's/\r$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d' "$denylist" > "$WORK/terms"
[ -s "$WORK/terms" ] || deny "the private-terms file ($denylist) is readable but has no terms in it -- only comments and blank lines, or nothing at all. An empty list matches nothing, so every post would pass unchecked, which is indistinguishable from a check that ran. Populate it (one term per line, # for comments) and retry. To post without the check, $TO_PRIVATE."

# Bodies the hook cannot read are a hole, not a pass. awk emits OPAQUE only
# when no heredoc feeds the value, so a heredoc elsewhere does not excuse it.
opaque=$(sed -n 's/^OPAQUE	//p' "$META" | head -1)
[ -n "$opaque" ] && deny "the body or title is built at run time ($opaque) and no heredoc in this command feeds it, so its text cannot be checked before it is posted. Write it literally, in a heredoc in the same command, or in a file and pass --body-file <path>."
if ! grep -q '^HEREDOC$' "$META"; then
  grep -q '^STDIN$' "$META" && deny "the body comes from stdin (-F - / --input -) and there is no heredoc in the command, so it cannot be checked. Put the text in a heredoc in the same command, or in a file and pass --body-file <path>."
fi
# normpath <absolute path>: collapse . and .. and repeated slashes (set -f
# is on, so the unquoted split never globs).
normpath() {
  np_out=""; np_ifs=$IFS; IFS=/
  for np_seg in $1; do
    case "$np_seg" in ''|.) ;; ..) np_out=${np_out%/*} ;; *) np_out="$np_out/$np_seg" ;; esac
  done
  IFS=$np_ifs; printf '%s' "${np_out:-/}"
}
# resolve <path>: absolute and normalised, as the shell will read it, against
# vcwd, where the command stands at that point (empty = unknown: relative fails).
vcwd=$cwd
cdstack=""; cddepth=0; NL=$(printf '\nx'); NL=${NL%x}   # the virtual cwd outside each open ( subshell, innermost first
# expand <path>: $VAR/${VAR} from the assignments replayed so far, $HOME and a leading ~. An unknown $VAR stays, and resolve refuses it.
expand() {
  cat "$WORK/vars" 2>/dev/null | P="$1" HOMEV="${HOME:-}" awk 'BEGIN { FS = "\t"; v["HOME"] = ENVIRON["HOMEV"] } { v[$1] = $2 } END {
      s = ENVIRON["P"]; if (s ~ /^~(\/|$)/) s = v["HOME"] substr(s, 2)   # ~ expands only where it is written, never where a $VAR puts it
      while ((j = index(s, "$")) > 0) {
        out = out substr(s, 1, j - 1); s = substr(s, j + 1)
        if (!match(s, /^\{[A-Za-z_][A-Za-z0-9_]*\}/) && !match(s, /^[A-Za-z_][A-Za-z0-9_]*/)) { out = out "$"; continue }
        name = substr(s, 1, RLENGTH); gsub(/[{}]/, "", name); if (name in v) { out = out v[name]; s = substr(s, RLENGTH + 1) } else out = out "$"
      }
      print out s }'
}
resolve() { rs_p=$(expand "$1"); case "$rs_p" in *'$'*|*'`'*) return 1 ;; /*) normpath "$rs_p" ;; *) [ -n "$vcwd" ] || return 1; normpath "$vcwd/$rs_p" ;; esac; }
sed -n 's/^HFED	//p' "$META" | grep -v '^$' > "$WORK/hfed"
hfed_has() { while IFS= read -r h; do [ "$(resolve "$h")" = "$1" ] && return 0; done < "$WORK/hfed"; return 1; }
# META is replayed in command order, so what stands before a path is read
# (a cd, an assignment) can be applied to it.
while IFS="$(printf '\t')" read -r kind a <&3; do
  case "$kind" in
    CDTO) if [ "$a" = - ]; then vcwd=""; else vcwd=$(resolve "$a") || vcwd=""; fi; continue ;;
    CDPUSH) cdstack="$vcwd$NL$cdstack"; cddepth=$((cddepth + 1)); continue ;;
    CDPOP) if [ "$cddepth" -gt 0 ]; then vcwd=${cdstack%%"$NL"*}; cdstack=${cdstack#*"$NL"}; cddepth=$((cddepth - 1)); else vcwd=""; fi; continue ;;   # a ) whose ( was never seen: the shell is somewhere unseen
    A) printf '%s\t%s\n' "${a%%=*}" "$(expand "${a#*=}")" >> "$WORK/vars"; continue ;;
    F) ;; FX) case "$a" in *'$'*|[!/]*) printf '%s\n' "$a" > "$WORK/badfile"; continue ;; esac ;; *) continue ;;
  esac
  f=$(resolve "$a") || { printf '%s\n' "$a" > "$WORK/badfile"; continue; }
  # A file this command writes from a heredoc need not exist yet: its text is
  # already in the scanned command, so the gate has read what it will hold.
  [ -r "$f" ] || { hfed_has "$f" || printf '%s\n' "$f" > "$WORK/badfile"; continue; }
  cat "$f" >> "$WORK/text-file"; printf '\n' >> "$WORK/text-file"
done 3< "$META"
[ -f "$WORK/badfile" ] && deny "--body-file $(cat "$WORK/badfile") cannot be read, so the text about to be posted cannot be checked. Write it to that same path from a heredoc in this same command (cat > PATH <<EOF ... EOF, or tee PATH <<EOF) -- the gate reads the heredoc body directly, so the file need not exist yet. Otherwise create the file in an earlier command and retry. The path is resolved with the \$VARs this same command assigns before it, after any cd in it, with . and .. collapsed; a variable set in an earlier command is invisible here, so spell the path out."
cat "$WORK/text-cmd" "$WORK/text-file" > "$TEXT"

grep -q -i -F -f "$WORK/terms" "$TEXT" || exit 0

# The home directory is a sanitization job, not a denial job: the path is
# machine-specific and belongs in posted text as `~`, never literally.
# updatedInput lets a PreToolUse hook rewrite the call, so when stripping
# the home path leaves no other private term, fix it and allow instead of
# denying. A hit inside a --body-file's contents does not qualify:
# rewriting tool_input never touches the file on disk, so the posted text
# would still carry the real path.
if [ -n "${HOME:-}" ] && grep -q -F -e "$HOME" -- "$TEXT" && ! grep -q -F -e "$HOME" -- "$WORK/text-file"; then
  # A plain substring match would also fire on a longer path that merely
  # starts with $HOME (/home/solace2, /home/solace-backup) and, since this
  # one rewrites what actually runs, corrupt it (~2 resolves to a different
  # user's home at execution time). Only replace where $HOME stands as a
  # whole path component: neither neighbour is a name character.
  sanitize() {
    awk -v old="$HOME" -v new='~' '
      { out = ""; s = $0
        while ((j = index(s, old)) > 0) {
          pre  = (j > 1) ? substr(s, j - 1, 1) : ""
          post = substr(s, j + length(old), 1)
          if (pre ~ /[A-Za-z0-9_.-]/ || post ~ /[A-Za-z0-9_.-]/) out = out substr(s, 1, j + length(old) - 1)
          else out = out substr(s, 1, j - 1) new
          s = substr(s, j + length(old))
        }
        print out s }'
  }
  sanitize < "$TEXT" > "$WORK/text.san"
  if ! grep -q -i -F -f "$WORK/terms" "$WORK/text.san"; then
    case "$tool" in
      Bash)
        newcmd=$(printf '%s\n' "$cmd" | sanitize)
        jq -cn --arg c "$newcmd" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$c}}}'
        ;;
      *)
        # jq's gsub is regex, not a literal replace: escape $HOME's regex
        # metacharacters and require the same word-boundary neighbours as
        # the shell path above.
        home_re=$(printf '%s' "$HOME" | sed -e 's/[.^$*+?()\[\]{}|\\]/\\&/g')
        newinput=$(printf '%s' "$payload" | jq -c --arg re "(?<![A-Za-z0-9_.-])${home_re}(?![A-Za-z0-9_.-])" '
          def repl: if type == "string" then gsub($re; "~") else . end;
          .tool_input | walk(repl)' 2>/dev/null) || deny 'unreadable hook payload'
        jq -cn --argjson i "$newinput" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:$i}}'
        ;;
    esac
    exit 0
  fi
fi

hits=""
while IFS= read -r term; do
  grep -q -i -F -e "$term" -- "$TEXT" && hits="$hits, $term"
done < "$WORK/terms"
deny "the text about to be posted to a public repo contains private term(s) from the denylist: ${hits#, }. Private detail does not go on public GitHub, ever -- it stays in GitHub's history. Either $TO_PRIVATE and link it from here, or rewrite the body without the term. Do not paraphrase it into something recognisable."
