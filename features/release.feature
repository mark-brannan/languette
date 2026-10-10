@python @family
Feature: release
  The family of guards for packages strangers install, and their
  retraction. A family is a configuration key that groups guards; this file
  holds the verdicts the family gives, run against every guard together.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every other
  scenario is allowed by design and fails CI when a guard stops allowing it.

  Scenario Outline: building and rehearsing a release is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                      | note        |
      | npm pack                     |             |
      | npm publish --dry-run        |             |
      | cargo publish --dry-run      |             |
      | poetry build                 |             |
      | npm install                  | local       |
      | git commit -m "release: npm publish runs in CI, not here" | prose |

  @planned
  Scenario Outline: a package is published where strangers install it
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                 | verdict | note |
      | npm publish                             | asks    |      |
      | npm publish --access public --tag next  | asks    |      |
      | yarn npm publish                        | asks    |      |
      | yarn publish --new-version 1.2.0        | asks    |      |
      | pnpm publish --no-git-checks            | asks    |      |
      | cargo publish                           | asks    |      |
      | ./gradlew publish                       | asks    |      |
      | gradle publishToMavenCentral            | asks    |      |
      | poetry publish --build                  | asks    |      |
      | mvn deploy -DskipTests                  | asks    |      |
      | mvn release:perform                     | asks    |      |

  @planned
  Scenario Outline: a published package or image is retracted
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                   | verdict | note                         |
      | cargo yank --version 1.2.0                                | asks    | new lockfiles cannot pick it |
      | npm unpublish some-package@1.2.0                          | asks    |                              |
      | npm deprecate some-package@"<2" "use 2.x"                 | asks    |                              |
      | npm dist-tag rm some-package next                         | asks    |                              |
      | circleci orb delete someone/deploy                        | asks    |                              |
      | az acr repository untag --name registry --image web:1.2.0 | asks    |                              |
      | aws ecr batch-delete-image --repository-name web --image-ids imageTag=1.2.0 | asks |              |
