# Approved guard names

A countable thing is plural (`guard-secrets`); an act or a mass noun is singular (`guard-infra`).

| Guard | Concept | Under the umbrella |
|---|---|---|
| `ask-first` | commands the repo lists as costly | each runs only after the user approves that run |
| `deny-always` | commands the repo forbids | each listed command, denied every time |
| `guard-commits` | the repo's commit policy | a commit that fails a check the repo lists |
| `guard-databases` | stored data | SQL or NoSQL drops, unbounded deletes, migration resets, restores |
| `guard-disks` | disks and volumes | `dd`, `mkfs`, `wipefs`, `shred` onto a device; partitioning; pool removal |
| `guard-github-issues` | GitHub issues | creating, transferring or deleting them |
| `guard-host-availability` | the host staying up | shutdown, reboot, fork bombs, service stops |
| `guard-infra` | live infrastructure | destroying or applying it without the user's approval |
| `guard-permissions` | file modes and ownership | recursive `chmod`, `chown`, `chgrp`; `chmod 777` |
| `guard-pipe-to-shell` | downloaded code run unseen | `curl u \| sh`, `sh <(curl ..)`, `eval "$(wget ..)"` |
| `guard-private-terms` | private words | a listed term posted to a public repo |
| `guard-protected-paths` | paths the repo lists | any agent write to them |
| `guard-recursive-delete` | directory trees | recursive `rm`, `find -delete` |
| `guard-scheduled-jobs` | scheduled work | wiping cron entries or timers |
| `guard-secrets` | credentials | one committed, printed into the transcript, or posted |
| `guard-sudo` | acting as root | `sudo`, `su`, `doas`, `pkexec` |
| `guard-worktrees` | worktree isolation | a branch switch in a `$HOME` worktree; another session's worktree |
