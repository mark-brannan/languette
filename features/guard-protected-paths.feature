@python
Feature: guard-protected-paths
  The guard for paths the repo lists: any agent write to one is denied. The
  repo lists the paths; the list starts empty. It is a stub today: it is not
  registered and judges nothing yet.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every
  scenario here is planned while the guard is a stub.

  # An allow row, written ahead: until the guard is registered the runner
  # denies every call to it (no guard is named so), so it is @planned too.
  # Drop the tag when the guard is registered.
  @planned
  Scenario Outline: a path no one listed is the agent's to write
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                          | note                                    |
      | echo x > notes.txt               | the list starts empty                   |
      | cat notes.txt                    | a read                                  |

  # The step vocabulary has no Given that lists a path, so these rows cannot
  # set the list yet; each assumes the repo lists "secrets/" and "deploy.yml".
  @planned
  Scenario Outline: an agent write to a listed path is denied
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                          | verdict | note                         |
      | echo x > secrets/token           | denies  | a redirect                   |
      | echo x >> deploy.yml             | denies  | an append                    |
      | tee deploy.yml < new.yml         | denies  | tee                          |
      | cp new.yml deploy.yml            | denies  | a copy onto it               |
      | sed -i 's/a/b/' deploy.yml       | denies  | an in-place edit             |
      | rm secrets/token                 | denies  | a delete is a write          |

  @planned
  Scenario Outline: reading a listed path is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                          | note                         |
      | cat secrets/token                | reads are not writes         |
