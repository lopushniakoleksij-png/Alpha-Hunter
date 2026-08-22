# ALPHA HUNTER — CURRENT PRODUCTION STATE

Last updated: 2026-08-22 23:45 UK
Repository: lopushniakoleksij-png/Alpha-Hunter
Branch: fix/v78-phase-history

## PURPOSE

This file is the mandatory Alpha Hunter production handoff record.

Before any new ChatGPT conversation changes Alpha Hunter production, it must read this record and establish the current state.

No production work may rely only on chat history.

## WORKFLOW RULE

PLAN → EXECUTE → TEST → VERIFY → RECORD → COMMIT → NEXT

No meaningful production step is complete until it is recorded.

## CURRENT GITHUB STATE

Repository verified: YES
Repository: lopushniakoleksij-png/Alpha-Hunter
Branch: main
Latest GitHub commit observed before ledger creation:
aea31f1 — Add V7.5 independent tracking and 24H finalization

ChatGPT UI GitHub status:
Connected
Permission: Allow all

IMPORTANT:
ChatGPT's GitHub integration previously returned zero accessible repositories.
Browser verification confirmed that Alpha-Hunter exists.
Connector/API access still requires separate verification.

## CURRENT PRODUCTION / RESEARCH STATE

Current active research: V7.10 Early Execution / RR Shadow Research

Classification: SHADOW / RESEARCH
Production permission: NONE

V7.10 must remain read-only until explicitly promoted after testing and verification.

Observed V7.10 diagnostic cases:

WLDUSDT
Class: WRONG_DIRECTION_BAD_RR
Direction: SHORT
Executable RR: 4.78
Captured RR: 0.01
Lost RR: 4.78
Move: -0.03

CAPUSDT
Class: WRONG_DIRECTION_BAD_RR
Direction: LONG
Executable RR: 0.86
Captured RR: 0.13
Lost RR: 0.73
Move: 0.38

V7.10 run explicitly reported:

- READ-ONLY SHADOW RESEARCH
- No Supabase rows written
- No trade permission generated

## LOCAL WORKING TREE LAST OBSERVED

Modified:
production_runner.py

Untracked:
data/
restore_previous_snapshot.py
tests/test_restore_previous_snapshot.py

This local state has NOT yet been reconciled with GitHub.

Do not overwrite, discard, commit, or promote these changes until their purpose and diff are verified.

## CURRENT PROBLEM

Production continuity depended too heavily on ChatGPT conversation history.

When a new chat was started, work state had to be reconstructed manually.

This created:

- wasted time
- drift risk
- duplicated investigation
- incorrect assumptions
- risk of losing experimental context
- risk of mixing research and production

## PERMANENT HANDOFF RULE

Every production session must record:

1. What we planned
2. What we executed
3. Files changed
4. Tests performed
5. Test results
6. Failures discovered
7. Decisions made
8. Production/research classification
9. Git commit
10. Exact next step

## NEXT STEP

STOP FEATURE DEVELOPMENT.

First reconcile the local Alpha Hunter working tree against GitHub.

Verify:

- production_runner.py diff
- data/snapshots/latest.json state
- restore_previous_snapshot.py
- tests/test_restore_previous_snapshot.py
- whether V7.10 changes are intentionally shadow-only
- whether any production behavior changed unintentionally

After reconciliation:

TEST → VERIFY NO DRIFT → RECORD RESULT → COMMIT SAFE STATE

Only then continue V7.10 research.

---

## PRODUCTION RECONCILIATION UPDATE — 2026-08-16

### Git / Branch State

Active branch:
feature/v710-early-execution-shadow

Production ledger commit from main:
7456b99 — Add Alpha Hunter production state ledger

Ledger merged into V7.10 branch:
a3d7eaf

### Local Working Changes

Modified:
- .gitignore
- production_runner.py

Untracked source/test files:
- restore_previous_snapshot.py
- tests/test_restore_previous_snapshot.py
- v75_lifecycle_evaluator.py

Runtime/generated data is now excluded from Git through:
data/

### V7.10 Runner Verification

