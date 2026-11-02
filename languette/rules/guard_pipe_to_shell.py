"""guard-pipe-to-shell: features/guard-pipe-to-shell.feature is the spec. A rule
set alone (languette/engine.py reads it): a download that is run as it arrives is
denied: curl, wget or fetch piped into an interpreter that reads its program from
stdin (`curl u | sh`, `| sudo bash -s`, `| python3 -`), a download handed over as
a file (`sh <(curl u)`, `source <(curl u)`) and one handed over as text
(`eval "$(curl u)"`, `bash -c "$(curl u)"`). An interpreter given a script of its
own (`| python3 -c ...`, `| node -e ...`, `| sh install.sh`) is not reading the
download as code. The reading of pipes and substitutions is the `pipe-to-shell`
test in languette/primitives.py."""

RULE_SET = {
    "guard": "guard-pipe-to-shell",
    "rules": [{"id": "pipe-to-shell", "match": [{"test": "pipe-to-shell"}], "action": "deny", "why": "pipe_to_shell"}],
}
