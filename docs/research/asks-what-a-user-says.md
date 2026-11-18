# What a user says about asks ([#433](https://github.com/mark-brannan/languette/issues/433), [#87](https://github.com/mark-brannan/languette/issues/87), [#84](https://github.com/mark-brannan/languette/issues/84))

The three issues ask one thing: what the verdict configuration lets a user say
about an ask. #433 would take the `asks` option out and stop guards asking when
they can't tell. #87 leaves open the shape of the config row. #84 leaves open
whether the nobody-to-answer fallback can be configured. This sets each
direction #433 lists against [the verdict design](../design/verdict.md) and the
counts on hand. Nothing is built or chosen here.

## Where the asks come from

#433 sorts a guard's ask into three situations. The counts below sort the
recorded asks the same way.

| #433's situation | Sites on main | Replay asks | One machine, one day |
|---|---|---|---|
| Can't read the call | 7, all named in #433 | 840 to 866 | 2 |
| Can't reach the forge | 10, all named in #433 | 22 to 44 | 0 |
| A judgment | `secrets_context`, `judged`, `cross_session_ask`, `wt_home_ask`, `signature_mcp_ask`, ask-first's rules | 45 | 6 |

- **Replay:** [the sampled replay](guard-replay-everyday.md), 36,299
  commands on `e20b2ad`, 933 asks in all. Sorted by guard and the reasons its
  examples show; the doc gives no count per site, so the sort is mine.
  bypass-ruleset's 840 are can't-read, and are mostly the replay's missing
  repository. Stacked-base splits about 22 can't-reach and 4 can't-read.
  The 22 from duplicate-prs could fall in either row. In the replay every
  forge read fails, so its can't-reach count says nothing about a live session.
  At least 6 of guard-secrets' 43 are misreads, such as `date -u` taken as a
  user:password flag, so they belong to none of the three situations.
- **One machine, 2026-11-17, 12:25 to 22:03 UTC:** 9,763 recorded calls, with
  7 asks reaching the user and 1 more overruled by another guard's deny.
  bypass-ruleset made 2, one for an unknown branch and one for a repository it
  couldn't find. guard-secrets made 6, each on a value named by `X-Api-Key`.
  In each of those the shown value starts like a name, the `printer.key` shape
  #433 tests, but the record masks the value, so a literal can't be ruled out.
- **[PR 422](https://github.com/mark-brannan/languette/pull/422):** one
  machine, five days, 16 asks: 11 can't tell, 3 a value named as a credential,
  2 a forced push to `main`.

## Each direction, against the design

| #433's direction | What the design says, and how they fit | Replay asks it changes | Decision |
|---|---|---|---|
| Can't read → deny, naming the rewrite | The design has a guard *report* and a per-guard mapping *decide*. #433 has the guard deny. The two fit if "can't read" is a finding whose default mapping is deny. Neither says whether a user may turn that deny back into an ask: the design fixes only a crashed guard's deny and an unparsable command's. Under #87 a deny tells both by default, so the user sees the rewrite too. | 840 to 866 become denies | |
| Can't reach → deny, naming what's broken | Same fit as the row above. Today the design's fallback turns this ask into a deny only when nobody is there. #433 makes it a deny whoever is there. | 22 to 44, all from the replay's stubbed forge | |
| A judgment → unchanged | Fits the default ask cell, "the prompt". Under #87 its `tell:` default is the user. After this change, the #84 fallback only ever sees judgments. | none | |
| Remove the `asks` option | The design says "the user can turn a deny into an ask, or an ask into a deny". `asks` is the only part of that which exists, as one switch for every guard; PR 422 says the per-guard mapping is not built. With `asks` gone, the sentence has no code until #87's row ships. That widens the gap a design doc may hold; it doesn't contradict the doc. #433 and the design agree that the fallback comes from the mode, not from this option. | today `asks=deny` turns all 933 into denies; after, none | |
| Two words in the shared layer: "can't tell" beside `ask` | The design's decision axis has three values: allow, ask, deny. "Can't tell" fits as a kind of finding that the mapping reads. It strains the design as a fourth decision. #87's option C, warn as a fourth decision, raises the same question about the same axis. | none by itself | |
| guard-secrets passes a name or an environment read | The design doesn't cover it: this is the guard's own reading. | some of 43; the replay doesn't split name from literal | |
| Done: the design says what an ask is for | The design has no such line yet. "What the verdict says" is where it would go (my guess); the file is at 79 of its 100 lines. | none | |

## Questions only the user can answer

- Can a user turn a can't-read or can't-reach deny back into an ask?
- Is "can't tell" a kind of finding or a fourth decision?
- Can the fallback be configured (#84), now that only judgments reach it?

## Words on offer

These are offers for the user to choose from. No pick is made here.

- **The option, if it stays or is renamed:** `asks` (today's name),
  `prompts`, `unsure`, `when_unsure`. **Its values:** `prompt` / `deny`
  (today's), `ask` / `deny`, or `user` / `agent`, named for who answers.
- **The shared-layer word for a finding the guard can't settle:** `cant_tell`,
  `unsure`, `unknown`, `unread`.
