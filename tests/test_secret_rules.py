"""languette/secret_rules.py: every rule compiles, ids are unique, each rule finds a
plausible sample of its own secret (bare and inside TOKEN=<sample>), and common
non-secrets match nothing. Every line holding a sample carries gitleaks:allow, so
the repo's own secret scan skips it."""

import random
import re
import string

import pytest

from languette.secret_rules import RULES

_R = random.Random(20260101)
_ALNUM, _LOWER, _HEX = string.ascii_letters + string.digits, string.ascii_letters, "0123456789abcdef"
_AGE, _AWS = "QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L", string.ascii_uppercase + "234567"


def pick(chars, n):
    return "".join(_R.choice(chars) for _ in range(n))


def A(n): return pick(_ALNUM, n)
def L(n): return pick(_LOWER, n)
def H(n): return pick(_HEX, n)
def D(n): return pick(string.digits, n)


SAMPLES = {
    "github-pat": "ghp_" + A(36),  # gitleaks:allow
    "github-fine-grained-pat": "github_pat_" + A(82),  # gitleaks:allow
    "github-oauth": "gho_" + A(36),  # gitleaks:allow
    "github-app-token": "ghs_" + A(36),  # gitleaks:allow
    "github-refresh-token": "ghr_" + A(36),  # gitleaks:allow
    "aws-access-token": "AKIA" + pick(_AWS, 16),  # gitleaks:allow
    "gcp-api-key": "AIza" + A(35),  # gitleaks:allow
    "slack-bot-token": "xoxb-" + D(11) + "-" + D(11) + "-" + A(24),  # gitleaks:allow
    "slack-user-token": "xoxp-" + D(11) + "-" + D(11) + "-" + D(11) + "-" + A(30),  # gitleaks:allow
    "slack-app-token": "xapp-1-A" + A(9).upper() + "-" + D(12) + "-" + H(30),  # gitleaks:allow
    "slack-webhook-url": "https://hooks.slack.com/services/" + A(43),  # gitleaks:allow
    "stripe-access-token": "sk_live_" + A(24),  # gitleaks:allow
    "openai-api-key": "sk-proj-" + A(74) + "T3BlbkFJ" + A(74),  # gitleaks:allow
    "anthropic-api-key": "sk-ant-api03-" + A(93) + "AA",  # gitleaks:allow
    "anthropic-admin-api-key": "sk-ant-admin01-" + A(93) + "AA",  # gitleaks:allow
    "npm-access-token": "npm_" + A(36),  # gitleaks:allow
    "pypi-upload-token": "pypi-AgEIcHlwaS5vcmc" + A(60),  # gitleaks:allow
    "huggingface-access-token": "hf_" + L(34),  # gitleaks:allow
    "huggingface-organization-api-token": "api_org_" + L(34),  # gitleaks:allow
    "sendgrid-api-token": "SG." + A(66),  # gitleaks:allow
    "gitlab-pat": "glpat-" + A(20),  # gitleaks:allow
    "gitlab-pat-routable": "glpat-" + A(30) + ".01" + H(7),  # gitleaks:allow
    "gitlab-runner-authentication-token": "glrt-" + A(20),  # gitleaks:allow
    "digitalocean-pat": "dop_v1_" + H(64),  # gitleaks:allow
    "digitalocean-access-token": "doo_v1_" + H(64),  # gitleaks:allow
    "digitalocean-refresh-token": "dor_v1_" + H(64),  # gitleaks:allow
    "private-key": "-----BEGIN RSA PRIVATE KEY-----",  # gitleaks:allow
    "jwt": "eyJ" + A(20) + ".eyJ" + A(20) + "." + A(24),  # gitleaks:allow
    "telegram-bot-api-token": D(10) + ":A" + A(34),  # gitleaks:allow
    "shopify-access-token": "shpat_" + H(32),  # gitleaks:allow
    "shopify-custom-access-token": "shpca_" + H(32),  # gitleaks:allow
    "shopify-private-app-access-token": "shppa_" + H(32),  # gitleaks:allow
    "shopify-shared-secret": "shpss_" + H(32),  # gitleaks:allow
    "square-access-token": "EAAA" + A(40),  # gitleaks:allow
    "vault-batch-token": "hvb." + A(150),  # gitleaks:allow
    "vault-service-token": "hvs." + A(100),  # gitleaks:allow
    "databricks-api-token": "dapi" + H(32),  # gitleaks:allow
    "postman-api-token": "PMAK-" + H(24) + "-" + H(34),  # gitleaks:allow
    "doppler-api-token": "dp.pt." + A(43),  # gitleaks:allow
    "age-secret-key": "AGE-SECRET-KEY-1" + pick(_AGE, 58),  # gitleaks:allow
    "sentry-org-token": "sntrys_eyJpYXQiO" + A(20) + "LCJyZWdpb25fdXJs" + A(20) + "_" + A(43),  # gitleaks:allow
    "sentry-user-token": "sntryu_" + H(64),  # gitleaks:allow
    "linear-api-key": "lin_api_" + A(40),  # gitleaks:allow
    "grafana-api-key": "eyJrIjoi" + A(80),  # gitleaks:allow
    "grafana-cloud-api-token": "glc_" + A(40),  # gitleaks:allow
    "grafana-service-account-token": "glsa_" + A(32) + "_" + H(8),  # gitleaks:allow
    "azure-ad-client-secret": A(3) + "8Q~" + A(34),  # gitleaks:allow
    "mailgun-private-api-token": "key-" + H(32),  # gitleaks:allow
    "mailgun-pub-key": "pubkey-" + H(32),  # gitleaks:allow
    "twilio-api-key": "SK" + H(32),  # gitleaks:allow
}

NON_SECRETS = ["README.md", "main", "--verbose", "-rf", "https://example.com/path", "git@github.com:owner/repo.git",
               "HEAD~3", "src/languette/scan.py", "KEY=value", "TOKEN=", "sk-learn", "ghp_short", "AKIA",
               "node_modules/.bin/eslint", "2026-01-01T00:00:00Z", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"]


def test_every_rule_compiles_and_is_described():
    assert RULES
    for rule in RULES:
        assert isinstance(rule.regex, re.Pattern), rule.id
        assert rule.id.strip() and rule.description.strip(), rule.id
        assert isinstance(rule.entropy, float) and rule.entropy >= 0.0, rule.id
        if "secret" in rule.regex.groupindex:
            assert rule.regex.groups >= 1, rule.id


def test_rule_ids_are_unique():
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids))


def test_every_rule_has_a_sample_and_every_sample_a_rule():
    assert set(SAMPLES) == {r.id for r in RULES}


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_a_sample_secret_is_found_bare_and_embedded(rule):
    sample = SAMPLES[rule.id]
    for word in (sample, "TOKEN=" + sample, "--token=" + sample, "https://u:" + sample + "@host/x"):
        m = rule.regex.search(word)
        assert m, f"{rule.id} missed {word!r}"
        secret = m.group("secret") if "secret" in rule.regex.groupindex else m.group(0)
        assert secret == sample, f"{rule.id}: secret {secret!r} is not the sample"


@pytest.mark.parametrize("word", NON_SECRETS)
def test_common_non_secrets_match_no_rule(word):
    assert [r.id for r in RULES if r.regex.search(word)] == []
