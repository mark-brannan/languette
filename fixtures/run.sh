#!/usr/bin/env bash
# Runs the scanner and guard contract in fixtures/*.jsonl.
#
#   fixtures/run.sh            check every fixture; exit 1 on any mismatch
#   fixtures/run.sh --engine python
#                              the same against languette/ (the Python proof of
#                              concept); a verdict for a guard it has not
#                              ported is skipped, and the hooks.json wiring
#                              checks, which run the shell guards, are not run
#   fixtures/run.sh --diff     run both engines over every fixture; exit 1 if
#                              any result the Python engine produces differs
#                              from the awk engine's, right or wrong
#   fixtures/run.sh --table    print the failure-mode table the README quotes
#   fixtures/run.sh --shape [FILE]
#                              only check that FILE (default hooks/hooks.json)
#                              has the shape Claude Code loads; CI runs this
#                              once, the full run repeats it
#
# One fixture per line. Three kinds:
#   tokens   {command, tokens}   scan() of the command, one entry per token:
#                                "w:<word>", "q:<raw text of a quoted word
#                                holding whitespace>", ";" (a separator)
#   texts    {command, texts}    texts_of() after strip_heredocs(), as the
#                                hooks call it: "<0|1>:<text>", 1 = nested
#   verdict  {guard, command, cwd, want[, reason_has, gap, table, note]}
#                                the named hooks/<guard>.sh fed the PreToolUse
#                                payload; want is deny, ask or allow. gap marks
#                                a documented known gap: the guard allows,
#                                silently, and that is the contract.
#                                ask-first verdicts also take a project dir
#                                ($PROJ in cwd), made fresh per fixture as a
#                                git repo: ask_config (object, or a string
#                                written raw) is its .claude/languette-ask.json;
#                                transcript (array of records, or "missing")
#                                its session transcript; spent the ids already
#                                spent; project_env false leaves
#                                CLAUDE_PROJECT_DIR unset; rerun is the decision
#                                a second identical call must get.
#
# It also checks the shape of hooks/hooks.json and its wiring (see below).
# AWK_PATH, as in the guard suites, is a directory whose `awk` is the
# implementation under test.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
LIB="$ROOT/hooks/lib-shell-words.awk"
[ -n "${AWK_PATH:-}" ] && PATH="$AWK_PATH:$PATH"
FIX="$ROOT/fixtures/scanner.jsonl $ROOT/fixtures/guards.jsonl"
ENGINE="awk"
if [ "${1:-}" = "--engine" ]; then
  ENGINE=${2:-}; shift 2 || true
  case $ENGINE in awk | python) : ;; *) echo "run.sh: --engine is awk or python" >&2; exit 2 ;; esac
fi
# The guards languette/ has a Python port of; a verdict for any other is skipped.
PY_GUARDS=" no-rm-tree ask-first "
# The guards with no shell twin: every engine runs their Python, --diff skips them.
PY_ONLY=" ask-first "
in_list() { [ "${1#* "$2" }" != "$1" ]; }

# ask_setup LINE: a fresh project dir in $FIXDIR for an ask-first fixture.
FIXDIR=""
ask_setup() {
  FIXDIR=$(mktemp -d)
  mkdir -p "$FIXDIR/.claude" "$FIXDIR/sub"
  git -C "$FIXDIR" init -q
  if jq -e 'has("ask_config")' <<<"$1" >/dev/null; then
    jq -j 'if (.ask_config | type) == "string" then .ask_config else (.ask_config | tojson) end' <<<"$1" \
      > "$FIXDIR/.claude/languette-ask.json"
  fi
  case $(jq -r '.transcript | type' <<<"$1") in
    array) jq -c '.transcript[]' <<<"$1" > "$FIXDIR/t.jsonl" ;;
    string) : ;;                               # "missing": no file at all
    *) : > "$FIXDIR/t.jsonl" ;;
  esac
  if jq -e 'has("spent")' <<<"$1" >/dev/null; then jq -r '.spent[]' <<<"$1" > "$FIXDIR/t.jsonl.languette-ask"; fi
}

