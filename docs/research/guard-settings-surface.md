# Every path that changes the settings governing the guards, and what a hook sees (measured)

Context: [#384](https://github.com/mark-brannan/languette/issues/384). Which guards run
and how is stored under `pluginConfigs["languette@languette"].options` in the user's
`~/.claude/settings.json` (plus `enabledPlugins`, and the repo's `.languette/` files).
This maps each way to change them and what a `PreToolUse` hook can tell of it. No
prototype; nothing here is a design.

Measured on `main` at 3fbb3cd, Claude Code 2.1.319. "Silent" means `languette/run.py`,
fed the payload under a scratch `HOME`, printed nothing and exited 0: no deny, no ask.
Rows marked read were taken from the code, not run.

## What the hook gets

A throwaway hook, loaded by `--settings`, logged the payload of three calls
(a Bash call, the same from a subagent, a Write):

| Field | Main session | Subagent |
|---|---|---|
| `session_id`, `transcript_path`, `cwd`, `tool_use_id`, `hook_event_name` | yes | yes |
| `tool_name`, `tool_input` (Bash: `command`, `description`; Write: `file_path`, `content`) | yes | yes |
| `permission_mode` | yes | yes |
| `prompt_id`, `effort.level` | yes | yes |
| `agent_id`, `agent_type` | absent | present |

The hook process had stdin a socket (`[ -t 0 ]` false), stdout and stderr sockets, and
`CLAUDE_*` variables inherited from the session (`CLAUDE_CODE_ENTRYPOINT`,
`CLAUDE_CODE_SESSION_ID`, `CLAUDE_PROJECT_DIR`, ...). Nothing in either names a
terminal, a human or a typed command.

## The paths

| # | Path | Call as the hook sees it | Today | Loosening vs tightening from the call alone |
|---|---|---|---|---|
| 1 | `languette config NAME=VALUE` | Bash `command`, name and value in the text | silent | A literal `=false` is readable, but whether it loosens depends on the option: some guards are on unless exactly `false` (`guard_disks`), others off unless exactly `true` (`guard_worktrees`). That is the manifest's, not the call's. A list option needs the current list to tell longer from shorter |
| 2 | `languette config --unset NAME` | Bash `command` | silent | No. It writes the option's default; direction needs the current value, read from settings |
| 3 | `languette doctor --fix` | Bash `command`, no values in it | silent (read) | No. It resets each option its guard refuses to the default; which options and to what is computed inside the process |
| 4 | `claude plugin configure ID --values-stdin` | Bash `command`; the JSON arrives by here-string, here-doc, pipe or file | silent | Only when the JSON is literal in the command text. `cat payload.json \| claude ...` or a variable hides it; also silent |
| 5 | Redirect or in-place edit of `settings.json` (`>`, `sed -i`, `jq ... \| tee`, `python3 -c`) | Bash `command` | silent | No in general. The text names the file at best, never the result |
| 6 | Edit tool on `settings.json` | `file_path`, `old_string`, `new_string` | silent | Yes. The after-state is the file read plus the edit applied, so the options can be diffed |
| 7 | Write tool on `settings.json` | `file_path`, `content` | silent | Yes, the same way: whole new content against the file on disk |
| 8 | `claude plugin disable` or `uninstall`; `enabledPlugins` set false | Bash `command`, or Edit/Write as in 6 and 7 | silent | Always a loosening (every guard goes), but a different file key than `pluginConfigs` |
| 9 | A project's `.claude/settings.json` or `.claude/settings.local.json` | Edit/Write or Bash as above | silent | The doctor reads `enabledPlugins` there (`doctor.py`, `settings_files`); an agent can write the project layer without touching `~/.claude` |
| 10 | `CLAUDE_PLUGIN_OPTION_NAME=false claude ...` | Bash `command` | silent | Sets the option for a nested `claude` only, not this session's guards |
| 11 | Files under `.languette/` (`ask-first.json`, `secrets.json`) and the terms files | Edit/Write or Bash | silent | Same shape as 6 and 7. `ask-first.json` lists the runs that ask; removing an entry loosens |

No row had already gone: every row above is silent on `main` at 3fbb3cd, as it was when
#371 landed (`7cb6452`).

## Findings

1. **No payload field tells the user from the agent.** A hook fires only on the model's
   own tool calls; a command the user types at their own shell never reaches it. So
   every payload it sees is the agent's (the `!` prompt prefix is the one open case,
   under Not measured), and "who is asking" has no answer in the call.
   `agent_id` and `agent_type` tell a subagent from the main session, which is a
   different question. `permission_mode` carries the user's mode, not the author of the
   call. The doctor's `y/N` prompt (`doctor.py`, `fix`) rests on `sys.stdin.isatty()`;
   `--fix` skips it, and an agent's Bash call has no TTY, so that prompt only protects
   against the agent that does not pass `--fix`. `languette config` has no prompt at all.
2. **Direction is decidable for the file tools, not for Bash.** Edit and Write give the
   guard the whole after-state (the file is on disk, the edit is in the payload), so
   rows 6, 7 and 9 can be judged by comparing the options before and after. Rows 1 to 5
   are shell text: only a literal value is readable, and rows 2, 3 and 5 are not even
   that.
3. **One call is not enough, even at its best.** A literal `--unset` or a default is
   "tightening" for one option and "loosening" for the next, because the manifest's
   default differs by option. A guard has to read the manifest and the current settings
   to answer, which a Bash-only rule cannot do from the text.
4. **A loosening has a second, wider door than `languette config`.** Rows 4, 5 and 8
   reach the same file without languette in the command at all, and row 9 reaches it
   from a path the user may not think of as the guards' settings.
5. **An after-the-fact check exists for what the call hides.** `PostToolUse` fires for
   Bash. A hook there could read the options again and compare them with the last
   reading, and say so on the next call. That is detection, not prevention, and holds
   state between calls (a transcript-side record, as the approvals already are).

## Not measured

- Whether a changed option reaches the running session's next hook at once (the
  environment is built when the hook starts, and a settings change may or may not be
  re-read mid-session). One throwaway-plugin run settles it, a few model calls.
- Whether a command the user runs with the `!` prefix in the Claude Code prompt fires
  `PreToolUse`. That is the one path a user's own act might share with the agent's.
- Managed (enterprise) settings, which outrank the user's and which an agent cannot
  write.
- Whether the approvals' own file, `<transcript>.languette-ask`, is writable by the same
  means; the same question one layer over.
