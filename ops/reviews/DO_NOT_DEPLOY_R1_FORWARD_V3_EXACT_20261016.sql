-- VERSIONED V3 PROPOSAL; NEVER RUN AGAINST PRODUCTION WITHOUT OWNER + DBA APPROVAL.
-- V3 R1 FORWARD DDL CANDIDATE (NOT PG INTEGRATION TESTED): OFFLINE FILE, DO NOT APPLY.
-- User has NOT authorized production access changes. Review-only.
-- Target if/when separately approved: Supabase PostgreSQL database postgres, PG >= 16.
-- No secrets, no live order authority, no UPDATE of paper source rows.
-- R1 security REVIEW revision: the reader is provisioned NOLOGIN, no credential.
-- Do not ALTER ROLE to LOGIN in this migration; require a distinct R1 activation approval.
-- 12 exact base tables: reader gets column-scoped SELECT + role-specific RLS.
-- Non-LOGIN, non-bypassRLS projection owner can read raw snapshot JSON;
-- NOLOGIN reader remains disabled until SEPARATE authorization; after authorized enablement it may read ONLY redacted scalar fields in two views, NOT JSON.
-- SECURITY: view-owner rights are intentional, not SECURITY INVOKER;
-- the owner is NOT a base-table owner and has explicit RLS policies.
-- Requires approved elevated DBA migration identity able to CREATE ROLE,
-- CREATE SCHEMA AUTHORIZATION and ALTER VIEW OWNER; rehearse with identical rights.
BEGIN;
DO $preflight$
DECLARE n integer;
BEGIN
 IF current_database()<>'postgres' OR current_setting('server_version_num')::integer<160000 THEN
  RAISE EXCEPTION 'R1_REFUSE_UNEXPECTED_DATABASE_OR_PG_VERSION';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN
   ('alpha_hunter_p2_readonly','alpha_hunter_p2_projection_owner'))
    OR to_regnamespace('ah_p2_ro') IS NOT NULL THEN
  RAISE EXCEPTION 'R1_REFUSE_ALREADY_PRESENT_ROLE_OR_SCHEMA';
 END IF;
 SELECT count(*) INTO n FROM (VALUES
 ('public.alpha_hunter_paper_orders_v02'),
 ('public.alpha_hunter_paper_fills_v02'),
 ('public.alpha_hunter_paper_exit_fills_v04'),
 ('public.alpha_hunter_paper_exit_attempts_v04'),
 ('public.alpha_hunter_paper_protective_orders_v03'),
 ('public.alpha_hunter_paper_events_v01'),
 ('public.alpha_hunter_paper_exit_activation_v04'),
 ('public.alpha_hunter_paper_entry_quarantine_v06'),
 ('public.alpha_hunter_paper_exit_quarantine_v04'),
 ('public.alpha_hunter_paper_reconciliation_quarantine_v04'),
 ('public.alpha_hunter_snapshots'),
 ('public.alpha_hunter_symbol_snapshots')
 ) AS expected(full_name)
 JOIN pg_class c ON c.oid=to_regclass(expected.full_name)
 JOIN pg_namespace ns ON ns.oid=c.relnamespace
 WHERE ns.nspname='public' AND c.relkind IN ('r','p')
   AND c.relrowsecurity
   AND NOT EXISTS (SELECT 1 FROM pg_policy pol WHERE pol.polrelid=c.oid);
 IF n<>12 THEN RAISE EXCEPTION 'R1_REFUSE_SOURCE_RELATION_OR_RLS_POLICY_BASELINE_CHANGED_%',n; END IF;
END
$preflight$;

CREATE ROLE alpha_hunter_p2_readonly NOLOGIN PASSWORD NULL NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE alpha_hunter_p2_projection_owner NOLOGIN NOINHERIT NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
-- Temporary SET access to the NOLOGIN non-bypassRLS view owner only; no INHERIT.
-- PG16+ keeps the automatic ADMIN TRUE / SET FALSE / INHERIT FALSE
-- creator membership after the temporary SET edge is later revoked.
GRANT alpha_hunter_p2_projection_owner TO CURRENT_USER WITH SET TRUE, INHERIT FALSE;
ALTER ROLE alpha_hunter_p2_readonly SET statement_timeout = '12s';
ALTER ROLE alpha_hunter_p2_readonly SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE postgres TO alpha_hunter_p2_readonly;
GRANT USAGE ON SCHEMA public TO alpha_hunter_p2_readonly, alpha_hunter_p2_projection_owner;
-- Migrator owns DB CREATE; NOLOGIN projection owner does not get DB CREATE.
-- Migrator requires the deliberately temporary ability to SET ROLE to owner.
CREATE SCHEMA ah_p2_ro AUTHORIZATION alpha_hunter_p2_projection_owner;

