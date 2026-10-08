r"""Known secret shapes, ported from gitleaks (https://github.com/gitleaks/gitleaks).

Each rule is the token-shaped part of a gitleaks rule (config/gitleaks.toml): a
vendor prefix or fixed format that identifies a secret by itself. Gitleaks'
context rules (a key name, then an assignment, then any value) are not here.
The regexes are Go RE2 converted to Python `re`: a mid-pattern `(?i)` became a
scoped `(?i:...)`, the capture group holding the secret is named `secret`, and
gitleaks' trailing terminator (quote, whitespace, `;` or end of text) became the
lookahead `(?!\w)`, so a match works inside a longer shell word such as
`TOKEN=<secret>`. Rule ids and descriptions are gitleaks' own.

Altered beyond that:
  private-key  the header line only; the body spans lines, a shell word cannot.
  azure-ad-client-secret  the leading quote-or-space boundary is a lookbehind
      for "not a token character", so `=`, `:` and `@` before it are fine.
  telegram-bot-api-token, mailgun-private-api-token, mailgun-pub-key  gitleaks
      requires the vendor name near the value; here the value shape stands alone
      (the leading `\b` replaces the name), so these three fire on shape only.

The gitleaks licence follows, as it requires.

MIT License

Copyright (c) 2019 Zachary Rice

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import re
from collections import namedtuple

# id: gitleaks' rule id. description: gitleaks' text. regex: compiled, used with
# regex.search(word) on one shell word; group "secret" if present (else group 0)
# is the secret. entropy: gitleaks' minimum Shannon entropy for that secret, 0.0 when none.
Rule = namedtuple("Rule", "id description regex entropy")

# The token has ended: the next character cannot continue a token.
_END = r"(?!\w)"

RULES = (
    Rule("github-pat", "Uncovered a GitHub Personal Access Token, potentially leading to unauthorized repository access and sensitive content exposure.",
         re.compile(r"ghp_[0-9a-zA-Z]{36}"), 3.0),
    Rule("github-fine-grained-pat", "Found a GitHub Fine-Grained Personal Access Token, risking unauthorized repository access and code manipulation.",
         re.compile(r"github_pat_\w{82}"), 3.0),
    Rule("github-oauth", "Discovered a GitHub OAuth Access Token, posing a risk of compromised GitHub account integrations and data leaks.",
         re.compile(r"gho_[0-9a-zA-Z]{36}"), 3.0),
    Rule("github-app-token", "Identified a GitHub App Token, which may compromise GitHub application integrations and source code security.",
         re.compile(r"(?:ghu|ghs)_[0-9a-zA-Z]{36}"), 3.0),
    Rule("github-refresh-token", "Detected a GitHub Refresh Token, which could allow prolonged unauthorized access to GitHub services.",
         re.compile(r"ghr_[0-9a-zA-Z]{36}"), 3.0),
    Rule("aws-access-token", "Identified a pattern that may indicate AWS credentials, risking unauthorized cloud resource access and data breaches on AWS platforms.",
         re.compile(r"\b(?P<secret>(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b"), 3.0),
    Rule("gcp-api-key", "Uncovered a GCP API key, which could lead to unauthorized access to Google Cloud services and data breaches.",
         re.compile(r"\b(?P<secret>AIza[\w-]{35})" + _END), 4.0),
    Rule("slack-bot-token", "Identified a Slack Bot token, which may compromise bot integrations and communication channel security.",
         re.compile(r"xoxb-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*"), 3.0),
    Rule("slack-user-token", "Found a Slack User token, posing a risk of unauthorized user impersonation and data access within Slack workspaces.",
         re.compile(r"xox[pe](?:-[0-9]{10,13}){3}-[a-zA-Z0-9-]{28,34}"), 2.0),
    Rule("slack-app-token", "Detected a Slack App-level token, risking unauthorized access to Slack applications and workspace data.",
         re.compile(r"(?i)xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]+"), 2.0),
    Rule("slack-webhook-url", "Discovered a Slack Webhook, which could lead to unauthorized message posting and data leakage in Slack channels.",
         re.compile(r"(?:https?://)?hooks.slack.com/(?:services|workflows|triggers)/[A-Za-z0-9+/]{43,56}"), 0.0),
    Rule("stripe-access-token", "Found a Stripe Access Token, posing a risk to payment processing services and sensitive financial data.",
         re.compile(r"\b(?P<secret>(?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})" + _END), 2.0),
    Rule("openai-api-key", "Found an OpenAI API Key, posing a risk of unauthorized access to AI services and data manipulation.",
         re.compile(r"\b(?P<secret>sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})T3BlbkFJ(?:[A-Za-z0-9_-]{74}|[A-Za-z0-9_-]{58})|sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20})" + _END), 3.0),
    Rule("anthropic-api-key", "Identified an Anthropic API Key, which may compromise AI assistant integrations and expose sensitive data to unauthorized access.",
         re.compile(r"\b(?P<secret>sk-ant-api03-[a-zA-Z0-9_\-]{93}AA)" + _END), 0.0),
    Rule("anthropic-admin-api-key", "Detected an Anthropic Admin API Key, risking unauthorized access to administrative functions and sensitive AI model configurations.",
         re.compile(r"\b(?P<secret>sk-ant-admin01-[a-zA-Z0-9_\-]{93}AA)" + _END), 0.0),
    Rule("npm-access-token", "Uncovered an npm access token, potentially compromising package management and code repository access.",
         re.compile(r"(?i)\b(?P<secret>npm_[a-z0-9]{36})" + _END), 2.0),
    Rule("pypi-upload-token", "Discovered a PyPI upload token, potentially compromising Python package distribution and repository integrity.",
         re.compile(r"pypi-AgEIcHlwaS5vcmc[\w-]{50,1000}"), 3.0),
    Rule("huggingface-access-token", "Discovered a Hugging Face Access token, which could lead to unauthorized access to AI models and sensitive data.",
         re.compile(r"\b(?P<secret>hf_(?i:[a-z]{34}))" + _END), 2.0),
    Rule("huggingface-organization-api-token", "Uncovered a Hugging Face Organization API token, potentially compromising AI organization accounts and associated data.",
         re.compile(r"\b(?P<secret>api_org_(?i:[a-z]{34}))" + _END), 2.0),
    Rule("sendgrid-api-token", "Detected a SendGrid API token, posing a risk of unauthorized email service operations and data exposure.",
         re.compile(r"\b(?P<secret>SG\.(?i:[a-z0-9=_\-\.]{66}))" + _END), 2.0),
    Rule("gitlab-pat", "Identified a GitLab Personal Access Token, risking unauthorized access to GitLab repositories and codebase exposure.",
         re.compile(r"glpat-[\w-]{20}"), 3.0),
    Rule("gitlab-pat-routable", "Identified a GitLab Personal Access Token (routable), risking unauthorized access to GitLab repositories and codebase exposure.",
         re.compile(r"\bglpat-[0-9a-zA-Z_-]{27,300}\.[0-9a-z]{2}[0-9a-z]{7}\b"), 4.0),
    Rule("gitlab-runner-authentication-token", "Discovered a GitLab Runner Authentication Token, posing a risk to CI/CD pipeline integrity and unauthorized access.",
         re.compile(r"glrt-[0-9a-zA-Z_\-]{20}"), 3.0),
    Rule("digitalocean-pat", "Discovered a DigitalOcean Personal Access Token, posing a threat to cloud infrastructure security and data privacy.",
         re.compile(r"\b(?P<secret>dop_v1_[a-f0-9]{64})" + _END), 3.0),
    Rule("digitalocean-access-token", "Found a DigitalOcean OAuth Access Token, risking unauthorized cloud resource access and data compromise.",
         re.compile(r"\b(?P<secret>doo_v1_[a-f0-9]{64})" + _END), 3.0),
    Rule("digitalocean-refresh-token", "Uncovered a DigitalOcean OAuth Refresh Token, which could allow prolonged unauthorized access and resource manipulation.",
         re.compile(r"(?i)\b(?P<secret>dor_v1_[a-f0-9]{64})" + _END), 0.0),
    Rule("private-key", "Identified a Private Key, which may compromise cryptographic security and sensitive data encryption.",
         re.compile(r"(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----"), 0.0),
    Rule("jwt", "Uncovered a JSON Web Token, which may lead to unauthorized access to web applications and sensitive user data.",
         re.compile(r"\b(?P<secret>ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\\_-]{17,}\.(?:[a-zA-Z0-9\/\\_-]{10,}={0,2})?)" + _END), 3.0),
    Rule("telegram-bot-api-token", "Detected a Telegram Bot API Token, risking unauthorized bot operations and message interception on Telegram.",
         re.compile(r"\b(?P<secret>[0-9]{5,16}:A(?i:[a-z0-9_\-]{34}))" + _END), 0.0),
    Rule("shopify-access-token", "Uncovered a Shopify access token, which could lead to unauthorized e-commerce platform access and data breaches.",
         re.compile(r"shpat_[a-fA-F0-9]{32}"), 2.0),
    Rule("shopify-custom-access-token", "Detected a Shopify custom access token, potentially compromising custom app integrations and e-commerce data security.",
         re.compile(r"shpca_[a-fA-F0-9]{32}"), 2.0),
    Rule("shopify-private-app-access-token", "Identified a Shopify private app access token, risking unauthorized access to private app data and store operations.",
         re.compile(r"shppa_[a-fA-F0-9]{32}"), 2.0),
    Rule("shopify-shared-secret", "Found a Shopify shared secret, posing a risk to application authentication and e-commerce platform security.",
         re.compile(r"shpss_[a-fA-F0-9]{32}"), 2.0),
    Rule("square-access-token", "Detected a Square Access Token, risking unauthorized payment processing and financial transaction exposure.",
         re.compile(r"\b(?P<secret>(?:EAAA|sq0atp-)[\w-]{22,60})" + _END), 2.0),
    Rule("vault-batch-token", "Detected a Vault Batch Token, risking unauthorized access to secret management services and sensitive data.",
         re.compile(r"\b(?P<secret>hvb\.[\w-]{138,300})" + _END), 4.0),
    Rule("vault-service-token", "Identified a Vault Service Token, potentially compromising infrastructure security and access to sensitive credentials.",
         re.compile(r"\b(?P<secret>(?:hvs\.[\w-]{90,120}|s\.(?i:[a-z0-9]{24})))" + _END), 3.5),
    Rule("databricks-api-token", "Uncovered a Databricks API token, which may compromise big data analytics platforms and sensitive data processing.",
         re.compile(r"\b(?P<secret>dapi[a-f0-9]{32}(?:-\d)?)" + _END), 3.0),
    Rule("postman-api-token", "Uncovered a Postman API token, potentially compromising API testing and development workflows.",
         re.compile(r"\b(?P<secret>PMAK-(?i:[a-f0-9]{24}\-[a-f0-9]{34}))" + _END), 3.0),
    Rule("doppler-api-token", "Discovered a Doppler API token, posing a risk to environment and secrets management security.",
         re.compile(r"dp\.pt\.(?i:[a-z0-9]{43})"), 2.0),
    Rule("age-secret-key", "Discovered a potential Age encryption tool secret key, risking data decryption and unauthorized access to sensitive information.",
         re.compile(r"AGE-SECRET-KEY-1[QPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{58}"), 0.0),
    Rule("sentry-org-token", "Found a Sentry.io Organization Token, risking unauthorized access to error tracking services and sensitive application data.",
         re.compile(r"\b(?P<secret>sntrys_eyJpYXQiO[a-zA-Z0-9+/]{10,200}(?:LCJyZWdpb25fdXJs|InJlZ2lvbl91cmwi|cmVnaW9uX3VybCI6)[a-zA-Z0-9+/]{10,200}={0,2}_[a-zA-Z0-9+/]{43})(?![a-zA-Z0-9+/])"), 4.5),
    Rule("sentry-user-token", "Found a Sentry.io User Token, risking unauthorized access to error tracking services and sensitive application data.",
         re.compile(r"\b(?P<secret>sntryu_[a-f0-9]{64})" + _END), 3.5),
    Rule("linear-api-key", "Detected a Linear API Token, posing a risk to project management tools and sensitive task data.",
         re.compile(r"lin_api_(?i:[a-z0-9]{40})"), 2.0),
    Rule("grafana-api-key", "Identified a Grafana API key, which could compromise monitoring dashboards and sensitive data analytics.",
         re.compile(r"(?i)\b(?P<secret>eyJrIjoi[A-Za-z0-9]{70,400}={0,3})" + _END), 3.0),
    Rule("grafana-cloud-api-token", "Found a Grafana cloud API token, risking unauthorized access to cloud-based monitoring services and data exposure.",
         re.compile(r"(?i)\b(?P<secret>glc_[A-Za-z0-9+/]{32,400}={0,3})" + _END), 3.0),
    Rule("grafana-service-account-token", "Discovered a Grafana service account token, posing a risk of compromised monitoring services and data integrity.",
         re.compile(r"(?i)\b(?P<secret>glsa_[A-Za-z0-9]{32}_[A-Fa-f0-9]{8})" + _END), 3.0),
    Rule("azure-ad-client-secret", "Azure AD Client Secret",
         re.compile(r"(?<![a-zA-Z0-9_~.])(?P<secret>[a-zA-Z0-9_~.]{3}\dQ~[a-zA-Z0-9_~.-]{31,34})(?![a-zA-Z0-9_~.-])"), 3.0),
    Rule("mailgun-private-api-token", "Found a Mailgun private API token, risking unauthorized email service operations and data breaches.",
         re.compile(r"\b(?P<secret>key-[a-f0-9]{32})" + _END), 0.0),
    Rule("mailgun-pub-key", "Discovered a Mailgun public validation key, which could expose email verification processes and associated data.",
         re.compile(r"\b(?P<secret>pubkey-[a-f0-9]{32})" + _END), 0.0),
    Rule("twilio-api-key", "Found a Twilio API Key, posing a risk to communication services and sensitive customer interaction data.",
         re.compile(r"SK[0-9a-fA-F]{32}"), 3.0),
)
