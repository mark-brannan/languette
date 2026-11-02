"""guard-disks: features/guard-disks.feature is the spec. A rule set alone
(languette/engine.py reads it): the commands that overwrite a disk are denied: `dd` with of=
under /dev, mkfs*, wipefs and shred on anything but the agent's own area (the scratchpad,
an agent worktree or /tmp), and a redirection or tee onto a disk device. A target this
guard cannot resolve to one allowed path is denied on sight, with a reason naming what it
saw. The walk of the command and the judging of its targets are the `disks` test; it gives
the verdict itself."""

RULE_SET = {
    "guard": "guard-disks",
    "rules": [{"id": "disks", "match": [{"test": "disks"}], "action": "deny"}],
}
