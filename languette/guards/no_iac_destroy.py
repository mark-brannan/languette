"""no-iac-destroy: a command that destroys real infrastructure runs only after
the user said yes to it, once, through AskUserQuestion.

The approval is ask-first's: an AskUserQuestion whose answer (not the
question, which is the agent's text) is exactly the rule's label, spent
through <transcript>.languette-ask, one click for one run. A command that runs
a rule twice needs two approvals; one inside a loop or xargs is denied
outright. Unlike ask-first, the list is built in, not the repo's.

Rules, judged on the words after the tool's name, global options skipped:

  rule                      command
  terraform-destroy         terraform|tofu|terragrunt destroy, or apply -destroy
  terraform-apply           terraform|tofu|terragrunt apply -auto-approve
  pulumi-destroy            pulumi destroy|down, unless --preview-only
  pulumi-up                 pulumi up|update --yes|-y, unless --preview-only
  cdk-destroy               cdk destroy
  cdk-deploy                cdk deploy --require-approval never
  aws-terminate-instances   aws ec2 terminate-instances, unless --dry-run
  aws-delete                aws <service> delete-*, unless --dry-run; so
                            rds delete-db-instance too
  aws-s3-rm                 aws s3 rm --recursive, unless --dryrun
  aws-s3-rb                 aws s3 rb --force
  gcloud-delete             gcloud ... delete
  az-delete                 az ... delete
  kubectl-delete            kubectl delete, unless --dry-run (bare, =client
                            or =server)
  helm-uninstall            helm uninstall|delete|del|un, unless --dry-run

Terragrunt is terraform with its own options skipped; `run-all`/`run --all`
fans out over modules and is one run here. The approval is the rule's, not
the command's: a click on "Run kubectl delete" pays for the next kubectl
delete the agent runs, whatever its target, which is why the deny tells the
agent to put the exact command in the question. Plans, previews, reads and
--help pass, since no rule names them. The tool is
found through wrappers, chains, `sh -c "..."`, `echo ... | sh` and the
launchers npx, bunx, `pnpm|yarn dlx` (`npx aws-cdk@2 destroy`); prose (grep,
git commit -m, cat) and process tools (pkill -f) that merely name a command
are not running it. Not seen: a run inside a script (`make destroy`), behind a
variable (`terraform $ACTION`), in a config file (cdk.json's requireApproval),
or applying a saved plan (`terraform apply plan.tfplan`); nor eksctl, oc,
helmfile, docker, ansible or a database's DROP.
"""

import re

from languette import scan as sw
from languette.guards.ask_first import LAUNCH, LOOP, PROSE, claim
from languette.verdict import deny

NAME = "no-iac-destroy"

