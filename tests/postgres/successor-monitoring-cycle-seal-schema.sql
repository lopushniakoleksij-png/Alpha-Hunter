-- SUCCESSOR SHADOW SCIENTIFIC RESEARCH ONLY.
-- NO PRODUCTION MIGRATION / NO SUPABASE DEPLOYMENT. Use ONLY an isolated
-- PostgreSQL instance. The tables are INTERNAL, not an exposed Data API.
-- A seal is a LOCAL STRUCTURAL PROOF, NOT actual venue protection,
-- no historical R10 repair, and NOT authorization for R10 admissions.
CREATE SCHEMA successor_shadow;
REVOKE ALL ON SCHEMA successor_shadow FROM PUBLIC;

CREATE TABLE successor_shadow.cycles (
  run_id text PRIMARY KEY REFERENCES public.alpha_hunter_snapshots(run_id),
  collected_at_utc timestamptz NOT NULL,
  run_source text NOT NULL CHECK(run_source='RENDER_CRON'),
  runtime_role text NOT NULL CHECK(runtime_role='RENDER_CRON'),
  fingerprint text NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
  expected_symbol_count integer NOT NULL CHECK(expected_symbol_count>=0),
  expected_position_count integer NOT NULL CHECK(expected_position_count>=0),
  symbol_manifest_source text NOT NULL CHECK(length(trim(symbol_manifest_source))>0),
  position_inventory_source text NOT NULL CHECK(length(trim(position_inventory_source))>0),
  position_inventory_asof_utc timestamptz NOT NULL,
  position_inventory_attested_complete boolean NOT NULL CHECK(position_inventory_attested_complete=true),
  source_policy_id text NOT NULL CHECK(length(trim(source_policy_id))>0),
  approved_quote_sources text[] NOT NULL CHECK(cardinality(approved_quote_sources)>0),
  max_quote_offset_seconds integer NOT NULL CHECK(max_quote_offset_seconds>0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK(position_inventory_asof_utc<=collected_at_utc),
  CHECK(position_inventory_asof_utc>=collected_at_utc-interval '35 minutes')
);

-- Exact symbol identity matters; matching the count alone is insufficient.
CREATE TABLE successor_shadow.expected_symbols(
  run_id text NOT NULL REFERENCES successor_shadow.cycles(run_id),
  symbol text NOT NULL CHECK(length(trim(symbol))>0 AND symbol=upper(symbol)),
  PRIMARY KEY(run_id,symbol)
);
CREATE TABLE successor_shadow.committed_symbols(
  run_id text NOT NULL REFERENCES successor_shadow.cycles(run_id),
  symbol text NOT NULL CHECK(length(trim(symbol))>0 AND symbol=upper(symbol)),
  source_row_id text NOT NULL CHECK(length(trim(source_row_id))>0),
  PRIMARY KEY(run_id,symbol),
  FOREIGN KEY(run_id,symbol) REFERENCES public.alpha_hunter_symbol_snapshots(run_id,symbol)
);

-- The initial FILL_ATTESTED reference is external to this isolated schema and
-- CANNOT be independently validated by this prototype. A prospective real
-- successor must JOIN an immutable as-of fill/source ledger before promotions.
-- PRIOR_SEALED_CYCLE IS locally verifiable, preventing manufactured continuity.
CREATE TABLE successor_shadow.expected_positions(
  run_id text NOT NULL REFERENCES successor_shadow.cycles(run_id),
  entry_order_id text NOT NULL CHECK(length(trim(entry_order_id))>0),
  symbol text NOT NULL CHECK(length(trim(symbol))>0 AND symbol=upper(symbol)),
  direction text NOT NULL CHECK(direction IN ('LONG','SHORT')),
  basis_kind text NOT NULL CHECK(basis_kind IN ('FILL_ATTESTED','PRIOR_SEALED_CYCLE')),
  basis_source_id text NOT NULL CHECK(length(trim(basis_source_id))>0),
  basis_qualified_at_utc timestamptz NOT NULL,
  PRIMARY KEY(run_id,entry_order_id),
  CHECK(basis_qualified_at_utc<=now())
);

-- This is evidence about an existing paper-position monitoring ATTEMPT.
-- It never places an order and never creates an exit fill.
CREATE TABLE successor_shadow.position_monitoring(
  run_id text NOT NULL,
  entry_order_id text NOT NULL,
  attempt_id text NOT NULL UNIQUE CHECK(length(trim(attempt_id))>0),
  source_run_id text NOT NULL,
  symbol text NOT NULL,
  direction text NOT NULL CHECK(direction IN ('LONG','SHORT')),
  outcome text NOT NULL CHECK(outcome IN('NO_TRIGGER','STOP_TRIGGERED','TARGET_TRIGGERED','HORIZON_CLOSED')),
  quote_source text NOT NULL CHECK(length(trim(quote_source))>0),
  captured_at_utc timestamptz NOT NULL,
  bid numeric NOT NULL CHECK(bid>0),
  ask numeric NOT NULL CHECK(ask>0),
  bid_size numeric NOT NULL CHECK(bid_size>0),
  ask_size numeric NOT NULL CHECK(ask_size>0),
  paper_only boolean NOT NULL DEFAULT true CHECK(paper_only=true),
  exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
  trade_permission boolean NOT NULL DEFAULT false CHECK(trade_permission=false),
  order_path text NOT NULL DEFAULT 'NONE' CHECK(order_path='NONE'),
  PRIMARY KEY(run_id,entry_order_id),
  FOREIGN KEY(run_id,entry_order_id)
    REFERENCES successor_shadow.expected_positions(run_id,entry_order_id),
  CHECK(source_run_id=run_id),
  CHECK(ask>=bid)
);

CREATE TABLE successor_shadow.completed_cycles(
  run_id text PRIMARY KEY REFERENCES successor_shadow.cycles(run_id),
  completed_at_utc timestamptz NOT NULL DEFAULT clock_timestamp(),
  status text NOT NULL DEFAULT 'LOCAL_STRUCTURAL_COMPLETE_NOT_SCIENTIFIC_PASS'
    CHECK(status='LOCAL_STRUCTURAL_COMPLETE_NOT_SCIENTIFIC_PASS'),
  paper_authority boolean NOT NULL DEFAULT false CHECK(paper_authority=false),
  exchange_authority boolean NOT NULL DEFAULT false CHECK(exchange_authority=false),
  scientific_pass_permitted boolean NOT NULL DEFAULT false CHECK(scientific_pass_permitted=false)
);

-- Immutable evidence: no UPDATE/DELETE to "repair" failed/historic runs.
CREATE FUNCTION successor_shadow.reject_mutation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 RAISE EXCEPTION 'SUCCESSOR_SHADOW_APPEND_ONLY';
END
$$;
CREATE FUNCTION successor_shadow.guard_new_evidence() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 -- Serializes inserts with finalize's SELECT FOR UPDATE of this same cycle.
 PERFORM 1 FROM successor_shadow.cycles
 WHERE run_id=NEW.run_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM successor_shadow.completed_cycles WHERE run_id=NEW.run_id) THEN
  RAISE EXCEPTION 'SUCCESSOR_SHADOW_CYCLE_ALREADY_SEALED';
 END IF;
 RETURN NEW;
