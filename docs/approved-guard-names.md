# Approved guard names

| Guard | Concept | Under the umbrella |
|---|---|---|
| `guard-recursive-delete` | directory trees | recursive `rm`, `find -delete` |
| `guard-permissions` | file modes and ownership | recursive `chmod`, `chown`, `chgrp`; `chmod 777` |
| `guard-host-availability` | the host staying up | shutdown, reboot, fork bombs, service stops |
| `guard-scheduled-jobs` | scheduled work | wiping cron entries or timers |
| `guard-pipe-to-shell` | downloaded code run unseen | `curl u \| sh`, `sh <(curl ..)`, `eval "$(wget ..)"` |
| `guard-worktrees` | worktree isolation | a branch switch in a `$HOME` worktree; another session's worktree |
| `guard-infra` | live infrastructure | destroying or applying it without the user's approval |
| `guard-github-issues` | GitHub issues | creating, transferring or deleting them |
| `guard-private-terms` | private words | a listed term posted to a public repo |
| `guard-secrets` | credentials | one committed, printed into the transcript, or posted |
| `ask-first` | commands the repo lists as costly | each runs only after the user approves that run |
| `guard-protected-paths` | paths the repo lists | any agent write to them |