# hooks_shape FILE: print one line per way FILE is not what Claude Code loads
# from a plugin's hooks/hooks.json -- a top-level object whose `hooks` holds
# `PreToolUse`, an array of entries, each with a string `matcher` and a
# non-empty `hooks` array of objects with `type: "command"` and a string
# `command` (Claude Code runs a hook by its `type`; without it, or with
# `type: "prompt"`, the `command` is never run). `claude plugin
# validate --strict` accepts a hooks.json that is garbage, so this is the only
# thing that notices. A shape check only: it proves nothing about what Claude
# Code does with the file (the headless smoke test is still run by hand).
hooks_shape() {
  jq -r '
    if type != "object" then "top level is \(type), want an object"
    elif (.hooks | type) != "object" then "\"hooks\" is \(.hooks | type), want an object (a top-level \"PreToolUse\" is not where Claude Code looks)"
    elif (.hooks.PreToolUse | type) != "array" then "hooks.PreToolUse is \(.hooks.PreToolUse | type), want an array"
    elif (.hooks.PreToolUse | length) == 0 then "hooks.PreToolUse is empty"
    else
      .hooks.PreToolUse | to_entries[] | .key as $i | .value |
      if type != "object" then "PreToolUse[\($i)] is \(type), want an object"
      elif (.matcher | type) != "string" then "PreToolUse[\($i)].matcher is \(.matcher | type), want a string"
      elif (.hooks | type) != "array" or (.hooks | length) == 0 then "PreToolUse[\($i)].hooks is \(.hooks | type), want a non-empty array"
      else .hooks | to_entries[] | .key as $j | .value |
        if type != "object" then "PreToolUse[\($i)].hooks[\($j)] is \(type), want an object"
        elif .type != "command" then "PreToolUse[\($i)].hooks[\($j)].type is \(.type | tojson), want \"command\""
        elif (.command | type) != "string" or .command == "" then "PreToolUse[\($i)].hooks[\($j)].command is \(.command | type), want a non-empty string"
        else empty end
      end
    end' "$1" 2>&1
}

if [ "${1:-}" = "--shape" ]; then
  f=${2:-$ROOT/hooks/hooks.json}
  problems=$(hooks_shape "$f")
  if [ -n "$problems" ]; then printf 'hooks.json shape: %s\n' "$f"; printf '  %s\n' "$problems"; exit 1; fi
  printf 'hooks.json shape ok: %s\n' "$f"
  exit 0
fi

if [ "${1:-}" = "--table" ]; then
  printf '| Command | Verdict | Why |\n|---|---|---|\n'
  jq -r 'select(.kind == "verdict" and .table) |
    "| `\(.command)` | \(if .want == "deny" then "DENY" else .want end) | \(.note)\(if .gap then " (known gap)" else "" end) |"' $FIX
  exit 0
fi

# scan_json <tokens|texts>: stdin is the command; prints a JSON array.
scan_json() {
  awk -v mode="$1" "$(cat "$LIB")"'
function js(s,   i, c, o) {
  o = ""
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "\\") o = o "\\\\"
    else if (c == "\"") o = o "\\\""
    else if (c == "\n") o = o "\\n"
    else if (c == "\t") o = o "\\t"
    else if (c == "\r") o = o "\\r"
    else o = o c
  }
  return "\"" o "\""
}
{ buf = buf (NR > 1 ? "\n" : "") $0 }
END {
  out = ""
  if (mode == "tokens") {
    n = scan(buf, w, k, q)
    for (i = 1; i <= n; i++) {
      v = (k[i] == ";") ? ";" : (k[i] == "q") ? "q:" q[i] : "w:" w[i]
      out = out (i > 1 ? "," : "") js(v)
    }
  } else {
    # exactly what the hooks feed texts_of: the text plus a newline, heredocs stripped
    nt = texts_of(strip_heredocs(buf "\n"), texts, nested)
    for (x = 1; x <= nt; x++) out = out (x > 1 ? "," : "") js(nested[x] ":" texts[x])
  }
  print "[" out "]"
}'
}

