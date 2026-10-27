# Changelog

## [0.0.8](https://github.com/mark-brannan/languette/compare/v0.0.7...v0.0.8) (2026-10-27)


### Features

* **install:** `languette install` wires Claude Code through its plugin marketplace ([#273](https://github.com/mark-brannan/languette/issues/273)) ([bfedca8](https://github.com/mark-brannan/languette/commit/bfedca8c9abffb525d2046545029ea64a2bec1b1))
* **worktrees:** a checkout whose directory can't be resolved passes with a note from the session's own worktree ([#268](https://github.com/mark-brannan/languette/issues/268)) ([fb6c39e](https://github.com/mark-brannan/languette/commit/fb6c39e85239f8ecafed83d994a661cb302a9e05))


### Bug Fixes

* **guard-git-work-loss:** add -A with paths and reset to own remote, in agent worktrees only ([#267](https://github.com/mark-brannan/languette/issues/267)) ([8fda807](https://github.com/mark-brannan/languette/commit/8fda807535deca72403eb3c019ec0a0a609fd759))
* **scan:** one command-rule loader and matcher; ask-first rejects unknown keys and accepts flags ([#272](https://github.com/mark-brannan/languette/issues/272)) ([ee8e5ad](https://github.com/mark-brannan/languette/commit/ee8e5ad7cd3167772b66606949feabebcb2a07db))


### Documentation

* **design:** guard rules, the path from today's guards to the engines ([#270](https://github.com/mark-brannan/languette/issues/270)) ([f5fe815](https://github.com/mark-brannan/languette/commit/f5fe81514cd6555cc5405eeff1c7813a680dac0f))
* **design:** the doctor and the install ([#274](https://github.com/mark-brannan/languette/issues/274)) ([75e9c60](https://github.com/mark-brannan/languette/commit/75e9c60e6c61d5298265f58cc62d35f483cd3d99))

## [0.0.7](https://github.com/mark-brannan/languette/compare/v0.0.6...v0.0.7) (2026-10-26)


### Features

* **guard-git-work-loss:** --force-with-lease to main asks instead of denying ([#258](https://github.com/mark-brannan/languette/issues/258)) ([c5422bb](https://github.com/mark-brannan/languette/commit/c5422bbefc2bb89418560cb5c44744341ada4c2b))
* **guard-review-threads:** a review_thread_logins setting names the logins whose reply counts ([#256](https://github.com/mark-brannan/languette/issues/256)) ([6b847a4](https://github.com/mark-brannan/languette/commit/6b847a4b422fd4c3747efbf6118b394556f4e2f6))
* **protected-services:** deny service, pkill and killall stops of a listed unit ([#263](https://github.com/mark-brannan/languette/issues/263)) ([c957187](https://github.com/mark-brannan/languette/commit/c957187b346dcfcc0281ab55fced9ff41dd2280c))


### Bug Fixes

* **guards:** --work-tree alone no longer pins; discards pass on a clean tree ([#254](https://github.com/mark-brannan/languette/issues/254)) ([0394a24](https://github.com/mark-brannan/languette/commit/0394a2483526df88267c37a8ab22f4485c82e749))
* **private-terms:** rewrite a home path in the posted text alone, and ask ([#264](https://github.com/mark-brannan/languette/issues/264)) ([01a75a0](https://github.com/mark-brannan/languette/commit/01a75a0fca15ea6945bdd00fdcbd58b5e663345b))
* **verdict:** an ask with no one to answer it is a deny that names the guard ([#260](https://github.com/mark-brannan/languette/issues/260)) ([557accc](https://github.com/mark-brannan/languette/commit/557accca6b70295bdaddf41f3e3df6a97c4c7017))


### Documentation

* **design:** gather runs guard by guard; verdict takes the mode ([#262](https://github.com/mark-brannan/languette/issues/262)) ([d3c6aea](https://github.com/mark-brannan/languette/commit/d3c6aeaee6919ac60dacfa9d72970192e00a0e92))
* **features:** restore the why of six guard features ([#257](https://github.com/mark-brannan/languette/issues/257)) ([b9566e8](https://github.com/mark-brannan/languette/commit/b9566e8249db7232f9bcab508548516ff3e246e0))
* **research:** a cheap cost estimate for a Bash command ([#261](https://github.com/mark-brannan/languette/issues/261)) ([3cd9549](https://github.com/mark-brannan/languette/commit/3cd95497abdf2ddd642bd94912ea19b967e4cc58))

## [0.0.6](https://github.com/mark-brannan/languette/compare/v0.0.5...v0.0.6) (2026-10-24)


### Bug Fixes

* **guards:** normalise the gh api endpoint before matching; a heredoc counts only when it is the path's one write ([#243](https://github.com/mark-brannan/languette/issues/243)) ([c9eaf97](https://github.com/mark-brannan/languette/commit/c9eaf97023da1bba7635b465c4c60514e4065685))


### Documentation

* **design:** portability rules ([#247](https://github.com/mark-brannan/languette/issues/247)) ([28a5386](https://github.com/mark-brannan/languette/commit/28a5386ea7ae31cc7a3acf2bb348a179d4c4654e))
* **research:** guards other agent-safety tools ship that languette lacks ([#253](https://github.com/mark-brannan/languette/issues/253)) ([98fb2ba](https://github.com/mark-brannan/languette/commit/98fb2ba191446b0b5168ac3e1cb923bdfdccc26f))
* **research:** SQL-level scan for DROP, TRUNCATE and other DDL ([#158](https://github.com/mark-brannan/languette/issues/158)) ([#241](https://github.com/mark-brannan/languette/issues/241)) ([c440bb5](https://github.com/mark-brannan/languette/commit/c440bb550f88af293b6559a839f12d86ba786707))

## [0.0.5](https://github.com/mark-brannan/languette/compare/v0.0.4...v0.0.5) (2026-10-24)


### Features

* **guard-bypass-labels:** default to no guarded labels; churn-ok and mixed-loops-ok are the driver's ([#236](https://github.com/mark-brannan/languette/issues/236)) ([a81b46f](https://github.com/mark-brannan/languette/commit/a81b46f701accb93e2a9a12b881b672d2ecfbcef))


### Bug Fixes

* **guard-bypass-ruleset:** a flag value named merge is not a pr merge ([#234](https://github.com/mark-brannan/languette/issues/234)) ([d18c041](https://github.com/mark-brannan/languette/commit/d18c041a24f363b5c250f468963f75a113c348bd))
* **guard-worktrees:** a worktree the session adds is its own ([#238](https://github.com/mark-brannan/languette/issues/238)) ([ba951de](https://github.com/mark-brannan/languette/commit/ba951de7d2f09e547e7024f1a8e86485de286c1a))


### Documentation

* comments, specs and metadata speak of the maintainer and decisions, not one workflow ([#240](https://github.com/mark-brannan/languette/issues/240)) ([97777e3](https://github.com/mark-brannan/languette/commit/97777e3c14f39147774e23089810e769aad70ed8))
* **decisions:** the decisions file names the maintainer once, in its header ([#239](https://github.com/mark-brannan/languette/issues/239)) ([f73ab26](https://github.com/mark-brannan/languette/commit/f73ab263b0446571dc2ad81a386cbe63d36929f0))

## [0.0.4](https://github.com/mark-brannan/languette/compare/v0.0.3...v0.0.4) (2026-10-15)


### Bug Fixes

* decode ANSI-C quoting in the scanner ([#212](https://github.com/mark-brannan/languette/issues/212)) ([#221](https://github.com/mark-brannan/languette/issues/221)) ([1a7e5e1](https://github.com/mark-brannan/languette/commit/1a7e5e1cde38a07c2bc3266c137a3e9bc3b23c47))
* **scan:** a heredoc fed to a shell is queued as executed text ([#220](https://github.com/mark-brannan/languette/issues/220)) ([4826c35](https://github.com/mark-brannan/languette/commit/4826c355c74feb5b3f84e13d83201d33743270ae))

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
