#!/bin/sh
# guard-worktrees: two controls over where a session's git work lands.
#
#   checkout-home  a branch switch in $HOME, when $HOME is itself a worktree
#                  (guard-worktrees-checkout-home.sh)
#   foreign        a reach into a linked worktree that is not the session's own
#                  (guard-worktrees-foreign.sh)
#
# Opt-in: hooks.json runs this only when the plugin option `guard_worktrees`
# is exactly true. A control is skipped when its own option
# (`guard_worktrees_checkout_home`, `guard_worktrees_foreign`) is exactly false.
# The first control to answer wins; a control that crashes makes this crash,
# and hooks.json turns that into a deny.
dir=$(cd "$(dirname "$0")" && pwd) || exit 3
payload=$(cat) || exit 3
for part in checkout-home:GUARD_WORKTREES_CHECKOUT_HOME foreign:GUARD_WORKTREES_FOREIGN; do
  name=${part%%:*}
  eval "opt=\${CLAUDE_PLUGIN_OPTION_${part#*:}-}"
  [ "$opt" = false ] && continue
  out=$(printf '%s' "$payload" | sh "$dir/guard-worktrees-$name.sh") || exit 3
  if [ -n "$out" ]; then printf '%s\n' "$out"; exit 0; fi
done