GRANT SELECT (order_id, decision_id, submitted_at_utc, symbol, direction, order_type, quantity, paper_only, exchange_authority, trade_permission, order_path, successor_activation_id, successor_spec_id, successor_scientific_fingerprint_sha256, successor_source_run_id) ON TABLE public.alpha_hunter_paper_orders_v02 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_orders_v02_select ON public.alpha_hunter_paper_orders_v02 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (fill_id, order_id, decision_id, fill_sequence, filled_at_utc, quantity, source_run_id, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_fills_v02 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_fills_v02_select ON public.alpha_hunter_paper_fills_v02 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (exit_fill_id, entry_order_id, decision_id, source_run_id, triggered_protective_order_id, protection_type, filled_at_utc, quantity, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_fills_v04 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_exit_fills_v04_select ON public.alpha_hunter_paper_exit_fills_v04 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (attempt_id, entry_order_id, decision_id, source_run_id, observed_at_utc, symbol, direction, outcome, triggered_protection_type, best_bid, best_ask, best_bid_size, best_ask_size, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_attempts_v04 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_exit_attempts_v04_select ON public.alpha_hunter_paper_exit_attempts_v04 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (protective_order_id, entry_order_id, decision_id, activated_by_fill_id, created_at_utc, symbol, direction, protection_type, side, trigger_price, quantity, reduce_only, status, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_protective_orders_v03 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_protective_orders_v03_select ON public.alpha_hunter_paper_protective_orders_v03 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (event_id, decision_id, sequence, occurred_at_utc, event_type, state, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_events_v01 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_events_v01_select ON public.alpha_hunter_paper_events_v01 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (activation_id, activated_at_utc, release_git_commit, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_activation_v04 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_exit_activation_v04_select ON public.alpha_hunter_paper_exit_activation_v04 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (order_id, decision_id, symbol, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_entry_quarantine_v06 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_entry_quarantine_v06_select ON public.alpha_hunter_paper_entry_quarantine_v06 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (entry_order_id, decision_id, symbol, protection_created_at_utc, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_exit_quarantine_v04 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_exit_quarantine_v04_select ON public.alpha_hunter_paper_exit_quarantine_v04 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (order_id, decision_id, symbol, submitted_at_utc, quarantined_at_utc, reason, paper_only, exchange_authority, trade_permission, order_path) ON TABLE public.alpha_hunter_paper_reconciliation_quarantine_v04 TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_paper_reconciliation_quarantine_v04_select ON public.alpha_hunter_paper_reconciliation_quarantine_v04 AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (run_id, collected_at_utc, version, product_type, symbol_count, error_count, created_at) ON TABLE public.alpha_hunter_snapshots TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_snapshots_select ON public.alpha_hunter_snapshots AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (run_id, symbol, collected_at_utc, state, previous_state, trade_permission, direction, last_price, open_interest, funding_rate, data_integrity_score, error, created_at) ON TABLE public.alpha_hunter_symbol_snapshots TO alpha_hunter_p2_readonly;
CREATE POLICY ah_p2_r1_symbol_snapshots_select ON public.alpha_hunter_symbol_snapshots AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_readonly USING (true);

GRANT SELECT (run_id, collected_at_utc, version, product_type, symbol_count, error_count, created_at, payload) ON TABLE public.alpha_hunter_snapshots TO alpha_hunter_p2_projection_owner;
CREATE POLICY ah_p2_r1_parent_owner_select
 ON public.alpha_hunter_snapshots AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_projection_owner USING (true);

GRANT SELECT (run_id, symbol, collected_at_utc, state, previous_state, trade_permission, direction, last_price, open_interest, funding_rate, data_integrity_score, error, created_at, payload) ON TABLE public.alpha_hunter_symbol_snapshots TO alpha_hunter_p2_projection_owner;
CREATE POLICY ah_p2_r1_symbol_owner_select
 ON public.alpha_hunter_symbol_snapshots AS PERMISSIVE FOR SELECT
 TO alpha_hunter_p2_projection_owner USING (true);

-- The view DEFINER role is intentionally not a source-table owner and cannot
-- bypass RLS; reader is not a member of the definer role and has NO payload grant.
-- Null/missing parent identity fields must be fail-closed at the consumer.
-- Switch into the NOLOGIN, non-bypass-RLS role to CREATE the views
-- directly with the correct owner. This avoids ALTER VIEW OWNER to a role
-- that the migration principal cannot SET and avoids broad database CREATE.
SET ROLE alpha_hunter_p2_projection_owner;
REVOKE ALL ON SCHEMA ah_p2_ro FROM PUBLIC;
GRANT USAGE ON SCHEMA ah_p2_ro TO alpha_hunter_p2_readonly;
CREATE VIEW ah_p2_ro.parent_snapshot_v01
 WITH (security_barrier = true, security_invoker = false) AS
SELECT run_id, collected_at_utc, version, product_type, symbol_count,
       error_count, created_at,
       jsonb_typeof(payload->'validation_identity') AS validation_identity_type,
       payload #>> '{validation_identity,run_source}' AS run_source,
       payload #>> '{validation_identity,git_commit}' AS git_commit,
       payload #>> '{validation_identity,config_sha256}' AS config_sha256,
       payload #>> '{validation_identity,scientific_fingerprint_sha256}' AS scientific_fingerprint_sha256,
       payload #>> '{validation_identity,scientific_fingerprint_version}' AS scientific_fingerprint_version
FROM public.alpha_hunter_snapshots;
REVOKE ALL ON ah_p2_ro.parent_snapshot_v01 FROM PUBLIC;
GRANT SELECT ON ah_p2_ro.parent_snapshot_v01 TO alpha_hunter_p2_readonly;

-- No raw JSON, strategy arrays, top-of-book lists, or private trade IDs.
-- Text fields are not trusted numeric/time types; a consumer must parse,
-- range-check, corroborate source clock and reject missing/malformed values.
CREATE VIEW ah_p2_ro.symbol_quote_v01
 WITH (security_barrier = true, security_invoker = false) AS
SELECT run_id, symbol, collected_at_utc, state, previous_state,
       trade_permission, direction, last_price, open_interest, funding_rate,
       data_integrity_score, error, created_at,
       jsonb_typeof(payload->'microstructure') AS microstructure_type,
       payload #>> '{microstructure,status}' AS microstructure_status,
       payload #>> '{microstructure,read_only}' AS microstructure_read_only_text,
       payload #>> '{microstructure,source_skew_ms}' AS source_skew_ms_text,
       payload #>> '{microstructure,ticker_timestamp_ms}' AS ticker_timestamp_ms_text,
       payload #>> '{microstructure,order_book,status}' AS order_book_status,
       payload #>> '{microstructure,order_book,source}' AS order_book_source,
       payload #>> '{microstructure,order_book,best_bid}' AS best_bid_text,
       payload #>> '{microstructure,order_book,best_ask}' AS best_ask_text,
       payload #>> '{microstructure,order_book,exchange_timestamp_ms}' AS order_book_exchange_timestamp_ms_text,
       payload #>> '{microstructure,recent_trades,status}' AS recent_trades_status,
       payload #>> '{microstructure,recent_trades,source}' AS recent_trades_source,
       payload #>> '{microstructure,recent_trades,newest_trade_timestamp_ms}' AS newest_trade_timestamp_ms_text
FROM public.alpha_hunter_symbol_snapshots;
REVOKE ALL ON ah_p2_ro.symbol_quote_v01 FROM PUBLIC;
GRANT SELECT ON ah_p2_ro.symbol_quote_v01 TO alpha_hunter_p2_readonly;
RESET ROLE;
REVOKE alpha_hunter_p2_projection_owner FROM CURRENT_USER;
-- Fail the same transaction if any temporary SET or INHERIT membership
-- persists. One documented automatic ADMIN-only membership is expected.
DO $r1_ownership_guard$
DECLARE memberships integer;
BEGIN
 SELECT count(*) INTO memberships FROM pg_auth_members m
 JOIN pg_roles target ON target.oid=m.roleid
 JOIN pg_roles member ON member.oid=m.member
 WHERE target.rolname='alpha_hunter_p2_projection_owner'
   AND member.rolname=current_user
   AND m.admin_option AND NOT m.set_option AND NOT m.inherit_option;
 IF memberships<>1 OR pg_has_role(current_user,'alpha_hunter_p2_projection_owner','SET')
 OR EXISTS(SELECT 1 FROM pg_auth_members m
 JOIN pg_roles target ON target.oid=m.roleid
 JOIN pg_roles member ON member.oid=m.member
 WHERE target.rolname='alpha_hunter_p2_projection_owner' AND member.rolname=current_user
 AND (m.set_option OR m.inherit_option)) THEN
  RAISE EXCEPTION 'R1_TEMP_SET_GRANT_CLEANUP_FAILED';
 END IF;
END
$r1_ownership_guard$;

-- Owner not bound by this review; credentials deliberately absent.
-- No scientific monitoring PASS is established by these views.
COMMIT;