pass=0; fail=0; skip=0
bad() { fail=$((fail + 1)); printf 'FAIL: %s\n' "$1"; shift; printf '  %s\n' "$@"; }

# got_of ENGINE LINE: what ENGINE makes of fixture LINE -- the compact JSON
# array for tokens and texts, the hook's raw output for a verdict -- or the
# word SKIP when ENGINE has no port of the guard.
got_of() {
  local kind cmd guard cwd
  kind=$(jq -r .kind <<<"$2")
  cmd=$(jq -j .command <<<"$2")
  case $kind in
    tokens | texts)
      if [ "$1" = python ]; then printf '%s' "$cmd" | python3 -IB "$ROOT/languette/scan.py" "$kind" 2>&1 | jq -c . 2>&1
      else printf '%s' "$cmd" | scan_json "$kind" 2>&1 | jq -c . 2>&1; fi ;;
    verdict)
      guard=$(jq -r .guard <<<"$2")
      cwd=$(jq -r .cwd <<<"$2"); cwd=${cwd/#\$HOME/$HOME}; cwd=${cwd/#\$PROJ/$FIXDIR}
      if [ "$1" = python ] && ! in_list "$PY_GUARDS" "$guard"; then echo SKIP; return; fi
      local penv=(-u CLAUDE_PROJECT_DIR)
      if [ -n "$FIXDIR" ] && [ "$(jq -r '.project_env' <<<"$2")" != false ]; then penv=("CLAUDE_PROJECT_DIR=$FIXDIR"); fi
      jq -n --arg c "$cmd" --arg d "$cwd" --arg t "${FIXDIR:+$FIXDIR/t.jsonl}" \
        '{tool_name:"Bash",tool_input:{command:$c},cwd:$d} + (if $t == "" then {} else {transcript_path:$t} end)' |
        if [ "$1" = python ] || in_list "$PY_ONLY" "$guard"; then env "${penv[@]}" timeout 5 python3 -IB "$ROOT/languette/run.py" --guard "$guard" 2>&1
        else timeout 5 sh "$ROOT/hooks/$guard.sh" 2>&1; fi ;;
  esac
}
decision_of() {
  local d
  d=$(jq -r '.hookSpecificOutput.permissionDecision // empty' <<<"$1" 2>/dev/null)
  printf '%s\n' "${d:-allow}"
}

if [ "${1:-}" = "--diff" ]; then
  same=0
  while IFS= read -r line; do
    if in_list "$PY_ONLY" "$(jq -r '.guard // ""' <<<"$line")"; then skip=$((skip + 1)); continue; fi
    p=$(got_of python "$line")
    if [ "$p" = SKIP ]; then skip=$((skip + 1)); continue; fi
    a=$(got_of awk "$line")
    if [ "$(jq -r .kind <<<"$line")" = verdict ]; then a=$(decision_of "$a"); p=$(decision_of "$p"); fi
    if [ "$a" = "$p" ]; then same=$((same + 1)); else
      bad "engines differ on: $(jq -c .command <<<"$line")" "awk:    $a" "python: $p"; fi
  done < <(cat $FIX)
  printf 'engines: %d agree, %d differ, %d skipped (no Python port)\n' "$same" "$fail" "$skip"
  [ "$fail" -eq 0 ]; exit
fi

