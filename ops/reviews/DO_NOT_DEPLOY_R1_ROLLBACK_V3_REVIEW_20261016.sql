-- VERSIONED V3 PROPOSAL; NEVER RUN AGAINST PRODUCTION WITHOUT OWNER + DBA APPROVAL.
-- V3 R1 ROLLBACK DDL CANDIDATE (NOT PG INTEGRATION TESTED): OFFLINE FILE, DO NOT APPLY.
-- Must be separately approved; run only by dedicated migration DBA after
-- stopping any separately approved future reader first. Never delete source
-- historical rows, R10 scientific history, or persistent external incidents.
BEGIN;
DO $guard$
BEGIN
 IF current_database()<>'postgres' THEN RAISE EXCEPTION 'R1_ROLLBACK_WRONG_DATABASE'; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles
       WHERE rolname='alpha_hunter_p2_readonly' AND NOT rolcanlogin)
 THEN RAISE EXCEPTION 'R1_ROLLBACK_READER_LOGIN_STATE_CHANGED_REVIEW_REQUIRED'; END IF;
 IF (SELECT count(*) FROM pg_policy WHERE polname LIKE 'ah_p2_r1_%')<>14
 THEN RAISE EXCEPTION 'R1_ROLLBACK_POLICY_COUNT_DRIFT_REVIEW_REQUIRED'; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='alpha_hunter_p2_readonly')
 OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='alpha_hunter_p2_projection_owner')
 OR to_regnamespace('ah_p2_ro') IS NULL
 OR to_regclass('ah_p2_ro.parent_snapshot_v01') IS NULL
 OR to_regclass('ah_p2_ro.symbol_quote_v01') IS NULL THEN
  RAISE EXCEPTION 'R1_ROLLBACK_NOT_AT_EXPECTED_PRESTATE';
 END IF;
END
$guard$;
-- Non-superuser CREATEROLE migration actor requires explicit temporary SET.
-- Its automatic ADMIN-only grant permits the temporary SET edge.
GRANT alpha_hunter_p2_projection_owner TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
SET ROLE alpha_hunter_p2_projection_owner;
REVOKE SELECT ON ah_p2_ro.parent_snapshot_v01 FROM alpha_hunter_p2_readonly;
REVOKE SELECT ON ah_p2_ro.symbol_quote_v01 FROM alpha_hunter_p2_readonly;
REVOKE USAGE ON SCHEMA ah_p2_ro FROM alpha_hunter_p2_readonly;
DROP VIEW ah_p2_ro.symbol_quote_v01 RESTRICT;
DROP VIEW ah_p2_ro.parent_snapshot_v01 RESTRICT;
DROP SCHEMA ah_p2_ro RESTRICT;
RESET ROLE;
-- Leave the temporary SET membership until view/schema grants and all
-- owner-role dependencies have been removed; DROP ROLE removes it last.
-- An early REVOKE may raise 2BP01 for dependent privileges.

DROP POLICY ah_p2_r1_paper_orders_v02_select ON public.alpha_hunter_paper_orders_v02;
REVOKE SELECT (order_id, decision_id, submitted_at_utc, symbol, direction, order_type, quantity, paper_only, exchange_authority, trade_permission, order_path, successor_activation_id, successor_spec_id, successor_scientific_fingerprint_sha256, successor_source_run_id) ON TABLE public.alpha_hunter_paper_orders_v02 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_fills_v02_select ON public.alpha_hunter_paper_fills_v02;
REVOKE SELECT (fill_id, order_id, decision_id, fill_sequence, filled_at_utc, quantity, source_run_id, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_fills_v02 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_exit_fills_v04_select ON public.alpha_hunter_paper_exit_fills_v04;
REVOKE SELECT (exit_fill_id, entry_order_id, decision_id, source_run_id, triggered_protective_order_id, protection_type, filled_at_utc, quantity, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_fills_v04 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_exit_attempts_v04_select ON public.alpha_hunter_paper_exit_attempts_v04;
REVOKE SELECT (attempt_id, entry_order_id, decision_id, source_run_id, observed_at_utc, symbol, direction, outcome, triggered_protection_type, best_bid, best_ask, best_bid_size, best_ask_size, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_attempts_v04 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_protective_orders_v03_select ON public.alpha_hunter_paper_protective_orders_v03;
REVOKE SELECT (protective_order_id, entry_order_id, decision_id, activated_by_fill_id, created_at_utc, symbol, direction, protection_type, side, trigger_price, quantity, reduce_only, status, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_protective_orders_v03 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_events_v01_select ON public.alpha_hunter_paper_events_v01;
REVOKE SELECT (event_id, decision_id, sequence, occurred_at_utc, event_type, state, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_events_v01 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_exit_activation_v04_select ON public.alpha_hunter_paper_exit_activation_v04;
REVOKE SELECT (activation_id, activated_at_utc, release_git_commit, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_activation_v04 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_entry_quarantine_v06_select ON public.alpha_hunter_paper_entry_quarantine_v06;
REVOKE SELECT (order_id, decision_id, symbol, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_entry_quarantine_v06 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_exit_quarantine_v04_select ON public.alpha_hunter_paper_exit_quarantine_v04;
REVOKE SELECT (entry_order_id, decision_id, symbol, protection_created_at_utc, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_quarantine_v04 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_paper_reconciliation_quarantine_v04_select ON public.alpha_hunter_paper_reconciliation_quarantine_v04;
REVOKE SELECT (order_id, decision_id, symbol, submitted_at_utc, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_reconciliation_quarantine_v04 FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_snapshots_select ON public.alpha_hunter_snapshots;
REVOKE SELECT (run_id, collected_at_utc, version, product_type, symbol_count, error_count, created_at) ON TABLE public.alpha_hunter_snapshots FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_symbol_snapshots_select ON public.alpha_hunter_symbol_snapshots;
REVOKE SELECT (run_id, symbol, collected_at_utc, state, previous_state, trade_permission, direction, last_price, open_interest, funding_rate, data_integrity_score, error, created_at) ON TABLE public.alpha_hunter_symbol_snapshots FROM alpha_hunter_p2_readonly;

DROP POLICY ah_p2_r1_parent_owner_select ON public.alpha_hunter_snapshots;
REVOKE SELECT (run_id, collected_at_utc, version, product_type, symbol_count, error_count, created_at, payload) ON TABLE public.alpha_hunter_snapshots FROM alpha_hunter_p2_projection_owner;

DROP POLICY ah_p2_r1_symbol_owner_select ON public.alpha_hunter_symbol_snapshots;
REVOKE SELECT (run_id, symbol, collected_at_utc, state, previous_state, trade_permission, direction, last_price, open_interest, funding_rate, data_integrity_score, error, created_at, payload) ON TABLE public.alpha_hunter_symbol_snapshots FROM alpha_hunter_p2_projection_owner;

REVOKE USAGE ON SCHEMA public FROM alpha_hunter_p2_readonly, alpha_hunter_p2_projection_owner;
REVOKE CONNECT ON DATABASE postgres FROM alpha_hunter_p2_readonly;
-- DROP ROLE automatically removes role-specific ALTER ROLE settings.
-- If newly added external dependencies exist, RESTRICT semantics fail safely;
-- never substitute CASCADE to force removal.
DROP ROLE alpha_hunter_p2_readonly;
-- Automatic ADMIN membership is removed by owner role deletion. There must
-- be NO unrelated dependents: role DROP fails closed if any remain.
DROP ROLE alpha_hunter_p2_projection_owner;
COMMIT;