# id -> (approve_label, what it does, cost, what to run instead). {tool} is the
# command word as written (terraform or tofu).
RULES = {
    "terraform-destroy": (
        "Run terraform destroy", "destroys the infrastructure",
        "deletes every resource the state manages, and the data on them",
        "`{tool} plan -destroy` lists what would go"),
    "terraform-apply": (
        "Run terraform apply unreviewed", "applies with -auto-approve",
        "applies a plan nobody read, which can create, change or delete real resources",
        "`{tool} plan` shows the change"),
    "pulumi-destroy": (
        "Run pulumi destroy", "destroys the stack",
        "deletes every resource in the stack, and the data on them",
        "`pulumi destroy --preview-only` lists what would go"),
    "pulumi-up": (
        "Run pulumi up unreviewed", "updates with --yes",
        "applies a change nobody read, which can create, change or delete real resources",
        "`pulumi preview --diff` shows the change"),
    "cdk-destroy": (
        "Run cdk destroy", "destroys stacks",
        "deletes the stacks and every resource in them",
        "`cdk ls` lists the stacks, `cdk diff` shows what a deploy would change"),
    "cdk-deploy": (
        "Run cdk deploy unreviewed", "deploys with --require-approval never",
        "skips the review of IAM and security-group changes",
        "`cdk diff` shows the change, with the security-sensitive parts called out"),
    "aws-terminate-instances": (
        "Run aws ec2 terminate-instances", "terminates EC2 instances",
        "terminates the instances, and the data on their instance-store volumes with them",
        "`aws ec2 describe-instances` shows what would go, and `--dry-run` checks the call"),
    "aws-delete": (
        "Run aws delete", "deletes cloud resources",
        "deletes the resource, and usually the data in it, with no recycle bin",
        "the matching `describe-*`, `get-*` or `list-*` call shows what would go (`--dry-run` where the service has it)"),
    "aws-s3-rm": (
        "Run aws s3 rm --recursive", "deletes every object under a prefix",
        "deletes every object under the prefix; only a versioned bucket keeps older versions",
        "`--dryrun` lists what would go, and `aws s3 ls --recursive` shows what is there"),
    "aws-s3-rb": (
        "Run aws s3 rb --force", "empties a bucket and deletes it",
        "deletes every object in the bucket, then the bucket",
        "`aws s3 ls s3://<bucket> --recursive` shows what it holds"),
    "gcloud-delete": (
        "Run gcloud delete", "deletes cloud resources",
        "deletes the resource, and usually the data in it",
        "`gcloud ... describe` or `gcloud ... list` shows what would go"),
    "az-delete": (
        "Run az delete", "deletes cloud resources",
        "deletes the resource, and usually the data in it; a resource group takes everything in it",
        "`az ... show` or `az ... list` shows what would go"),
    "kubectl-delete": (
        "Run kubectl delete", "deletes cluster objects",
        "deletes the objects; a namespace takes everything in it, and a volume claim its data",
        "`--dry-run=server` shows what would go, and `kubectl get` shows what is there"),
    "helm-uninstall": (
        "Run helm uninstall", "uninstalls a release",
        "removes the release and the resources it created from the cluster",
        "`helm uninstall <release> --dry-run` shows what would go, and `helm status` what is there"),
}

TOOLS = frozenset("terraform tofu terragrunt pulumi cdk aws-cdk aws gcloud az kubectl helm".split())
_TOOL = re.compile(r"(?:^|/)(?:" + "|".join(sorted(TOOLS)) + r")(?:@[^/]*)?\Z")
_ANY = re.compile(r"(?:^|/)(?:" + "|".join(sorted(TOOLS | LAUNCH)) + r")(?:@[^/]*)?\Z")
_LAUNCHER = re.compile(r"(?:^|/)(?:" + "|".join(sorted(LAUNCH)) + r")\Z")
HELP = frozenset("-h -help --help".split())

# Options that take the next word as their value, and so must not be
# mistaken for the subcommand. Unknown options are read as flags.
VALUED = {
    "terragrunt": "--terragrunt-config --config --terragrunt-working-dir --working-dir --terragrunt-download-dir "
                  "--download-dir --terragrunt-iam-role --iam-assume-role --terragrunt-parallelism --parallelism "
                  "--terragrunt-include-dir --queue-include-dir --terragrunt-exclude-dir --queue-exclude-dir "
                  "--terragrunt-log-level --log-level --terragrunt-source --source",
    "pulumi": "--color --cwd -C --profiling --tracing --memprofilerate --verbose -v",
    "cdk": "-a --app -c --context -p --plugin --profile -r --role-arn -o --output --proxy --ca-bundle-path "
           "--toolkit-stack-name --build --lookups --notices",
    "aws": "--profile --region --endpoint-url --output --query --ca-bundle --cli-read-timeout "
           "--cli-connect-timeout --color --cli-binary-format",
    "kubectl": "-n --namespace --context --kubeconfig --cluster --user -s --server --token --as --as-group "
               "--as-uid --certificate-authority --client-certificate --client-key --cache-dir "
               "--request-timeout --tls-server-name --username --password --profile --profile-output "
               "--log-flush-frequency -v --v --vmodule",
    "helm": "-n --namespace --kube-context --kubeconfig --kube-apiserver --kube-token --kube-as-user "
            "--kube-as-group --kube-ca-file --kube-tls-server-name --registry-config --repository-cache "
            "--repository-config --burst-limit --qps",
}
VALUED = {k: frozenset(v.split()) for k, v in VALUED.items()}


