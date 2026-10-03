# R8 reconciliation gate tests

Run `npm ci --ignore-scripts && npm test` here with Node 22+.
Pinned PGlite executes the actual containment SQL in an empty PostgreSQL WASM
database with synthetic upstream tables. No credentials or live data are used.

The original PR head failed five of these six tests: closed, NULL, and absent
gates hid unresolved exposure, and gate reopening/recent-entry containment
checks failed. The corrected migration passes all six. The existing scope test
also passes: partial fills, quarantined entries, pre-activation orders and
unrelated reconciliation events cannot enter this recovery path.

Inventory and exposure visibility are independent of the deployment gate.
The runtime worklist remains gated. A closed/unknown/missing gate does not
authorize processing or imply that an expiry will run. The status explicitly
reports blocked processing with visible unresolved entries.

The tests also check service-role read access, absence of INSERT permission,
migration reapplication, and explicit expiry releasing containment without
generating a fill or deleting the earlier event.

Limits: synthetic schema, single-session execution, no production extension or
performance verification. This patch does not resolve the separate successor
cohort/horizon deployment gate and does not authorize deployment into active R8.