production_runner.py local modification adds:

STEP 10 — V7.10 EARLY EXECUTION RR SHADOW

Script:
v710_early_execution_rr_shadow.py

Verified:
- Supabase access uses GET/read-only path
- no requests.post
- no requests.put
- no requests.patch
- no requests.delete
- no httpx write methods found
- trade_permission remains False

Current classification:
SHADOW / READ-ONLY RESEARCH

### Snapshot Restore Verification

restore_previous_snapshot.py:

- reads latest Supabase snapshot with GET
- does not mutate Supabase
- writes restored snapshot locally only
- local target: data/snapshots/latest.json
- atomic temporary-file replacement used

Test:

python -m unittest tests.test_restore_previous_snapshot -v

Result:
5 tests run
5 passed
0 failures
PASS

### V7.5 Lifecycle Evaluator Verification

Command:

python v75_lifecycle_evaluator.py

Result:
PASS

Episodes:
69

Expansion results:
3%  = 58/69 = 84.1%
5%  = 50/69 = 72.5%
10% = 32/69 = 46.4%

Execution:
Trade Ready = 0
Trade Permission = 0

Performance classifications:
ACTIVE = 11
EARLY_DETECTION_NO_EXECUTION = 18
EARLY_EXPANSION = 8
MISSED_MAJOR_EXPANSION = 32

IMPORTANT FINDING:

Alpha Hunter is detecting many genuine expansion events, including 32 episodes that reached major expansion, but the execution layer generated zero Trade Ready and zero Trade Permission outcomes.

This confirms a major detection-to-execution conversion problem that requires investigation.

### CURRENT SAFETY STATE

No real trade execution introduced.
No V7.10 Supabase mutation discovered.
V7.10 remains SHADOW.
No runtime data will be blindly committed.

### EXACT NEXT STEP

Run full Git status and diff audit before staging anything.

NO COMMIT.
NO PUSH.
NO PRODUCTION PROMOTION.

---

## CHECKPOINT COMPLETED — 2026-08-16

Reconciliation commit:
91b1615 — Reconcile V7.10 shadow production state and recovery tooling

Remote branch:
feature/v710-early-execution-shadow

Push status:
PASS

GitHub remote verification:
PASS

Commit verified remotely:
91b1615da3818e6f48539d7dfe64b24e046e6a16

Working tree before this ledger update:
CLEAN

### VERIFIED CHECKPOINT STATE

- Production ledger established
- Ledger filename corrected to CURRENT_STATE.md
- Runtime data excluded from Git
- Snapshot restore tooling added
- Snapshot restore tests: 5/5 PASS
- V7.5 lifecycle evaluator: PASS
- V7.10 runner hook verified
- V7.10 Supabase path remains read-only
- Trade permission remains FALSE
- No real trade execution introduced
- V7.10 remains SHADOW / RESEARCH

### NEXT STEP

Commit and push this checkpoint ledger update only.

After that:
resume V7.10 investigation from the recorded state.

DO NOT reconstruct state from chat history.
READ CURRENT_STATE.md FIRST.

---

## V7.10 ENTRY-LOCATION CHECKPOINT — 2026-08-16

Execution replay:
- Evaluated: 23
- Correct early direction: 22/23
- Correct direction NO_PREEXISTING_5R_SETUP: 13
- Correct direction STOP_FIRST: 3
- Correct direction TARGET_FIRST: 1
- Correct direction UNRESOLVED: 5

Stop-policy conclusion:
- No stop policy promoted.
- Positive provisional R is small-sample and materially influenced by AVAX.
- Stop changes alone do not solve NO_SETUP frequency.

Entry-location matrix:

MARKET:
- TARGET_FIRST 1
- STOP_FIRST 1
- NO_SETUP 18
- Resolved R +4.53

PB25:
- TARGET_FIRST 2
- STOP_FIRST 1
- FILLED_UNRESOLVED 4
- NOT_FILLED 1
- TARGET_BEFORE_FILL 0
- NO_SETUP 14
- Resolved R +11.87

