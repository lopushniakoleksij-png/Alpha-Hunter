# Alpha Hunter — P0 authentic QA parity and independent sign-off packet

**Evidence cutoff: 17 November 2026.**
**Release status: NO-GO / draft PR #445.** Research and paper execution only. This is a read-only evidence packet, **not** an approval or a completed benchmark.

## 1. Access and evidence custody

**Blocked:** The connected GitHub integration exposes PRs, files and CI but **no private Codespaces terminal or container controls**. The authorised `alpha-hunter-private-postgres17-qa` Docker container was last reported stopped with exit code 255; its present lifecycle state has **not** been independently re-inspected. Existing Codespaces account access, private archive custody and retained QA volumes are unverified in this turn.

An exact-filename search of the files available to this chat for `production_schema.dump` and the protected schema archive found no accessible archive. This **does not mean no archive exists inside the owner's Codespace**. Never copy raw production schema/function source, credentials, customer data or private archive into public GitHub or chat.

The older Stage 7 `ah_authentic_schema_20261110` reference and newer `alpha_hunter_private_qa` full-parity validation target are **different** databases. One must never silently substitute for the other.

## 2. Production reference — directly inspected, SELECT-only

Ran the exact committed metadata inventory SQL `ops/sql/readonly_stage2_structural_fingerprint_v01.sql` and `ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql` against the connected production Supabase project, splitting their separate SELECT statements for accurate tool results. Confirmed on 17 Nov:

| Catalog baseline | Verified value |
| --- | --- |
| Public Alpha Hunter application tables / RLS-enabled | 128 / 128 |
| Application columns / indexes / RLS policy rows | 3,012 / 360 / 0 |
| Application triggers / trigger-bearing tables | 131 / 108 |
| Distinct direct trigger functions / SECURITY DEFINER trigger call sites | 36 / 21 |
| Columns fingerprint | `c802a3e3d96d620a20adc8c3af350472` |
| Index fingerprint | `5a7e8cbe8b8450677f6be84a77caaa6e` |
| Trigger/direct-function fingerprint | `5c5b202307ef6bb57b4a9b08082c2a1e` |
| Table-grant/RLS fingerprint | `c9785c793fa51a732c2edc96ba22c7eb` |
| Private function inventory | 110 functions, 65 SECURITY DEFINER, digest `8fae5afad12f3040d30d0416cbfd9be1` |
| Public Alpha Hunter function inventory | 10 functions, 5 SECURITY DEFINER, digest `a75b1d2ed683766dbd5ffa3830f7f087` |
| Private table application triggers | 0 |
| Extensions verified | `http 1.6`, `pg_cron 1.6.4`, `pg_net 0.20.4`, `pg_stat_statements 1.11`, `pgcrypto 1.3`, `plpgsql 1.0`, `supabase_vault 0.3.1`, `uuid-ossp 1.1`, all in expected schemas |

Six critical private callback source digests also matched the frozen expected values in `ops/local/verify_restored_private_pg17_fingerprints_v01.sh`. These counts/hashes do **not** certify the complete transitive trigger graph, live performance, effective privileges or runtime behavior. A separate query confirmed the candidate atomic RPC **absent** and candidate payoff index **absent** from production, as expected.

## 3. Exact release dependencies and evidence required

| Gate | Minimum evidence | Status |
| --- | --- | --- |
| A1 — QA recovery | Authorised Codespace access; read-only exit-255 Docker inspect, final logs/event classification, volume/backup integrity and documented approved recovery, without deleting or replacing container | **BLOCKED** |
| B1 — private archive | Owner-only `production_schema.dump`, no-password role inventory, SHA-256, secure directory/file permissions; offline `pg_restore --list` and extension topology | **BLOCKED** |
| B2/B3 — restored parity | In `alpha_hunter_private_qa`, exact structural/function/grant/role/extension fingerprints plus nested trigger DAG, GUC and dynamic dependency review; no treating old Stage 7 reference as full parity | **BLOCKED** |
| C — concurrency/integrity | Actual private PostgreSQL three-client identical-run races, overlapping distinct runs, immutable conflicting retry, injected timeout/rollback/lost-ACK/replay, zero missing/orphan/duplicate core and downstream records | **BLOCKED** |
| D — performance | Authentic durable 30/50/61 and peak symbol workload, baseline versus candidate index, p50/p95/p99/max over adequate samples, WAL/locks/IO and real local PostgREST service-role HTTP deadline | **BLOCKED** |
| E — full downstream | Strategy observations, quote/freeze, payoff, paper-order/decision/filled/protection/outcome evidence with linked run identities and invariant side-effect counts | **BLOCKED** |
| F — release authorisation | Two **independent** named qualified reviewers, evidence-reviewed DBA and security sign-off for immutable SHA; owner separately authorises a £0, paper-only, monitored rollout/rollback | **NOT SIGNED** |

## 4. Evidence honesty and acceptance signatures

- Prior Stage 7/8 **single fixture/serial** 61-symbol durable commits were valid limited QA observations. They do not satisfy C/D or B2/B3, do not certify a production p99 SLO, and cannot be reused to claim the final authentic matrix passed.
- Latest GitHub test success certifies only branch code and declared CI fixture coverage. It does not prove secure private archive custody, actual private Docker state or production deployment.
- **Independent DBA**: reviewer identity, qualification, exact commit SHA, signed schema/roles/trigger parity evidence, isolation and performance measurements, decision `PASS/FAIL`, UTC date — **PENDING**.
- **Independent security reviewer**: identity, qualification, exact commit SHA, effective grants/RLS/RPC execute role, no trade-authority escalation, auth/security boundaries, risk exceptions, decision `PASS/FAIL`, UTC date — **PENDING**.
- **Owner release decision**: explicit approval only after all mandatory gates pass. Until then **NO merge, schema change, deployment, production scanner restart, live orders or new spending**.

**Next action:** authorised owner/custodian reopens existing private Codespace and performs A1 read-only forensics, without restarting it until backup and root-cause assessment are documented. Then obtain B1/B2/B3 private material and verified QA parity. If that access is unavailable, stop at BLOCKED rather than inventing an authentic test result.
