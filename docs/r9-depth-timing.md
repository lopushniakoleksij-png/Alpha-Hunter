# R9 depth and timing diagnostic

Forward-only companion to the frozen R9 paper test. The collector runs in a
separate GitHub Actions job every five minutes (best effort; actual gaps are
reported). No Render restart, scanner integration or execution changes required.

It selects only unfilled R9 LIMIT orders with a SUBMITTED latest state, at most
35 minutes old, after checking active R9 identity and a fresh matched canonical
scan. It reads Bitget public depth; its only writes are to two new diagnostic
tables. It records all observations, failures and worker start/end events.

Each capture stores the order snapshot, request/receipt times, exchange timestamp,
returned bids/asks, entry distance and displayed capacity. Books older than 30
seconds or more than 5 seconds in the future are rejected. Invalid, non-finite,
duplicate-price, empty or crossed books cannot support a capacity verdict.
Responses after expiry are explicitly labelled. Orders may close during a request;
the stored selection snapshot is not a claim that they remained open at receipt.

`RETURNED_DEPTH_INSUFFICIENT` means only the returned book was insufficient.
Displayed quantity/VWAP is not an exchange fill, queue-position estimate or profit.
Neither diagnostic table enters R9 admissions, fills, exits or profitability.
Historical missed touches are unknown and never reconstructed as fills.

Deployment: install `ops/sql/r9_depth_timing_v01.sql`, then merge the tested
workflow. A push starts one collection; the schedule collects future observations.
Inspect run START/END pairs for interruption, counts for failures, and
`alpha_hunter_r9_depth_timing_gaps_v01` for actual sampling gaps. Five-minute
scheduling is not a latency guarantee. Disable only this workflow for rollback;
retain append-only evidence and keep discovery/execution running.