PB50:
- TARGET_FIRST 1
- STOP_FIRST 2
- FILLED_UNRESOLVED 2
- NOT_FILLED 4
- TARGET_BEFORE_FILL 2
- NO_SETUP 11
- Resolved R +3.13

PB75:
- TARGET_FIRST 0
- STOP_FIRST 3
- NOT_FILLED 2
- TARGET_BEFORE_FILL 11
- FILL_AND_STOP_SAME_BAR 2
- NO_SETUP 4
- Resolved R -3.00

DECISION:
- PB25 is the strongest current entry-location candidate.
- Evidence is NOT sufficient for production promotion.
- PB75 appears too deep and frequently misses expansion.
- Setup geometry / target structure remains the dominant unresolved bottleneck.
- Trade permission remains FALSE.
- V7.10 remains SHADOW / RESEARCH.

EXACT NEXT STEP:
Run v710_target_ladder_diagnostic.py to determine whether NO_SETUP cases are caused by target structure being too close, stop distance being too wide, or farther pre-existing structure restoring 5R.

---

## V7.10 TARGET-LADDER CHECKPOINT — 2026-08-16

Target-ladder diagnostic:
- Evaluated: 23
- Failures: 0
- FARTHER_STRUCTURE_RESTORES_5R: 5
- STOP_TOO_WIDE_EVEN_FOR_10PCT: 12
- TARGET_OR_STRUCTURE_BOTTLENECK: 6

Primary finding:
- 52.2% of evaluated early episodes fail primarily because structural stop distance is too wide even for a hypothetical 10% reward move.
- Direction discovery is therefore not the dominant current failure.
- Stop/invalidation geometry at DIRECTION_EMERGING is now the primary execution bottleneck.
- Farther pre-existing structure restores >=5R in only a minority of cases.
- Target selection alone cannot solve the majority of NO_SETUP outcomes.

Examples of excessive stop distance:
- CYSUSDT: 45.73%
- HUSDT: 30.74%
- AEONUSDT: up to 11.52%
- DOLOUSDT: 8.06%

DECISION:
- Do not promote PB25 yet.
- Do not loosen Trade Permission.
- Do not select a stop policy yet.
- Investigate how V7.8 creates structural stop/invalidation at DIRECTION_EMERGING.
- V7.10 remains SHADOW / RESEARCH.
- Trade permission remains FALSE.

EXACT NEXT STEP:
Trace stop_price and stop_distance_pct generation through V7.7/V7.8 and determine why early emerging episodes receive excessively wide structural invalidations.

---

## V7.10 STOP-SOURCE ROOT-CAUSE CHECKPOINT — 2026-08-16

Emerging stop-source forensics:
- Emerging rows evaluated: 23
- Stop >2%: 15/23 = 65.2%
- Stop >3 ATR: 12/23 = 52.2%
- Every observed stop source was 15M structure.
- No 1H stop source was selected.

Wide stop source breakdown:
- 15M_SWING_HIGH + 0.25ATR15 buffer: 9
- 15M_SWING_LOW + 0.25ATR15 buffer: 6

Extreme examples:
- CYSUSDT SHORT: stop 45.73%, 4.94 ATR
- HUSDT SHORT: stop 30.74%, 4.42 ATR
- AEONUSDT SHORT: stop up to 11.52%, 4.23 ATR
- DOLOUSDT LONG: stop 8.06%, 2.21 ATR

ROOT-CAUSE FINDING:
- Excessive stops are not being created by 1H structure.
- The dominant source is the 15M structural extreme used at DIRECTION_EMERGING.
- During strong displacement, the recent structural extreme can remain far behind price and cease to be useful execution invalidation.
- The 0.25 ATR buffer widens the stop further but is not the primary cause.
- Simply forcing a shorter stop window is not yet justified because prior replay showed increased stop-outs.

DECISION:
- Do not change production stop logic.
- Do not promote PB25.
- Do not loosen Trade Permission.
- Do not impose a hard 2% or 3 ATR production cap yet.
- Test stop admissibility and local stop re-anchoring in V7.10 shadow research.
- Trade permission remains FALSE.
- V7.10 remains SHADOW / RESEARCH.