END
$$;
-- Explicit trigger list; no implicit triggers on main/production tables.
CREATE TRIGGER immutable_cycles BEFORE UPDATE OR DELETE ON successor_shadow.cycles
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER immutable_expected_symbols BEFORE UPDATE OR DELETE ON successor_shadow.expected_symbols
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER immutable_committed_symbols BEFORE UPDATE OR DELETE ON successor_shadow.committed_symbols
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER immutable_expected_positions BEFORE UPDATE OR DELETE ON successor_shadow.expected_positions
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER immutable_position_monitoring BEFORE UPDATE OR DELETE ON successor_shadow.position_monitoring
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER immutable_completed_cycles BEFORE UPDATE OR DELETE ON successor_shadow.completed_cycles
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.reject_mutation();
CREATE TRIGGER guard_expected_symbols BEFORE INSERT ON successor_shadow.expected_symbols
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.guard_new_evidence();
CREATE TRIGGER guard_committed_symbols BEFORE INSERT ON successor_shadow.committed_symbols
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.guard_new_evidence();
CREATE TRIGGER guard_expected_positions BEFORE INSERT ON successor_shadow.expected_positions
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.guard_new_evidence();
CREATE TRIGGER guard_position_monitoring BEFORE INSERT ON successor_shadow.position_monitoring
 FOR EACH ROW EXECUTE FUNCTION successor_shadow.guard_new_evidence();

