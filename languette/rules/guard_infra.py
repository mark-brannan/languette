"""guard-infra: features/guard-infra.feature is the spec. A rule set (languette/engine.py
reads it) whose handler is code: a command that destroys real infrastructure (terraform
destroy, kubectl delete and kin) runs only on the user's approval, one per run. The walk
of the command is the `infra-runs` test; the approval is read from the transcript, which
also shows the call that spent it, by the `infra-approval` handler (languette/infra_runs.py), which
gives the verdict."""

RULE_SET = {
    "guard": "guard-infra",
    "rules": [{"id": "infra-destroy", "match": [{"test": "infra-runs"}], "action": "deny",
               "handler": "infra-approval"}],
}