EXACT NEXT STEP:
Build a read-only stop re-anchor diagnostic that compares the current V7.8 stop against local re-anchored stops and tests whether waiting for a valid local invalidation can preserve early direction while improving executable RR.

---

## V7.8 HISTORICAL EVIDENCE MUTATION DEFECT — 2026-08-16

Audit result:
- Raw EMERGING rows: 37
- Currently usable EMERGING rows: 21
- Usable correct direction: 20
- Usable wrong direction: 1

Confirmed historical degradation examples:
- CAPUSDT episode 70bdc9f4301133fdeb3f2412
  - EMERGING phase: 2026-08-15T17:08:21Z
  - measurement_quality: INSUFFICIENT_CANDLE_HISTORY
  - closed 15M bars available on latest rerun: 7
  - closed 1H bars available on latest rerun: 9

- CYSUSDT episode a046ccf95346f0da2e8254d4
  - EMERGING phase: 2026-08-15T17:08:21Z
  - measurement_quality: INSUFFICIENT_CANDLE_HISTORY
  - closed 15M bars available on latest rerun: 7
  - closed 1H bars available on latest rerun: 9

Control:
- VELVETUSDT episode 96b492a4abe75a7955308345
  - newer EMERGING phase
  - COMPLETE
  - closed 15M bars: 94
  - closed 1H bars: 112

ROOT CAUSE:
- V7.8 recalculates historical phase evidence using the current rolling candle window.
- Older phase timestamps eventually fall outside sufficient rolling history.
- V7.8 upserts on snapshot_id.
- A previously COMPLETE historical snapshot can therefore be overwritten by later INSUFFICIENT_CANDLE_HISTORY evidence.
- Historical research evidence is not currently immutable.

IMPACT:
- V7.10 cohorts changed between experiments.
- Previous 23-episode comparisons are not guaranteed stable.
- Stop-policy, target-ladder, entry-location and re-anchor results remain provisional until evidence integrity is repaired and cohorts are frozen.

IMMEDIATE SAFETY DECISION:
- Do not run V7.8 again until repaired.
- Do not run production_runner.py while V7.8 mutation risk remains.
- Do not promote PB25.
- Do not promote stop re-anchoring.
- Do not change Trade Permission.
- Trade permission remains FALSE.

REQUIRED FIX:
1. Historical phase candle retrieval must be anchored to phase_at, not today's latest rolling window.
2. Existing COMPLETE phase evidence must never be downgraded by an incomplete later recalculation.
3. Add explicit immutable-snapshot regression tests.
4. Reconstruct damaged historical rows from phase-time historical candles.
5. Freeze an episode-ID cohort before rerunning V7.10 comparisons.

EXACT NEXT STEP:
Add failing regression tests for COMPLETE-snapshot preservation and phase-time historical candle reconstruction before modifying V7.8 implementation.

---

## V7.8 IMMUTABILITY REGRESSION TEST — RED CHECKPOINT — 2026-08-16

Regression tests added:
- tests/test_v78_snapshot_immutability.py

Result:
- 2 failed
- 1 passed
- 1 environment warning

Confirmed failing protections:

1. COMPLETE snapshot preservation
- Existing COMPLETE snapshot was supplied.
- Incoming row had the same snapshot_id but INSUFFICIENT_CANDLE_HISTORY.
- Current upsert_rows() returned 1 and attempted persistence.
- Expected behavior is 0 writes.
- Defect reproduced successfully.

2. Phase-time historical reconstruction
- V7.8 does not currently provide load_phase_candles().
- Historical candle reconstruction therefore remains dependent on the rolling current-candle window.
- Defect reproduced successfully.

Passing behavior:
- Existing INSUFFICIENT snapshot may be upgraded to COMPLETE.

TDD STATUS:
RED — defects reproduced before implementation changes.

SAFETY:
- Do not run V7.8.
- Do not run production_runner.py.
- Trade permission remains FALSE.

