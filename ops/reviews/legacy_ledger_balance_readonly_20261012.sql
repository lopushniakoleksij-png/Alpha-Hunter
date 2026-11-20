-- Shadow-only, SELECT-only all-history ledger balance audit.
-- Complements legacy_residual_coverage_readonly_20261012.sql.
-- A positive residual means unresolved modeled paper exposure, not a live trade.
-- No cohort/date/lifecycle-state filter; no replay, backfill or permission change.
WITH orders AS (
  SELECT order_id, symbol, direction, quantity AS ordered_quantity
  FROM public.alpha_hunter_paper_orders_v02
), fills AS (
  SELECT order_id, COUNT(*) AS fill_events, SUM(quantity) AS filled_quantity
  FROM public.alpha_hunter_paper_fills_v02 GROUP BY order_id
), exits AS (
  SELECT entry_order_id AS order_id, COUNT(*) AS exit_events, SUM(quantity) AS exited_quantity
  FROM public.alpha_hunter_paper_exit_fills_v04 GROUP BY entry_order_id
), ledger AS (
  SELECT COALESCE(o.order_id, f.order_id, e.order_id) AS order_id,
         o.symbol, o.direction, o.ordered_quantity,
         COALESCE(f.fill_events,0) AS fill_events,
         COALESCE(e.exit_events,0) AS exit_events,
         COALESCE(f.filled_quantity,0) AS filled_quantity,
         COALESCE(e.exited_quantity,0) AS exited_quantity,
         COALESCE(f.filled_quantity,0)-COALESCE(e.exited_quantity,0) AS residual_quantity,
         CASE
           WHEN o.order_id IS NULL THEN 'ORPHAN_FILL_OR_EXIT'
           WHEN o.ordered_quantity <= 0 THEN 'INVALID_ORDER_QUANTITY'
           WHEN COALESCE(f.filled_quantity,0) < 0 OR COALESCE(e.exited_quantity,0) < 0 THEN 'NEGATIVE_LEDGER_QUANTITY'
           WHEN COALESCE(f.filled_quantity,0) > o.ordered_quantity + 0.000000000001 THEN 'FILLED_GREATER_THAN_ORDERED'
           WHEN COALESCE(e.exited_quantity,0) > COALESCE(f.filled_quantity,0) + 0.000000000001 THEN 'EXIT_GREATER_THAN_FILLED'
           WHEN COALESCE(f.filled_quantity,0)-COALESCE(e.exited_quantity,0) > 0.000000000001 THEN 'POSITIVE_RESIDUAL_REQUIRES_COVERAGE_AUDIT'
           ELSE 'BALANCED_OR_UNFILLED'
         END AS ledger_state
  FROM orders o
  FULL OUTER JOIN fills f ON f.order_id=o.order_id
  FULL OUTER JOIN exits e ON e.order_id=COALESCE(o.order_id,f.order_id)
)
SELECT ledger_state, COUNT(*) AS order_count,
       COUNT(*) FILTER (WHERE residual_quantity > 0.000000000001) AS positive_residual_orders
FROM ledger
GROUP BY ledger_state
ORDER BY ledger_state;