def _name(word):
    """The tool a command word names: its basename, without an @version."""
    b = word.rsplit("/", 1)[-1]
    b = b.split("@", 1)[0] if "@" in b[1:] else b
    return "cdk" if b == "aws-cdk" else b


def _pos(rest, valued=frozenset()):
    """The non-option words of `rest`, skipping the value of an option in
    `valued`."""
    out, skip = [], False
    for w in rest:
        if skip:
            skip = False
        elif w in valued:
            skip = True
        elif not w.startswith("-"):
            out.append(w)
    return out


def _flag(rest, *names):
    """The last `-name`, `--name` or `--name=value` among `rest`: None when
    absent, "" when bare, else the value. Names carry no dashes."""
    v = None
    for w in rest:
        m = re.fullmatch(r"--?([^=]+)(?:=(.*))?", w)
        if m and m.group(1) in names:
            v = m.group(2) or ""
    return v


def _on(v):
    """A boolean flag's value, as Go's and Python's flag parsers read it."""
    return v is not None and v.lower() not in ("false", "f", "0")


def _after(rest, name):
    """The value of --name, as `--name=v` or `--name v`."""
    for i, w in enumerate(rest):
        if w.startswith(f"--{name}="):
            return w.split("=", 1)[1]
        if w == f"--{name}" and i + 1 < len(rest):
            return rest[i + 1]
    return None


def _terraform(rest):
    sub = (_pos(rest) or [None])[0]
    if sub == "destroy" or (sub == "apply" and _on(_flag(rest, "destroy"))):
        return "terraform-destroy"
    if sub == "apply" and _on(_flag(rest, "auto-approve")):
        return "terraform-apply"


def _terragrunt(rest):
    """Terraform, after terragrunt's own options and the run-all forms."""
    words, skip = [], False
    for w in rest:
        if skip:
            skip = False
        elif w in VALUED["terragrunt"]:
            skip = True
        else:
            words.append(w)
    pos = _pos(words)
    if pos and pos[0] in ("run-all", "run"):
        words = words[words.index(pos[0]) + 1:]
    elif pos and pos[0] in ("destroy-all", "apply-all"):
        words = [pos[0][:-4]] + words[words.index(pos[0]) + 1:]
    return _terraform(words)


def _pulumi(rest):
    sub = (_pos(rest, VALUED["pulumi"]) or [None])[0]
    if _on(_flag(rest, "preview-only")):
        return None
    if sub in ("destroy", "down"):
        return "pulumi-destroy"
    yes = _on(_flag(rest, "yes")) or any(re.fullmatch(r"-[yfrdeE]*y[yfrdeE]*", w) for w in rest)
    if sub in ("up", "update") and yes:
        return "pulumi-up"


def _cdk(rest):
    sub = (_pos(rest, VALUED["cdk"]) or [None])[0]
    if sub == "destroy":
        return "cdk-destroy"
    if sub == "deploy" and _after(rest, "require-approval") == "never":
        return "cdk-deploy"


def _aws(rest):
    pos = _pos(rest, VALUED["aws"])
    service, op = (pos + [None, None])[:2]
    dry = _on(_flag(rest, "dry-run"))
    if op == "terminate-instances" and not dry:
        return "aws-terminate-instances"
    if op and op.startswith("delete-") and not dry:
        return "aws-delete"
    if service == "s3" and op == "rm" and _on(_flag(rest, "recursive")) and not _on(_flag(rest, "dryrun")):
        return "aws-s3-rm"
    if service == "s3" and op == "rb" and _on(_flag(rest, "force")):
        return "aws-s3-rb"