EXACT NEXT STEP:
Implement immutable COMPLETE snapshot preservation and phase_at-anchored historical candle loading, then rerun these regression tests to reach GREEN.

---

## V7.8 EVIDENCE INTEGRITY REPAIR — STAGE 1 GREEN — 2026-08-16

Implemented:
- COMPLETE historical snapshots are now immutable in upsert_rows().
- Existing COMPLETE evidence is skipped rather than recalculated or overwritten.
- INSUFFICIENT evidence may still be upgraded to COMPLETE.
- Added load_phase_candles() for phase_at-anchored Bitget historical retrieval.

Verification:
- tests/test_v78_snapshot_immutability.py: 3 passed.
- Combined V7.8 regression + V7.10 suite: 60 passed.
- git diff --check: clean.
- Python compile: clean.
- Only v78_timing_rr_decay_shadow.py modified.

IMPORTANT:
- load_phase_candles() exists but is NOT yet wired into V7.8 main.
- V7.8 main still uses current rolling client.candles() history.
- DETECTION / EMERGING / CONFIRMED therefore still need independent phase-time retrieval.

SAFETY:
- Do not run v78_timing_rr_decay_shadow.py yet.
- Do not run production_runner.py yet.
- No database reconstruction yet.
- Trade permission remains FALSE.

EXACT NEXT STEP:
Add regression tests proving DETECTION, EMERGING and CONFIRMED each use their own phase_at timestamp, then replace the remaining rolling client.candles() calls with phase-anchored retrieval.

---

## V7.8 PHASE-HISTORY WIRING — STAGE 2 RED — 2026-08-16

Regression test added:
- tests/test_v78_phase_history_wiring.py

Purpose:
Prove that V7.8 DETECTION, EMERGING and CONFIRMED must each reconstruct candle history using their own phase_at timestamp.

RED TEST RESULT:
- 1 failed
- 1 environment warning

Confirmed failure:
- Expected load_phase_candles() calls: 6
- Actual calls: 0

Interpretation:
- load_phase_candles() exists from Stage 1.
- V7.8 main is NOT yet using it.
- Current main still uses rolling client.candles() history.
- The same rolling history is reused across DETECTION / EMERGING / CONFIRMED.
- Stage 2 defect is reproduced before implementation changes.

TDD STATUS:
RED — phase-time wiring defect reproduced.

SAFETY:
- Do not run v78_timing_rr_decay_shadow.py.
- Do not run production_runner.py.
- No database reconstruction.
- No stop-model promotion.
- Trade permission remains FALSE.

GITHUB RECORDING RULE:
Every meaningful Alpha Hunter production/research step must follow:
PLAN → EXECUTE → TEST → VERIFY → RECORD → COMMIT → PUSH → REMOTE VERIFY → NEXT.

No step is considered complete until its checkpoint is present on GitHub.

EXACT NEXT STEP:
Wire load_phase_candles() into DETECTION, EMERGING and CONFIRMED using each phase's own timestamp, then rerun the Stage 2 regression and full relevant test suite.

---

# ALPHA HUNTER HARD STOP / HANDOFF CHECKPOINT — 2026-08-16

## CURRENT REMOTE CHECKPOINT

Branch:
feature/v710-early-execution-shadow

Last verified remote commit before this checkpoint:
906ba37a334444f67311db2a86e96ac91aebce5d

Commit:
Record V7.8 phase history wiring RED test

## WHY WORK PAUSED

V7.10 execution research exposed unstable experiment cohorts.

Root cause was traced to V7.8 historical evidence mutation:
historical phase rows were reconstructed from the current rolling Bitget candle window and upserted over the same snapshot_id.

Older COMPLETE evidence could therefore degrade into:
INSUFFICIENT_CANDLE_HISTORY.

This made historical research cohorts unstable and made V7.10 comparisons provisional.

## COMPLETED REPAIR WORK

### Stage 1 — COMPLETE SNAPSHOT IMMUTABILITY

Implemented in v78_timing_rr_decay_shadow.py:

