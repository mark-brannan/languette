## Summary

A credential can leave the machine three ways a hook can see: committed, printed into the transcript, or posted. It can also land in languette's own records, if a metrics writer stores the commands it judged. Both needs are the same question asked of the same parsed command: *which of these words is a secret?*

This proposes one detector, a pure function over the parser's words, returning findings. `guard-secrets` (today a two-line stub) feeds its findings to the verdict; the metrics writer uses the same findings to mask before it writes. One list, one set of fixtures, two consumers. Part of #76 (guards and verdict as pure functions); pairs with the metrics issue once it has a number.

## What is known

**Prior art layers three methods.** gitleaks, detect-secrets and secretlint each combine known token shapes (`ghp_…`, `AKIA…`, `sk-…`, PEM headers), context (`TOKEN=`, `Authorization:`, `--password`) and entropy, as a shipped default list that the user extends with their own patterns. Nothing here invents a method; the work is choosing the mix and porting the list.

**languette's edge is position.** The parser ladder (#4) gives words, quotes resolved and heredocs read, so the detector matches per word and the writer redacts per word. Prior art runs regexes over raw text; a mask over raw text misses a value split by quoting or doubles up on one that appears twice. A finding here is an index into the word stream, not an offset into a string.

**stdlib only** (Runtime dependencies ruling, `docs/decisions.md`). The list is ported, not imported. Licences, checked 2026-10-07:

| Source | Licence | Portable? |
|---|---|---|
| gitleaks | MIT | yes, with attribution |
| secretlint | MIT | yes, with attribution |
| detect-secrets (Yelp) | Apache-2.0 | yes, with attribution and NOTICE |
| trufflehog | AGPL-3.0 | no |
| secrets-patterns-db | CC-BY-SA-4.0 | no (share-alike) |

## Shape

- `languette/secrets.py`: `findings(scan) -> [Finding]`, pure. A `Finding` names the word index, the rule that fired and how it fired (shape, context, entropy). No I/O; the scan is the input.
- `guard-secrets`: calls the detector, reports its findings; the verdict decides the action, as the epic has it.
- Metrics writer: calls the detector, masks the words it names, writes the masked stream.
- Default list in the repo, each rule carrying its source and licence line. A user list in `.languette/secrets.json` extends the default, as gitleaks' `extend` does; it never replaces it.
- `fixtures/secrets.jsonl`: `(command, findings)` rows, the contract for both consumers and for both engines (#19).

## May be considered

Choices for the implementer, worth a line in the PR, none gating this issue:

- The method mix: whether entropy fires alone or only confirms a context hit; which gitleaks rules make the first cut.
- False-positive tolerance per consumer: a guard that denies pays for a false positive in a blocked command; a writer that masks pays in a lost metric. The same findings may map to different actions, and the detector's finding can carry confidence to let the verdict do that.
- What the mask covers: the value after `=`, or the whole word.
- Where the user list is enforced in the ladder's awk rung, whose words are less exact.
- Whether the secret-scan workflow (gitleaks, trufflehog over history) and this detector should share the user list, or stay separate.

## Not in scope

Scanning files the command names, or stdout after the fact. The detector reads the command as parsed; a PostToolUse read of output is its own issue if wanted.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
