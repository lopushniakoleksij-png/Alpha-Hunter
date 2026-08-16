# ALPHA HUNTER — CURRENT PRODUCTION STATE

Last updated: 2026-08-16 18:04 UK
Repository: lopushniakoleksij-png/Alpha-Hunter
Branch: main

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