- Existing COMPLETE historical snapshots are immutable.
- COMPLETE evidence is skipped instead of overwritten.
- INSUFFICIENT evidence may be upgraded to COMPLETE.
- load_existing_snapshot_rows() added.
- load_phase_candles() added for phase_at-anchored Bitget history.

Tests:

tests/test_v78_snapshot_immutability.py

TDD progression:
RED:
- 2 failed
- 1 passed

GREEN:
- 3 passed

Combined verification:
- V7.8 regression + V7.10 tests: 60 passed
- Python compile passed
- git diff --check passed

Stage 1 remote commit:
baf9b2514f3c769ca782838562b323557001f52e

### Stage 2 — PHASE-HISTORY WIRING

Regression test added:

tests/test_v78_phase_history_wiring.py

Purpose:
Require independent historical candle reconstruction for:

DETECTION
→ history anchored to detection_at

EMERGING
→ history anchored to emerging_at

CONFIRMED
→ history anchored to confirmed_at

Current RED result:

Expected load_phase_candles() calls: 6
Actual calls: 0

Result:
1 failed

This proves V7.8 main still uses rolling client.candles() history.

Stage 2 RED remote commit:
906ba37a334444f67311db2a86e96ac91aebce5d

## CURRENT CODE STATE

load_phase_candles() EXISTS.

Immutable COMPLETE protection EXISTS.

But V7.8 main is NOT YET wired to load_phase_candles().

The remaining old rolling client.candles() calls must be replaced.

## DO NOT DO YET

Do NOT run:

v78_timing_rr_decay_shadow.py

Do NOT run:

production_runner.py

Do NOT reconstruct Supabase rows yet.

Do NOT promote:

- PB25
- stop re-anchoring
- 2% stop cap
- 3 ATR stop cap
- any V7.10 execution rule

Trade Permission remains FALSE.

V7.10 remains SHADOW / RESEARCH.

## V7.10 RESULTS CURRENTLY PROVISIONAL

Previous results including:

- target ladder
- stop policy matrix
- entry location matrix
- stop re-anchor replay
- +18.65 provisional R

must not be treated as validated until:

1. V7.8 evidence integrity is fully repaired.
2. damaged historical rows are reconstructed.
3. research cohort episode IDs are frozen.
4. repeated V7.10 runs reproduce the same cohort/results.

## EXACT NEXT STEP

Implement Stage 2 GREEN:

Replace remaining rolling client.candles() usage in
v78_timing_rr_decay_shadow.py with load_phase_candles().

Required calls:

DETECTION:
15m @ detection_at
1H @ detection_at

EMERGING:
15m @ emerging_at
1H @ emerging_at

CONFIRMED:
15m @ confirmed_at
1H @ confirmed_at

Then run:

python -m py_compile v78_timing_rr_decay_shadow.py

python -m pytest -q tests/test_v78_phase_history_wiring.py

Expected:
1 passed

Then run:

python -m pytest -q \
tests/test_v78_snapshot_immutability.py \
tests/test_v78_phase_history_wiring.py \
tests/test_v710_*.py

Expected approximately:
61 passed

Then:

VERIFY
→ RECORD Stage 2 GREEN
→ COMMIT
→ PUSH
→ REMOTE SHA VERIFY

Only after remote verification:

NEXT PHASE:
Controlled damaged historical evidence reconstruction.

Then:
Freeze fixed episode-ID V7.10 cohort.

Then:
Rerun V7.10 execution research.

## GOVERNING WORKFLOW

PLAN
→ EXECUTE
→ TEST
→ VERIFY
→ RECORD
→ COMMIT
→ PUSH
→ REMOTE VERIFY
→ NEXT

No meaningful Alpha Hunter step is complete until recorded on GitHub.

## 2026-08-22 FIVE-DAY CLOUD AUDIT AND V7.8 STAGE 2 GREEN

### CLOUD EVIDENCE AUDIT

Audited branch:
live/alpha-hunter-5d-20260816

Evidence window:
2026-08-16T22:07:27Z through 2026-08-21T21:28:24Z

Observed:

