@python
Feature: guard-secrets
  A credential pasted into a Bash command is in the transcript already, and in
  whatever the command commits, prints or posts next. A word holding a known
  token shape (gitleaks' list, ported) is denied. A value only its context
  names as a credential (`DB_PASSWORD=...`, `--password ...`, a URL with a
  password) is asked about, since the shape alone cannot tell a secret from a
  hostname. Entropy only confirms a hit: a placeholder of x's is silence.
  Heredoc bodies and nested shell text are read too. The project may extend
  the list in .languette/secrets.json.

  Scenario Outline: the reason names the shape, shortens the value and says what to do instead
    When the agent runs `<command>`
    Then the guard denies, naming "<naming>"

    Examples:
      | command                            | naming                       | note           |
      | export GITHUB_TOKEN=ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx | GitHub Personal Access Token | gitleaks:allow |
      | export GITHUB_TOKEN=ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx | `ghp_…`                      | gitleaks:allow |
      | export GITHUB_TOKEN=ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx | read it from the environment | gitleaks:allow |

  Scenario Outline: a known token shape is denied wherever it sits
    When the agent runs `<command>`
    Then the guard denies

    Examples:
      | command                                                              | note                                   |
      | git commit -m "add token ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx"                                       | prose, but posted: gitleaks:allow      |
      | curl -H "Authorization: Bearer ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx" https://api.github.com/user     | inside a quoted header: gitleaks:allow |
      | echo "AWS_ACCESS_KEY_ID=AKIAJLLZVLZQ6KHGX4TA" >> .env                               | gitleaks:allow                         |
      | export SESSION_JWT=eyJRdHtmHvLUbHdl0nl2wCb.eyJK7DB82GL3AQ8h7mDXT9j.MBBc58LOBUxytTVN3hRhwllh | gitleaks:allow |
      | AGE_KEY=AGE-SECRET-KEY-1M3QJM0F9LDM85ZRJLWWFSA6GY6DJDRXUEY6DSXELLN40HVPQ9Y36J2CNYY ./run | gitleaks:allow |
      | ssh host 'export GH_TOKEN=ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx'                                      | nested shell text: gitleaks:allow      |
      | gh issue comment 1 --body "use ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx"                                 | posted: gitleaks:allow                 |

  Scenario: a heredoc body is read
    When the agent runs:
      """
      cat <<'EOF' > .env
      GITHUB_TOKEN=ghp_WIGVIY73i8FbiZaMfOrZmcKUHMmOPgxrVYyx # gitleaks:allow
      EOF
      """
    Then the guard denies

  Scenario: a private key header is a secret whatever follows it
    When the agent runs:
      """
      cat > id_rsa <<'EOF'
      -----BEGIN RSA PRIVATE KEY----- gitleaks:allow
      MIIEowIBAAKCAQEA
      -----END RSA PRIVATE KEY-----
      EOF
      """
    Then the guard denies

  Scenario Outline: a value only named as a credential is asked about
    When the agent runs `<command>`
    Then the guard asks

    Examples:
      | command                                                       | note                      |
      | mysql --password=Zq9kLm2pQ7rXv4Tn -e 'select 1'                             | gitleaks:allow            |
      | mysql --password Zq9kLm2pQ7rXv4Tn -e 'select 1'                             | gitleaks:allow            |
      | DB_PASSWORD=Zq9kLm2pQ7rXv4Tn ./manage.py migrate                            | gitleaks:allow            |
      | export API_KEY=S3cr3tPa55w0rdXy                                            | gitleaks:allow            |
      | psql postgres://app:S3cr3tPa55w0rdXy@db.example.com/app                    | URL password: gitleaks:allow |
      | curl -H "X-Api-Key: S3cr3tPa55w0rdXy" https://example.com                  | gitleaks:allow            |
      | githubToken=Zq9kLm2pQ7rXv4Tn ./run                                          | camelCase key: gitleaks:allow |
      | curl -u app:S3cr3tPa55w0rdXy https://example.com                           | user:password: gitleaks:allow |

  Scenario Outline: an indented data line is read whole: indent, export and quotes set aside
    When the agent runs:
      """
      cat <<'EOF' > config
        <line>
      EOF
      """
    Then the guard asks

    Examples:
      | line                            | note                  |
      | password: Zq9kLm2pQ7rXv4Tn      | YAML: gitleaks:allow  |
      | "password": "Zq9kLm2pQ7rXv4Tn", | JSON: gitleaks:allow  |
      | export API_KEY=Zq9kLm2pQ7rXv4Tn | .env: gitleaks:allow  |

  Scenario Outline: no credential, no verdict
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                                        | note                                   |
      | grep -n TOKEN= config.py                                       | a key name, no value                   |
      | export TOKEN="$GITHUB_TOKEN"                                   | a variable, not a literal              |
      | export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx     | the shape, with a placeholder's entropy: gitleaks:allow |
      | export API_KEY=xxxxxxxxxxxxxxxx                                | gitleaks:allow                         |
      | mysql --password '<password>' -e 'select 1'                    | a placeholder                          |
      | mkdir -p build && ssh -p 2222 host                             | -p is not a password here              |
      | git commit -m "fix token refresh on expiry"                    | prose about tokens                     |
      | DB_PASSWORD=secret ./run                                       | too short to be judged                 |
      | export AUTH_TOKEN_FILE=/run/secrets/token                      | a path                                 |
      | docker login -u me --password-stdin < pw.txt                   | the safe way                           |
      | sudo -u root ls                                                | -u names a user, no password           |
      | bypass=Zq9kLm2pQ7rXv4Tn ./run                                  | ends in pass, not a key: gitleaks:allow |
      | compass=Zq9kLm2pQ7rXv4Tn ./run                                 | ends in pass, not a key: gitleaks:allow |
      | echo done                                                      |                                        |

  Scenario: the project's own patterns extend the list
    Given a project directory
    And the file ".languette/secrets.json" holds:
      """
      {"patterns": [{"id": "acme-key", "description": "Acme API key", "regex": "acme_[a-z0-9]{24}"}]}
      """
    When the agent runs `echo acme_skzop8bx8jbs1x04d6233g6w`
    Then the guard denies, naming "Acme API key"

  Scenario: a project file that does not parse denies until it is fixed
    Given a project directory
    And the file ".languette/secrets.json" holds:
      """
      {"patterns": [{"id": "bad", "regex": "("}]}
      """
    When the agent runs `echo hello`
    Then the guard denies, naming "does not compile"

  Scenario: a project pattern may not reuse a shipped rule's id
    Given a project directory
    And the file ".languette/secrets.json" holds:
      """
      {"patterns": [{"id": "github-pat", "regex": "acme_[a-z0-9]{24}"}]}
      """
    When the agent runs `echo hello`
    Then the guard denies, naming "shipped rule"
