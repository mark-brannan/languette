@python @family
Feature: data
  The family of guards for stored records erased, wherever they live. A
  family is a configuration key that groups guards; this file holds the
  verdicts the family gives, run against every guard together.

  Scenarios tagged @planned are verdicts no guard gives yet: they are
  expected to fail, so they never fail CI, and a row that starts passing
  shows as XPASS. The verdicts there are proposals, not rulings. Every other
  scenario is allowed by design and fails CI when a guard stops allowing it.

  Scenario Outline: reading what a forge holds is allowed
    When the agent runs `<command>`
    Then the guard is silent

    Examples:
      | command                                         | note |
      | gh release list --repo someone/project          |      |
      | gh api repos/someone/project/hooks              | a GET |
      | gh variable list                                |      |
      | glab release view v1.2.0                        |      |
      | gh issue comment 12 --body "gh repo delete is not something to run" | prose |

  @planned
  Scenario Outline: something only GitHub holds is deleted
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                   | verdict | note                         |
      | gh repo delete someone/project --yes                      | asks    |                              |
      | gh repo archive someone/project --yes                     | asks    |                              |
      | gh release delete v1.2.0 --yes                            | asks    |                              |
      | gh release delete v2.0.0-rc1 --cleanup-tag -y             | asks    | the tag goes too             |
      | gh release delete-asset v1.2.0 app.tar.gz --yes           | asks    |                              |
      | gh variable delete REGION                                 | asks    |                              |
      | gh gist delete 0123abcd --yes                             | asks    |                              |
      | gh api -X DELETE repos/someone/project/hooks/56           | asks    | a webhook                    |
      | gh api -X DELETE repos/someone/project/releases/90        | asks    |                              |
      | gh api --method DELETE repos/someone/project/actions/variables/REGION | asks |                    |
      | gh api -X DELETE repos/someone/project                    | asks    | the repository itself        |
      | gh api -X DELETE repos/someone/project/git/refs/tags/v1   | asks    | a tag on the remote          |

  @planned
  Scenario Outline: something only GitLab or Azure DevOps holds is deleted
    When the agent runs `<command>`
    Then the guard <verdict>

    Examples:
      | command                                                         | verdict | note |
      | glab repo delete group/project --yes                            | asks    |      |
      | glab repo archive group/project                                 | asks    |      |
      | glab release delete v1.2.0 --yes                                | asks    |      |
      | glab api -X DELETE projects/42                                  | asks    |      |
      | glab api --method DELETE projects/42/hooks/7                    | asks    |      |
      | glab api -X DELETE projects/42/releases/v1.2.0                  | asks    |      |
      | gitlab-rake gitlab:cleanup:orphan_job_artifact_files DRY_RUN=false | asks |      |
      | gitlab-rails runner 'Project.find(42).destroy'                  | asks    |      |
      | az devops invoke --area git --resource repositories --http-method DELETE --route-parameters project=web repositoryId=9 | asks | |