while IFS= read -r line; do
  kind=$(jq -r .kind <<<"$line")
  cmd=$(jq -j .command <<<"$line")
  FIXDIR=""
  [ "$(jq -r '.guard // ""' <<<"$line")" = ask-first ] && ask_setup "$line"
  out=$(got_of "$ENGINE" "$line")
  rerun=$(jq -r '.rerun // empty' <<<"$line")
  [ -n "$rerun" ] && out2=$(got_of "$ENGINE" "$line")
  [ -n "$FIXDIR" ] && rm -rf "$FIXDIR"
  case $kind in
    tokens | texts)
      want=$(jq -c ".$kind" <<<"$line")
      if [ "$out" = "$want" ]; then pass=$((pass + 1)); else
        bad "$kind of: $cmd" "want: $want" "got:  $out"; fi ;;
    verdict)
      if [ "$out" = SKIP ]; then skip=$((skip + 1)); continue; fi
      guard=$(jq -r .guard <<<"$line"); want=$(jq -r .want <<<"$line")
      rh=$(jq -r '.reason_has // empty' <<<"$line")
      got=$(decision_of "$out")
      reason=$(jq -r '.hookSpecificOutput.permissionDecisionReason // empty' <<<"$out" 2>/dev/null)
      if [ "$got" != "$want" ]; then bad "$guard, want $want, got $got: $cmd" "hook output: $out"
      elif [ -n "$rh" ] && ! grep -qF -- "$rh" <<<"$reason"; then
        bad "$guard denied, but the reason does not name what it saw ($rh): $cmd" "reason: $reason"
      elif [ -n "$rerun" ] && [ "$(decision_of "$out2")" != "$rerun" ]; then
        bad "$guard, want $rerun on the second call, got $(decision_of "$out2"): $cmd" "hook output: $out2"
      else pass=$((pass + 1)); fi ;;
    *) bad "unknown fixture kind: $kind" ;;
  esac
done < <(cat $FIX)

if [ "$ENGINE" = python ]; then
  printf 'fixtures: %d passed, %d failed, %d skipped (python: %s)\n' "$pass" "$fail" "$skip" "$(command -v python3)"
  [ "$fail" -eq 0 ]; exit
fi

# Wiring: each command in hooks/hooks.json must fail closed. Run it the way
# Claude Code does, with CLAUDE_PLUGIN_ROOT set, three ways: the script is
# there and judges a payload; the script is missing; the script crashes.
# A plain `sh missing.sh` exits 127, which Claude Code reads as a non-blocking
# error, so both failures have to come out as a deny decision.
HJ="$ROOT/hooks/hooks.json"
shape=$(hooks_shape "$HJ")
if [ -n "$shape" ]; then bad "hooks.json is not the shape Claude Code loads" "$shape"; else pass=$((pass + 1)); fi
# And the shape check must reject what #8 found `validate --strict` passing.
SHAPE=$(mktemp)
while IFS= read -r wrong; do
  printf '%s' "$wrong" > "$SHAPE"
  if [ -z "$(hooks_shape "$SHAPE")" ]; then bad "hooks_shape accepted $wrong"; else pass=$((pass + 1)); fi
done <<'WRONG'
{"PreToolUse": 5}
[]
{"hooks": {"PreToolUse": []}}
{"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "x"}]}]}}
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "x"}]}]}}
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "prompt", "command": "x"}]}]}}
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": ""}]}]}}
not json
WRONG
rm -f "$SHAPE"
CRASH=$(mktemp -d)
mkdir -p "$CRASH/hooks"
printf 'exit 3\n' > "$CRASH/hooks/crash.sh"
# ask-first judges only in a project that lists the command.
ASKP=$(mktemp -d); mkdir -p "$ASKP/.claude"
printf '%s' '{"commands":[{"id":"walk","match":[{"cmd":"npm","args":["run","walk"]}],"cost":"long","approve_label":"Run walk"}]}' \
  > "$ASKP/.claude/languette-ask.json"
