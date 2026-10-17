# P2 pre-unseal censoring and dependence audit — independent scientific review required

**17 October 2026. Strictly read-only research. NO active evaluator patch, no sealed outcome access, no prospective cohort modification, no R9 actions or trading authority.**

## Reproducible evidence (aggregate metadata only)

Source: `public.alpha_hunter_geometry_holdout_bindings`, `public.alpha_hunter_geometry_holdout_evaluator_failures`, frozen public spec and operational collection status. Re-run `ops/research/p2_geometry_preunseal_censoring_audit_v01.sql` with read-only permissions.

| Observation | Read-only evidence |
| --- | ---: |
| Frozen prospective bindings | 30,697 |
| Eligible bindings | 3,915 |
| Excluded bindings | 26,782 |
| Capture failures | 0 |
| Evaluator failure *events* | 218 |
| Distinct bindings with failure | 27 |
| URL-unsafe-symbol failure events | 217 |
| Eligible bindings with logged URL rejection | **26** |
| Additional eligible non-ASCII symbol bindings with no logged error | **21** |
| **Total eligible candidates at risk from symbol restriction** | **47** |
| Transient SSL timeout events | 1 |
| Shared source signal ID from LONG+SHORT candidates | 4,225 distinct source IDs |
| Unexplained cross-symbol shared source IDs | 0 |
| Primary result exposed | false |

The three non-ASCII source symbols are 龙虾USDT, 哈基米USDT, 牛来USDT (the audit groups names, not performance). The original frozen evaluator has a hard expression `r.symbol !~ '^[A-Z0-9]+USDT$'` raising `SYMBOL_NOT_URL_SAFE`, followed by fail-closed retry and DATA_INSUFFICIENT after **three failures and six hours**. The regex is a deliberate request-safety constraint: **do not weaken it with unescaped user-supplied URL text**. This creates *systematic* missing-data risk. The 21 without logged failures are **unknown** as to actual evaluation; no access to sealed outcomes was performed, no claim that 47 results are missing, and **218 retry events are not 218 independent trades**. New timestamps/failures require a fresh read before any later independent review.

Every two-way reused source signal ID refers to the same symbol and source capture but opposite LONG/SHORT directions; it is not a unique trade pair and **must be clustered** when a study uses independent-source inference. Distinct diagnostic IDs are unique. The current P2 preregistration must not change candidate inclusion, direction, treatment or denominator because of this discovery. Review this dependence at the scheduled 19 November cohort freeze.

## No-peeking and prospective-change firewall

- Do **not** query `alpha_hunter_geometry_holdout_outcomes_sealed` or change its row-level permissions or sealed-result hashes before independent scientific unseal authorization.
- Do **not** alter original frozen schema fingerprints, observation windows, stop/target definitions, accepted/excluded bindings, evaluator URL safety, 35-minute R9 monitor cap, live orders, paper admission halt or historical outcomes.
- If a result has permanently insufficient source evidence, retain it as a **missing/censored observation** under the frozen protocol. Do not reclassify it as a win, loss, TP/SL, or silently erase its binding from the cohort.
- No speculative historical depth, no percent-encoded request made retroactively that could read a different market feed and silently overwrite data. Any Unicode-accepting URL implementation belongs in a **separately preregistered successor-only isolated test** with an explicit exchange symbol-identity mapping, quoted/encoded path, full source custody and independent risk/security review.
- Existing P2 geometry v0.1 captured 3,915 eligible candidates and reports 3,954 complete binding/horizon sets as operational metadata; **these metrics are not proof of valid paired outcomes** and must not be used to peek at hypothesis success. Evaluator failure events can coexist with subsequent censored sealed rows; metadata cannot establish which individual outcomes exist.
- Source-signal pairing across LONG/SHORT must not be treated as two independent symbol/day clusters. Randomness or label permutation does not create independence.
- Even if all pre-unseal QA is numerically green, `review_capture_metadata` never grants permission to unseal, trade, activate an alternative stop/target, or promote an unreviewed strategy.

## Independent review check after cohort freeze

1. Confirm immutable declared eligible/excluded denominator and retained failures; report actual missingness by symbol, direction, epoch and source *only when protocol permits*.
2. Verify prospective output row custody and price-source authentication; place systematically unobserved symbols in the predefined missingness/sensitivity strata, not an outcome-based post-hoc exclusion.
3. Validate predeclared first-touch path ordering for both variants, cost/funding availability and adverse quote/depth evidence; still no fill performance claim from public bar history.
4. Evaluate both dependence-adjusted inference and missing-not-at-random risk in a **separate approved scientific review**, with no opportunistic threshold changes after viewing results.
5. New successor P3 remains a different experiment: **230 actual prospective completed pairs, 60 symbols, 20 UTC days, positive symbol- and day-equal lower confidence bounds after costs**, plus explicit independent risk/scientific approval. The existing P2 geometry cohort cannot be counted toward it.

**Current decision: HOLD/NO SCIENTIFIC PROMOTION.** R9 test continues unchanged with 0 qualifying completions and halted admissions. This audit is not a database migration and is not executable trade authority.