def _kubectl(rest):
    if (_pos(rest, VALUED["kubectl"]) or [None])[0] != "delete":
        return None
    dry = _flag(rest, "dry-run")
    if dry is None or dry not in ("", "client", "server", "true"):
        return "kubectl-delete"


def _helm(rest):
    if (_pos(rest, VALUED["helm"]) or [None])[0] in ("uninstall", "delete", "del", "un") \
            and not _on(_flag(rest, "dry-run")):
        return "helm-uninstall"


def _delete(rule):
    return lambda rest: rule if "delete" in _pos(rest) else None


JUDGE = {"terraform": _terraform, "tofu": _terraform, "terragrunt": _terragrunt, "pulumi": _pulumi, "cdk": _cdk, "aws": _aws,
         "gcloud": _delete("gcloud-delete"), "az": _delete("az-delete"), "kubectl": _kubectl, "helm": _helm}


def _judge(word, rest):
    """The rule the command `word rest...` breaks, or None."""
    if HELP & set(rest):
        return None
    return JUDGE[_name(word)](rest)


def _candidates(s, g, b, nested):
    """Indices of tool words to judge in a segment whose first tool-or-launcher
    word is g. A launcher (npx, pnpm dlx) hands over to the first tool after it."""
    if _LAUNCHER.search(s.w[g]) and not _TOOL.search(s.w[g]):
        return [i for i in range(g + 1, b + 1) if s.k[i] == "w" and _TOOL.search(s.w[i])][:1]
    if nested:
        return [g]
    return [i for i in range(g, b + 1) if s.k[i] == "w" and _TOOL.search(s.w[i])]


def _runs(text):
    """({rule: [tool name per run]}, whether the text has a loop word). A
    segment is one run of at most one rule."""
    found, loop = {}, False
    for t, nested in sw.texts_of(sw.strip_heredocs(text), PROSE):
        s = sw.Scan(t)
        loop = loop or any(k == "w" and w in LOOP for k, w in zip(s.k, s.w))
        for a, b in s.segments():
            if a > b:
                continue
            g = sw.cmd_index(s, a, b, _ANY, nested, prose=PROSE)
            if g is None:
                continue
            for i in _candidates(s, g, b, nested):
                rule = _judge(s.w[i], s.w[i + 1:b + 1])
                if rule:
                    found.setdefault(rule, []).append(_name(s.w[i]))
                    break
    return found, loop


def check(payload, env=None):
    cmd = (payload.get("tool_input") or {}).get("command") if isinstance(payload, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    found, loop = _runs(cmd + "\n")
    if not found:
        return None
    if loop:
        return deny("no-iac-destroy: " + ", ".join(f"`{r}`" for r in found) + " inside a loop, xargs, "
                    "parallel or watch runs an unknown number of times, and each run needs its own "
                    "approval. Run it once, on its own, after looking at what it would remove.")
    try:
        approved, spent = claim(payload, {RULES[r][0]: len(found[r]) for r in found})
    except (OSError, ValueError) as e:
        return deny(f"no-iac-destroy: cannot read the session transcript to look for the user's approval, or "
                    f"record it as spent ({e}), so `{cmd.strip()}` is denied. Ask the user to run it themselves.")
    if spent:
        return None
    parts = []
    for r in found:
        label, what, cost, instead = RULES[r]
        n, have = len(found[r]), len(approved[label])
        if have >= n:
            continue
        parts.append(
            f"`{cmd.strip()}` {what} (`{r}`)"
            + (f"; it runs the rule {n} times and has {have} unspent approvals" if n > 1 else "")
            + f". Cost: {cost}. Instead, look first: {instead.format(tool=found[r][0])}."
            f" If the user then wants this run, call AskUserQuestion: give the exact command, why it must run "
            f"now and the cost above, with one option labelled exactly \"{label}\" and one to skip. "
            "One approval is one run; ask again before running it again.")
    return deny("no-iac-destroy: " + "\n\n".join(parts))
