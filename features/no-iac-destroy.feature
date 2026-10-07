@python
Feature: no-iac-destroy
  A command that destroys real infrastructure, or applies it without review,
  is denied until the user approves that one run through AskUserQuestion: the
  approval mechanism of ask-first, with the rules built in instead of listed
  by the repo. The deny names what to run instead and how to approve. Plans,
  previews, reads, --help and dry runs pass. Each scenario runs in a fresh git
  repo with an empty transcript, unless it says otherwise.

  Background:
    Given a project directory

  Rule: the destructive forms are denied, and the reason says what to run instead

    Scenario Outline: the command is denied, naming the preview
      When the agent runs `<command>`
      Then the guard denies, naming "<instead>"

      Examples:
        | command                                                                        | instead                            |
        | terraform destroy                                                              | terraform plan -destroy            |
        | tofu destroy                                                                   | tofu plan -destroy                 |
        | terragrunt destroy                                                             | terragrunt plan -destroy           |
        | terraform apply -destroy                                                       | terraform plan -destroy            |
        | terraform apply -auto-approve                                                  | terraform plan` shows the change   |
        | tofu apply -auto-approve                                                       | tofu plan` shows the change        |
        | pulumi destroy                                                                 | pulumi destroy --preview-only      |
        | pulumi up --yes                                                                | pulumi preview --diff              |
        | pulumi up -y                                                                   | pulumi preview --diff              |
        | cdk destroy                                                                    | cdk ls                             |
        | cdk deploy --require-approval never                                            | cdk diff                           |
        | aws ec2 terminate-instances --instance-ids i-0abc                              | aws ec2 describe-instances         |
        | aws iam delete-user --user-name bob                                            | the matching `describe-*`          |
        | aws rds delete-db-instance --db-instance-identifier prod --skip-final-snapshot | the matching `describe-*`          |
        | aws s3 rm s3://bucket --recursive                                              | --dryrun                           |
        | aws s3 rb s3://bucket --force                                                  | aws s3 ls s3://<bucket>            |
        | gcloud compute instances delete vm-1                                           | gcloud ... describe                |
        | az group delete --name rg                                                      | az ... show                        |
        | kubectl delete namespace prod                                                  | --dry-run=server                   |
        | helm uninstall web                                                             | helm uninstall <release> --dry-run |

    Scenario Outline: the reason says how the user approves one run
      When the agent runs `<command>`
      Then the guard denies, naming "one option labelled exactly "<label>""

      Examples:
        | command                                           | label                           |
        | terraform destroy                                 | Run terraform destroy           |
        | terraform apply -auto-approve                     | Run terraform apply unreviewed  |
        | pulumi destroy                                    | Run pulumi destroy              |
        | pulumi up --yes                                   | Run pulumi up unreviewed        |
        | cdk destroy                                       | Run cdk destroy                 |
        | cdk deploy --require-approval never               | Run cdk deploy unreviewed       |
        | aws ec2 terminate-instances --instance-ids i-0abc | Run aws ec2 terminate-instances |
        | aws sqs delete-queue --queue-url u                | Run aws delete                  |
        | aws s3 rm s3://b --recursive                      | Run aws s3 rm --recursive       |
        | aws s3 rb s3://b --force                          | Run aws s3 rb --force           |
        | gcloud projects delete p                          | Run gcloud delete               |
        | az vm delete -n vm -g rg --yes                    | Run az delete                   |
        | kubectl delete pod web-1                          | Run kubectl delete              |
        | helm delete web                                   | Run helm uninstall              |

    Scenario Outline: the command is denied however it is reached or spelled
      When the agent runs `<command>`
      Then the guard denies

      Examples:
        | command                                                        | note                                          |
        | terraform -chdir=infra destroy                                 | a global option before the subcommand         |
        | terraform destroy -auto-approve -target=x.y                    | with its own flags                            |
        | terraform apply --destroy                                      | -- spelling                                   |
        | terraform apply -destroy=true                                  | explicit value                                |
        | terraform apply --auto-approve                                 | -- spelling                                   |
        | terraform apply -auto-approve=true -var a=b                    | explicit value                                |
        | /usr/local/bin/terraform destroy                               | by path                                       |
        | terragrunt run-all destroy --terragrunt-non-interactive        | terragrunt, fanned out over modules           |
        | terragrunt run --all apply -auto-approve                       | terragrunt's newer run form                   |
        | terragrunt --terragrunt-working-dir infra destroy              | terragrunt's own valued option first          |
        | terragrunt destroy-all                                         | terragrunt's old spelling                     |
        | timeout 1h terraform destroy                                   | wrapper                                       |
        | sudo -u deploy kubectl delete -f app.yaml                      | sudo                                          |
        | cd infra && terraform destroy                                  | chain                                         |
        | terraform plan; terraform destroy                              | later in a ; chain                            |
        | sh -c "terraform destroy"                                      | sh -c nests                                   |
        | bash -c 'timeout 1h terraform destroy'                         | bash -c with a wrapper inside                 |
        | echo terraform destroy \| sh                                   | echo into a shell                             |
        | aws-vault exec prod -- terraform destroy                       | a credentials wrapper                         |
        | ssh bastion kubectl delete pod web-1                           | remote                                        |
        | pulumi down                                                    | destroy's alias                               |
        | pulumi --cwd infra destroy --yes                               | a global option's value before the subcommand |
        | pulumi up -yf                                                  | clustered short flags                         |
        | pulumi update --yes                                            | up's alias                                    |
        | pulumi destroy --preview-only=false                            | preview switched off                          |
        | npx cdk destroy                                                | npx launcher                                  |
        | npx aws-cdk@2 destroy MyStack                                  | the package name, with a version              |
        | pnpm dlx aws-cdk destroy                                       | pnpm dlx launcher                             |
        | cdk -a "node app.js" destroy                                   | an option's value before the subcommand       |
        | cdk deploy --require-approval=never                            | = spelling                                    |
        | cdk deploy MyStack --require-approval never                    | after a stack name                            |
        | aws --profile prod ec2 terminate-instances --instance-ids i-1  | a global option's value first                 |
        | aws ec2 delete-security-group --group-id sg-1                  | any delete-*                                  |
        | aws ec2 terminate-instances --no-dry-run                       | --no-dry-run is not a dry run                 |
        | aws s3 rm s3://b --recursive --exclude "*.txt"                 | with filters                                  |
        | gcloud --project p compute instances delete vm                 | gcloud, a global option first                 |
        | az keyvault secret delete --vault-name v -n s                  | az, a deep subcommand                         |
        | kubectl -n prod delete deploy web                              | a namespace option's value first              |
        | kubectl --namespace=prod delete deploy web                     | = spelling                                    |
        | kubectl delete -f app.yaml --dry-run=none                      | dry-run switched off                          |
        | kubectl delete -f app.yaml --dry-run=false                     | dry-run switched off                          |
        | helm --kube-context prod uninstall web                         | a global option's value first                 |
        | helm del web                                                   | del alias                                     |
        | helm un web                                                    | un alias                                      |
        | helm uninstall web --dry-run=false                             | dry-run switched off                          |

  Rule: plans, previews, reads and help pass

    Scenario Outline: a command that only looks, plans or previews is silent
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                                  | note                                |
        | terraform plan                                           | the plan                            |
        | terraform plan -destroy                                  | the destroy plan                    |
        | terraform apply                                          | prompts the user itself             |
        | terraform apply -auto-approve=false                      | explicit off                        |
        | terraform apply plan.tfplan                              | a saved plan, reviewed at plan time |
        | terraform init                                           |                                     |
        | terraform destroy --help                                 | help                                |
        | terraform destroy -h                                     | help                                |
        | tofu plan -destroy                                       |                                     |
        | terragrunt plan -destroy                                 |                                     |
        | terragrunt run-all plan                                  |                                     |
        | terragrunt hcl fmt                                       |                                     |
        | terraform state list                                     |                                     |
        | pulumi preview                                           |                                     |
        | pulumi up                                                | prompts the user itself             |
        | pulumi up --preview-only --yes                           | preview only                        |
        | pulumi destroy --preview-only                            | preview only                        |
        | pulumi stack ls                                          |                                     |
        | cdk diff                                                 |                                     |
        | cdk deploy                                               | prompts for security changes        |
        | cdk deploy --require-approval broadening                 | still asks about broadening         |
        | cdk synth                                                |                                     |
        | aws ec2 terminate-instances --instance-ids i-1 --dry-run | dry run                             |
        | aws ec2 delete-security-group --group-id sg-1 --dry-run  | dry run                             |
        | aws ec2 describe-instances                               | a read                              |
        | aws s3 ls s3://b --recursive                             | a listing                           |
        | aws s3 rm s3://b --recursive --dryrun                    | s3's own dry run                    |
        | aws s3 rm s3://b/one-key                                 | one object, not a prefix            |
        | aws s3 rb s3://b                                         | refuses a non-empty bucket          |
        | aws --profile delete-me s3 ls                            | an option's value                   |
        | aws s3api list-objects --bucket b                        |                                     |
        | gcloud compute instances list                            |                                     |
        | gcloud compute instances describe vm                     |                                     |
        | gcloud compute instances delete vm --help                | help                                |
        | az group show --name rg                                  |                                     |
        | az vm list                                               |                                     |
        | kubectl get pods                                         |                                     |
        | kubectl delete -f app.yaml --dry-run=client              | client dry run                      |
        | kubectl delete -f app.yaml --dry-run=server              | server dry run                      |
        | kubectl delete pod web-1 --dry-run                       | bare dry run                        |
        | kubectl --namespace delete get pods                      | delete is the namespace's value     |
        | kubectl apply -f app.yaml                                |                                     |
        | helm install web ./chart                                 |                                     |
        | helm uninstall web --dry-run                             | dry run                             |
        | helm plugin uninstall diff                               | a plugin, not a release             |
        | helm list                                                |                                     |

    Scenario Outline: prose and process tools that name a destructive command are not running it
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                                       | note                 |
        | grep -rn 'terraform destroy' docs             | grep prose           |
        | rg "kubectl delete" .                         | rg prose             |
        | git commit -m "docs: never terraform destroy" | commit message prose |
        | gh pr create -b "run kubectl delete by hand"  | PR body prose        |
        | echo terraform destroy                        | echo with no shell   |
        | cat runbooks/kubectl-delete.md                | a file name          |
        | pkill -f "terraform destroy"                  | pkill names it       |
        | pgrep -f "kubectl delete"                     | pgrep, quoted        |
        | which terraform                               | which names it       |
        | ls terraform                                  | a directory name     |

  Rule: a destructive command needs the user's approval for each run

    Scenario: approved once
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy`
      Then the guard is silent

    Scenario: approved, then spent on the first call
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy`
      Then the guard is silent
      When the agent runs it again
      Then the guard denies

    Scenario: the label approves its own rule, not another's
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `kubectl delete namespace prod`
      Then the guard denies, naming "Run kubectl delete"

    Scenario: one approval covers every spelling of its rule
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `tofu apply -destroy`
      Then the guard is silent

    Scenario: already spent
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      And the approvals already spent are:
        """
        toolu_A
        """
      When the agent runs `terraform destroy`
      Then the guard denies

    Scenario: the user chose skip
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Skip\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy`
      Then the guard denies

    Scenario: the label is not exact
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy later\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy`
      Then the guard denies

    Scenario: another label does not approve a destroy
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run e2e\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy`
      Then the guard denies

    Scenario: two runs with one approval
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy; terraform destroy`
      Then the guard denies, naming "runs the rule 2 times and has 1 unspent"

    Scenario: two runs with two approvals
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_B", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy && terraform destroy`
      Then the guard is silent
      When the agent runs it again
      Then the guard denies

    Scenario: two rules, one approved
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy && kubectl delete namespace prod`
      Then the guard denies, naming "Run kubectl delete"

    Scenario: two rules, both approved
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_K", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `kubectl delete`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run kubectl delete", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_K", "content": "User has answered your questions: \"Run `kubectl delete`?\"=\"Run kubectl delete\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `terraform destroy && kubectl delete namespace prod`
      Then the guard is silent

    Scenario: a nested run counts once
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `sh -c "terraform destroy"`
      Then the guard is silent

    Scenario: the transcript is missing
      Given the transcript is missing
      When the agent runs `terraform destroy`
      Then the guard denies, naming "cannot read the session transcript"

    Scenario: the payload names no transcript
      When the agent calls tool "Bash" with input `{"command": "terraform destroy"}`
      Then the guard denies, naming "cannot read the session transcript"

    Scenario: the transcript is missing and the command is a preview
      Given the transcript is missing
      When the agent runs `terraform plan -destroy`
      Then the guard is silent

  Rule: a run inside a loop or xargs is denied whatever was approved

    Scenario Outline: a loop or fan-out
      Given the transcript holds:
        """
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_A", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_A", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_B", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `terraform destroy`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run terraform destroy", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_B", "content": "User has answered your questions: \"Run `terraform destroy`?\"=\"Run terraform destroy\". You can now continue with the user's answers in mind."}]}}
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_K", "name": "AskUserQuestion", "input": {"questions": [{"question": "Run `kubectl delete`?", "header": "Destroy", "multiSelect": false, "options": [{"label": "Run kubectl delete", "description": "irreversible"}, {"label": "Skip", "description": ""}]}]}}]}}
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_K", "content": "User has answered your questions: \"Run `kubectl delete`?\"=\"Run kubectl delete\". You can now continue with the user's answers in mind."}]}}
        """
      When the agent runs `<command>`
      Then the guard denies, naming "unknown number of times"

      Examples:
        | command                                                 | note          |
        | for d in a b c; do terraform -chdir=$d destroy; done    | loop          |
        | kubectl get pods -o name \| xargs kubectl delete        | xargs fan-out |
        | find . -name '*.yaml' -exec kubectl delete -f {} \;     | find -exec   |
        | while read n; do kubectl delete pod $n; done < pods.txt | while         |

  Rule: tools outside the rules are not this guard's business

    Scenario Outline: a command no rule covers is silent
      When the agent runs `<command>`
      Then the guard is silent

      Examples:
        | command                   | note                      |
        | ls                        |                           |
        | docker rm web             | docker is not covered     |
        | ansible-playbook site.yml | ansible is not covered    |
        | psql -c "DROP TABLE t"    | databases are not covered |
