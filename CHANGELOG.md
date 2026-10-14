# Changelog

## [0.0.3](https://github.com/mark-brannan/languette/compare/v0.0.2...v0.0.3) (2026-10-14)


### Features

* **guard-duplicate-prs:** a second PR on an issue an open PR already closes ([#125](https://github.com/mark-brannan/languette/issues/125)) ([2964565](https://github.com/mark-brannan/languette/commit/2964565d0ff792580be2dc36e9cc63ef3a0d34a7))
* **guard-github-issues:** a yes through AskUserQuestion opens a shut door once ([#202](https://github.com/mark-brannan/languette/issues/202)) ([ffab211](https://github.com/mark-brannan/languette/commit/ffab211740bc00693a5c01c26fc4bb9c864d4ca9))
* **guard-review-threads:** a bot's thread is resolved only on a fix or a record ([#118](https://github.com/mark-brannan/languette/issues/118)) ([8f6a459](https://github.com/mark-brannan/languette/commit/8f6a459901203e41a17aafb3b8fe15aae2276384))
* **guard-signed-comments:** a comment an agent posts to GitHub is signed as an agent's ([#119](https://github.com/mark-brannan/languette/issues/119)) ([eb9527f](https://github.com/mark-brannan/languette/commit/eb9527f14095c19d95193b37f2b5964c095831d9))
* **guards:** guard-host-availability denies SysV service stop and restart ([#185](https://github.com/mark-brannan/languette/issues/185)) ([fb0eee8](https://github.com/mark-brannan/languette/commit/fb0eee87d71d94b6a834267ce631f33d77ee90e6))


### Performance

* **hooks:** one hooks.json entry per event ([#209](https://github.com/mark-brannan/languette/issues/209)) ([eacc6de](https://github.com/mark-brannan/languette/commit/eacc6deb054e9cc41de42ff66f8668f18acd42a0))


### Documentation

* **decisions:** new guards build on the shared layer first ([#200](https://github.com/mark-brannan/languette/issues/200)) ([730725e](https://github.com/mark-brannan/languette/commit/730725e9b2c58e2235b6d727f8dacd869277079e))
* **design:** guard rules, four engines a guard is written on ([#199](https://github.com/mark-brannan/languette/issues/199)) ([5b951ce](https://github.com/mark-brannan/languette/commit/5b951cef706986492bc3dfc206cab338477de501))
* **research:** cluster the regex guard's git and GitHub rules beside ours by harm ([#134](https://github.com/mark-brannan/languette/issues/134)) ([#187](https://github.com/mark-brannan/languette/issues/187)) ([30bff66](https://github.com/mark-brannan/languette/commit/30bff66dd4292721327c7255f6d25bd73368bcf3))

## [0.0.2](https://github.com/mark-brannan/languette/compare/v0.0.1...v0.0.2) (2026-10-10)


### Features

* **scan:** `languette scan` reads a command as the guards do, for an outside hook (experimental, v0.1-alpha) ([#175](https://github.com/mark-brannan/languette/issues/175)) ([6611cbe](https://github.com/mark-brannan/languette/commit/6611cbec885ddb5a63bc0376b0f5c2fb0c67e28d))


### Bug Fixes

* **record:** mask with the shared secret detector ([#173](https://github.com/mark-brannan/languette/issues/173)) ([20184ab](https://github.com/mark-brannan/languette/commit/20184ab7327b897fc4f75029d85b19ed60945bf2))
* **scan:** a heredoc opener's line runs past a backslash continuation and an open quote ([#174](https://github.com/mark-brannan/languette/issues/174)) ([5382255](https://github.com/mark-brannan/languette/commit/53822556e3393ddc102456f07f55edecde82a910))


### Documentation

* **decisions:** ship by merging the release PR; titles carry a conventional type ([#177](https://github.com/mark-brannan/languette/issues/177)) ([0e8d19b](https://github.com/mark-brannan/languette/commit/0e8d19be10770597721c7a231584b8fc76db8a93))

## 0.0.1 (2026-10-10)


### Features

* **ask-first:** deny repo-listed costly commands until the user approves one run ([#23](https://github.com/mark-brannan/languette/issues/23)) ([0cf7e04](https://github.com/mark-brannan/languette/commit/0cf7e0462cc957916c15778eaa417a8d825203e0))


### Dependencies

* Dependabot bumps the test tools weekly and the actions monthly ([#156](https://github.com/mark-brannan/languette/issues/156)) ([96c6de1](https://github.com/mark-brannan/languette/commit/96c6de1f46ebf5ac30113e926d966ed56f720a52))


### Documentation

* record the ask-first config rulings ([#26](https://github.com/mark-brannan/languette/issues/26)) ([d53d974](https://github.com/mark-brannan/languette/commit/d53d974844dc717df27b004ce46224f327407905))
* state the shape of a strong guard and the scenario-based contract ([#28](https://github.com/mark-brannan/languette/issues/28)) ([aaa0518](https://github.com/mark-brannan/languette/commit/aaa0518c997ef87344f37daf898959abe6fc0fe9))
* the guard pipeline design, and its ruling in decisions.md ([#86](https://github.com/mark-brannan/languette/issues/86)) ([c3bbef7](https://github.com/mark-brannan/languette/commit/c3bbef71d172332d89d8d56d5b82af97aeaa8e06))