- 111 cloud run directories
- 111 raw-universe captures
- 111 deep snapshots
- 111 live-scan PASS records
- 111 v79 universe PASS records
- 0 traceback, fatal, exception, or explicit error matches in logs
- approximately 120 hourly observations were expected
- multiple schedule gaps exceeded 70 minutes
- the largest observed gaps were approximately 120 minutes
- only 66 status manifests contain the complete 13-line model chain
- 40 manifests contain only raw_universe, live_scan, and v79_universe
- 5 manifests also contain guardrails but not the full downstream chain

Interpretation:

The five-day collection produced substantial usable evidence, but it was
not a perfectly continuous hourly chain. Missing status entries must not be
silently interpreted as model PASS or FAIL. The live evidence branch remains
DATA / LIVE-EVIDENCE ONLY and must not be merged wholesale.

### V7.8 STAGE 2 GREEN

Defect proven by regression test:

V7.8 main used one rolling current-candle response for DETECTION, EMERGING,
and CONFIRMED. The phase-anchored historical loader existed but was never
wired into the main execution path.

Repair:

- DETECTION now loads 15m and 1H history anchored to detection_at.
- EMERGING now loads 15m and 1H history anchored to emerging_at.
- CONFIRMED now loads 15m and 1H history anchored to confirmed_at.
- Rolling client.candles() calls were removed from the V7.8 phase comparison.
- Trade permission remains FALSE.
- V7.8 remains SHADOW / RESEARCH.
- V7.10 remains SHADOW / RESEARCH.

Verification:

- V7.8 phase-history and immutability tests: 4 passed
- Complete repository test suite: 221 passed
- git diff --check: passed

Branch:
fix/v78-phase-history

## EXACT NEXT STEP AFTER REMOTE VERIFICATION

Do not promote any V7.10 rule yet.

Next phase:

1. Identify every historical V7.8 row created with rolling/current candles.
2. Preserve immutable COMPLETE evidence rules while marking damaged rows.
3. Perform controlled reconstruction using phase-anchored history.
4. Freeze the repaired episode-ID cohort.
5. Rerun V7.10 research against that fixed cohort.
6. Compare results before considering any production promotion.

## 2026-08-23 CONTROLLED V7.8 RECONSTRUCTION SAFEGUARDS

Branch:
repair/v78-damaged-evidence

Implemented:

- Added v78_reconstruct_damaged_evidence.py.
- Default execution is read-only dry-run.
- Dry-run loads all V7.8 evidence with pagination.
- Existing COMPLETE rows are excluded and remain immutable.
- Only INSUFFICIENT_CANDLE_HISTORY rows may enter the candidate manifest.
- Any unexpected non-COMPLETE quality blocks reconstruction.
- Candidate manifests are deterministically sorted and SHA-256 frozen.
- Apply mode requires the exact frozen manifest.
- Candidate-set drift after dry-run blocks apply mode.
- Apply mode requires an explicit digest confirmation environment value.
- V7.8 upsert supports a strict snapshot-ID allowlist.
- Reconstruction writes only rows upgraded to COMPLETE.
- New, unrelated, incomplete, and non-allowlisted rows cannot be written.
- Trade permission remains FALSE.

Verification:

- Reconstruction/V7.8 focused tests: 10 passed.
- Complete repository test suite: 227 passed.
- Python compile: passed.
- git diff --check: passed.

Database status:

- No Supabase reconstruction was executed from this workspace.
- No Supabase credentials were copied, exposed, or requested.
- No candidate manifest was frozen because Supabase is not configured locally.
- No production_runner execution occurred.
- No V7.10 rule was promoted.

## EXACT NEXT STEP

Run the reconstruction tool in an authorized environment with the existing
Supabase configuration in dry-run mode and freeze its manifest. Audit the
candidate count, symbols, phases, timestamps, and digest. Only after that
review may the exact digest be supplied to apply mode. After apply, verify
that candidates either upgraded to COMPLETE or remained unchanged, then
freeze the repaired V7.10 episode-ID cohort and rerun research.