decision() { jq -r '.hookSpecificOutput.permissionDecision // empty' 2>/dev/null; }
while IFS= read -r c; do
  name=$(sed -n 's|.*/hooks/\([a-z-]*\)\.sh".*|\1|p;s|.*languette/run\.py" --guard \([a-z-]*\);.*|\1|p' <<<"$c" | head -n 1)
  case $name in
    ask-first) cmd='npm run walk' ;;
    no-git-footguns) cmd='git add -A' ;;
    no-rm-tree) cmd='rm -rf build' ;;
    no-delete-stacked-base) cmd='git push origin --delete "$b"' ;;
    *) bad "wiring: no payload known for $name"; continue ;;
  esac
  payload=$(jq -n --arg c "$cmd" --arg d "$HOME/project" --arg t "$ASKP/t.jsonl" \
    '{tool_name:"Bash",tool_input:{command:$c},cwd:$d,transcript_path:$t}')
  export CLAUDE_PROJECT_DIR="$ASKP"
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT="$ROOT" sh -c "$c" 2>&1 | decision)
  case $got in deny | ask) pass=$((pass + 1)) ;; *) bad "wiring: $name did not judge a payload through hooks.json (got: ${got:-nothing})" ;; esac
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT=/nonexistent sh -c "$c" 2>&1 | decision)
  if [ "$got" = deny ]; then pass=$((pass + 1)); else bad "wiring: $name is fail-open when the script is missing (got: ${got:-nothing})"; fi
  # Toggle: CLAUDE_PLUGIN_OPTION_<KEY>=false skips the guard (no output, exit
  # 0). Unset, empty or anything else is not "false" and runs it, so $got is
  # the deny from above. The probe above ran with the variable unset.
  var="CLAUDE_PLUGIN_OPTION_$(printf '%s' "$name" | tr 'a-z-' 'A-Z_')"
  out=$(printf '%s' "$payload" | env "$var=false" CLAUDE_PLUGIN_ROOT="$ROOT" sh -c "$c" 2>&1); rc=$?
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then pass=$((pass + 1)); else bad "wiring: $name still ran with $var=false (rc=$rc, out: $out)"; fi
  for v in "" 0 False no true 1; do
    got=$(printf '%s' "$payload" | env "$var=$v" CLAUDE_PLUGIN_ROOT="$ROOT" sh -c "$c" 2>&1 | decision)
    case $got in deny | ask) pass=$((pass + 1)) ;; *) bad "wiring: $name was skipped with $var='$v' (got: ${got:-nothing})" ;; esac
  done
  if [ "$name" = ask-first ]; then mkdir -p "$CRASH/languette"; printf 'raise SystemExit(3)\n' > "$CRASH/languette/run.py"
  else cp "$CRASH/hooks/crash.sh" "$CRASH/hooks/$name.sh"; fi
  got=$(printf '%s' "$payload" | CLAUDE_PLUGIN_ROOT="$CRASH" sh -c "$c" 2>&1 | decision)
  if [ "$got" = deny ]; then pass=$((pass + 1)); else bad "wiring: $name is fail-open when the script crashes (got: ${got:-nothing})"; fi
done < <(jq -r '.hooks.PreToolUse[] | select(.matcher == "Bash") | .hooks[].command' "$HJ")
unset CLAUDE_PROJECT_DIR
[ "$(jq '[.hooks.PreToolUse[].hooks[]] | length' "$HJ")" = 4 ] || bad "wiring: hooks.json should wire exactly the four guards"
rm -rf "$CRASH" "$ASKP"
# Every guard has exactly one userConfig key, a boolean defaulting to true.
PJ="$ROOT/.claude-plugin/plugin.json"
want='["ask_first","no_delete_stacked_base","no_git_footguns","no_rm_tree"]'
[ "$(jq -c '.userConfig | keys' "$PJ")" = "$want" ] || bad "userConfig: keys should be exactly $want"
[ "$(jq '[.userConfig[] | select(.type == "boolean" and .default == true and .title and .description)] | length' "$PJ")" = 4 ] ||
  bad "userConfig: every key should be a titled, described boolean defaulting to true"

printf 'fixtures: %d passed, %d failed (awk: %s)\n' "$pass" "$fail" "$(command -v awk)"
[ "$fail" -eq 0 ]
