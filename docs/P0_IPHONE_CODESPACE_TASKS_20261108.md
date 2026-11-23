# Alpha Hunter P0 — iPhone-friendly Codespace QA tasks (8 Nov 2026)

**Scope:** only the existing Codespace on `fix/supabase-write-timeout-qa`, draft PR #445. **Budget:** £0. **Production:** NO-GO. **Real orders:** disabled.

## First gate: preserve the stopped QA container (Task 0)

Before attempting any QA container start or schema restoration, use **Terminal → Run Task… → `Alpha Hunter P0 — 0. Diagnose existing QA container exit (read-only)`** in the already-authorised private Codespace. It runs `ops/local/p0_qa_exit255_readonly_diag_v01.py` and only inspects container identity, Docker state, mount types/counts and classified final log/event signals. It will not print raw logs, paths or secrets, and cannot restart or repair the container. If the container is missing, renamed, replaced or its image/network/branch identity differs, it returns `BLOCKED` and must not be bypassed. Exit 255 or a completed read-only diagnostic is **not** authorisation to restart: inspect the existing backup/archive custody separately before any change.

## Open the task menu without typing shell commands

1. Open the existing **congenial system** Codespace (not the `main` Codespace).
2. Update the repair branch in the Codespace using **Source Control → More Actions (⋯) → Pull**. Do not discard or overwrite uncommitted changes. The tasks appear only after this new commit is pulled.
3. In the VS Code main menu choose **Terminal → Run Task...** (or command palette **Tasks: Run Task**).
4. **First select Alpha Hunter P0 — 0. Diagnose existing QA container exit (read-only)**; read the sanitized result. Then run **Alpha Hunter P0 — 1. Check private QA readiness (read-only)**. Do not start/recreate/replace any QA container. There is no database password to enter for either task.

## Available manual tasks

| Task | Existing guarded script | What it does | What it DOES NOT do |
| --- | --- | --- | --- |
| 0. Diagnose existing QA container exit (read-only) | `ops/local/p0_qa_exit255_readonly_diag_v01.py` | Classifies preserved local QA container state, mount types/count, last logs and historical Docker events without exposing secrets | No restart, SQL connection, export, new container or backup verification |
| 1. Check private QA readiness (read-only) | `ops/local/check_private_pg17_clone_readiness_v01.sh` | Inspects local Codespace environment, cached PG17 image, and owner-only private archive presence | No production connection, archive export, container start, database writes or remote tests |
| 2. Inspect existing private archive (offline) | `ops/local/inspect_private_pg_archive_topology_v01.sh` | Only when a private archive already exists: checks archive file permissions, local schema-only TOC and known trigger/function names using an offline PG17 Docker image | Does not export, connect to production, restore, or certify the full graph |
| 3. Verify restored private PG17 clone (read-only) | `ops/local/verify_restored_private_pg17_fingerprints_v01.sh` | Only after an authorized clone is restored in the expected network-isolated container: compares structural hashes, selected functions, roles/ACL structure and extensions against inspected baseline | Does not create the clone, seed realistic workload, benchmark p95/p99 or issue independent approval |

Tasks are **manual only**, not configured to run on workspace open or from CI. The underlying scripts enforce the authenticated Codespace and isolated repair branch (and further safeguards where needed). No credentials or private function bodies are committed to this public repository.

## Interpret the read-only task outputs

- `QA_A1_RESULT=READ_ONLY_COMPLETE`: stopped-container forensic inspection completed, but **backup integrity is not verified and restart remains prohibited**.
- `QA_A1_RESULT=BLOCKED_*` or `QA_IDENTITY` mismatch: stop without replacing or restarting anything; preserve the existing state and review the QA identity privately.
- `QA_A1_RESULT=RUNNING_VERIFY_REFERENCE`: this only means the container is already running; it is not proof the restored schema is authentic.

- `AUTHENTIC_SCHEMA_DUMP=NOT_FOUND` / `NEXT_GATE=AUTHORISED_PRIVATE_SCHEMA_EXPORT`: the required archive is not available at the checked private location. **Stop**; stage 2/3 cannot pass yet.
- `AUTHENTIC_SCHEMA_DUMP=FOUND_PRIVATE_ARCHIVE_PERMISSIONS_OK`: the guarded private location contains at least one archive with expected file permissions. The existence check **is not** proof the contents are authentic or complete. Run Task 2 when appropriate.
- `LOCAL_DOCKER_DAEMON=UNAVAILABLE`: Docker is not currently usable. Stop rather than purchasing or starting new infrastructure.
- Any `BLOCKED`, `REFUSED`, or `FAIL`: preserve the output, do not bypass safeguards.

**Important:** Neither the task picker nor GitHub access can provide credentials or reach the existing private Codespace session on the user's behalf. If a new export is necessary, it remains a **separate, explicitly authorized, locally handled operation**; the guarded `ops/local/export_private_pg_schema.sh` is deliberately **not** registered as a one-click task. Never share passwords, archives, private function definitions, or sensitive output in chat or the public PR.

## Release boundary

These tasks are a convenience layer on top of existing isolated QA scripts, not a repair or acceptance result. A restored authentic production-equivalent clone, 30/50/61-symbol performance/correctness evidence, source-custody remediation, independent DBA/security approval and explicit owner authorization are still mandatory. Do not modify `main`, production SQL, scanners, automated safeguards, or trading permissions.