CREATE FUNCTION successor_shadow.try_seal_cycle(p_run_id text) RETURNS text
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r successor_shadow.cycles%ROWTYPE;
BEGIN
 SELECT * INTO r FROM successor_shadow.cycles
 WHERE run_id=p_run_id FOR UPDATE;
 IF NOT FOUND THEN RETURN 'UNKNOWN_OR_INCOMPLETE_MISSING_RUN'; END IF;
 IF EXISTS(SELECT 1 FROM successor_shadow.completed_cycles WHERE run_id=p_run_id) THEN
  RETURN 'ALREADY_SEALED_STRUCTURAL_ONLY';
 END IF;
 IF (SELECT count(*) FROM successor_shadow.expected_symbols WHERE run_id=p_run_id)
     <>r.expected_symbol_count OR
    (SELECT count(*) FROM successor_shadow.committed_symbols WHERE run_id=p_run_id)
     <>r.expected_symbol_count OR
    EXISTS(SELECT 1 FROM successor_shadow.expected_symbols e
      WHERE e.run_id=p_run_id AND NOT EXISTS(
       SELECT 1 FROM successor_shadow.committed_symbols s
       WHERE s.run_id=e.run_id AND s.symbol=e.symbol)) OR
    EXISTS(SELECT 1 FROM successor_shadow.committed_symbols s
      WHERE s.run_id=p_run_id AND NOT EXISTS(
       SELECT 1 FROM successor_shadow.expected_symbols e
       WHERE e.run_id=s.run_id AND e.symbol=s.symbol))
 THEN
  RETURN 'UNKNOWN_OR_INCOMPLETE_SYMBOL_STAGE';
 END IF;
 IF (SELECT count(*) FROM successor_shadow.expected_positions WHERE run_id=p_run_id)
      <>r.expected_position_count OR
    (SELECT count(*) FROM successor_shadow.position_monitoring WHERE run_id=p_run_id)
      <>r.expected_position_count
 THEN
  RETURN 'UNKNOWN_OR_INCOMPLETE_POSITION_COUNT';
 END IF;
 IF EXISTS(
  SELECT 1 FROM successor_shadow.expected_positions p
  LEFT JOIN successor_shadow.position_monitoring m
   ON m.run_id=p.run_id AND m.entry_order_id=p.entry_order_id
  WHERE p.run_id=p_run_id AND (
   m.entry_order_id IS NULL OR m.symbol<>p.symbol OR m.direction<>p.direction
   OR NOT(m.quote_source=ANY(r.approved_quote_sources))
   OR ABS(EXTRACT(EPOCH FROM (m.captured_at_utc-r.collected_at_utc)))
       >r.max_quote_offset_seconds
   OR m.captured_at_utc<p.basis_qualified_at_utc
   OR m.captured_at_utc-p.basis_qualified_at_utc>interval '35 minutes'
   OR (p.basis_kind='PRIOR_SEALED_CYCLE' AND NOT EXISTS(
      SELECT 1 FROM successor_shadow.completed_cycles previous_seal
      JOIN successor_shadow.position_monitoring previous_attempt
       ON previous_attempt.run_id=previous_seal.run_id
      WHERE previous_seal.run_id=p.basis_source_id
       AND previous_attempt.entry_order_id=p.entry_order_id
       AND previous_attempt.symbol=p.symbol
       AND previous_attempt.direction=p.direction
       AND previous_attempt.captured_at_utc=p.basis_qualified_at_utc
   ))
  )
 ) THEN
  RETURN 'UNKNOWN_OR_INCOMPLETE_POSITION_EVIDENCE_OR_35M_GAP';
 END IF;
 INSERT INTO successor_shadow.completed_cycles(run_id) VALUES(p_run_id);
 RETURN 'SEALED_LOCAL_STRUCTURAL_ONLY';
END
$$;

REVOKE ALL ON ALL TABLES IN SCHEMA successor_shadow FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA successor_shadow FROM PUBLIC;
