# How Claude Code passes plugin settings to a hook (measured)

Claude Code hands each key to the hook as `CLAUDE_PLUGIN_OPTION_<KEY>`.
Measured on Claude Code 2.1.258, with a throwaway plugin loaded by
`--plugin-dir` and options supplied through `pluginConfigs`:

| Setting | Env in the hook |
|---|---|
| key `flag_off`, boolean `false` | `CLAUDE_PLUGIN_OPTION_FLAG_OFF=false` |
| key `flag_on`, boolean `true` | `CLAUDE_PLUGIN_OPTION_FLAG_ON=true` |
| key `camelKey`, boolean `false` | `CLAUDE_PLUGIN_OPTION_CAMELKEY=false` |
| `multiple` string `["a b","c,d"]` | `CLAUDE_PLUGIN_OPTION_LIST_VALS=a b,c,d` |
| `multiple` string `[]` | `CLAUDE_PLUGIN_OPTION_LIST_VALS=` |
| key unset, though the manifest gives a `default` | variable absent |

The name is the key upper-cased, underscores kept and camelCase not split.
Booleans arrive as the words `true` and `false`. A list is joined with a bare
comma and no escaping, so an item holding a comma can't be recovered. A
string `"false"` looks the same as a boolean `false`. A `default` did not
reach the environment under `--plugin-dir`; the installed-plugin path was not
measured, which is why the guards treat unset as on.
