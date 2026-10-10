@python
Feature: everyday-commands
  Commands agents run all day, with every guard on: each passes, and no guard
  says a word. Rows are anonymized from the October 2026 replay of 101,671
  agent commands (require-well-formed.feature). A guard that fires only on a
  project's own configuration is left unconfigured here.

  Background:
    Given a project directory
    And the working directory is "{PROJ}"
    And the stubs "gh" and "timeout" are first on PATH

  Scenario Outline: an everyday command passes every guard
    When the agent runs `<command>`
    Then the guard is silent

    Examples: git
      | command                                         |
      | git status                                      |
      | git status --short                              |
      | git diff --stat                                 |
      | git diff HEAD~1 -- src/app.py                   |
      | git log --oneline -10                           |
      | git show HEAD --stat                            |
      | git blame -L 10,20 src/app.py                   |
      | git branch --show-current                       |
      | git rev-parse --show-toplevel                   |
      | git fetch origin                                |
      | git switch -c fix/empty-list origin/main        |
      | git add src/app.py tests/test_app.py            |
      | git commit -m "fix: handle an empty list"       |
      | git stash list                                  |
      | git worktree list                               |
      | git pull --rebase                               |
      | git push -u origin fix/empty-list               |

    Examples: gh
      | command                                         |
      | gh pr list --state open                         |
      | gh pr view 12 --json title,body                 |
      | gh pr checks 12                                 |
      | gh pr diff 12                                   |
      | gh issue view 34 --comments                     |
      | gh run list -L 5                                |
      | gh api repos/o/r/pulls/12/comments              |

    Examples: tests and builds
      | command                                         |
      | pytest -q tests/test_app.py                     |
      | python3 -m pytest -x -k parse                   |
      | uv run pytest                                   |
      | npm test                                        |
      | npm ci                                          |
      | npm run build                                   |
      | pip install -r requirements.txt                 |
      | cargo test                                      |
      | go test ./...                                   |
      | make lint                                       |

    Examples: reading files
      | command                                         |
      | cat README.md                                   |
      | head -50 src/app.py                             |
      | sed -n 1,40p src/app.py                         |
      | ls -la                                          |
      | wc -l src/*.py                                  |
      | find . -name "*.py" -not -path "./.venv/*"      |
      | grep -rn "TODO" src                             |
      | rg -n "def main"                                |
      | tree -L 2                                       |

    Examples: one-liners and housekeeping
      | command                                         |
      | python3 -c "import sys; print(sys.version)"     |
      | node -e "console.log(process.version)"          |
      | jq '.dependencies' package.json                 |
      | curl -s https://api.github.com/repos/o/r \| jq . |
      | mkdir -p build/out                              |
      | cp src/app.py src/app.py.bak                    |
      | chmod +x scripts/build.sh                       |
      | rm -rf node_modules                             |
      | rm -rf dist build                               |
      | which python3                                   |
      | echo done                                       |
