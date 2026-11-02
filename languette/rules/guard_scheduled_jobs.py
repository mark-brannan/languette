"""guard-scheduled-jobs: features/guard-scheduled-jobs.feature is the spec. A rule
set alone (languette/engine.py reads it): `crontab -r`, which deletes the whole
crontab with no undo, is denied at command position, behind a wrapper, and with r
in a short-option cluster (`-ir`).

A proof of concept for configurable rules (#226): the rule file languette ships
beside this one, when present, adds rules of the same shape. A rule only
tightens, so the file never removes a default; a file that does not load denies
every command, naming the file and the fault."""

RULE_SET = {
    "guard": "guard-scheduled-jobs",
    "file": "guard-scheduled-jobs.json",
    # Process words are commands here, and launchers are not looked through:
    # `pkill crontab -r` is denied and `sh -c "npx crontab -r"` passes.
    "read": {"process_prose": False, "launchers": False},
    "rules": [{"id": "crontab-wipe", "match": [{"cmd": "crontab", "flags": ["r"]}], "action": "deny",
               "why": "cron_remove"}],
}
