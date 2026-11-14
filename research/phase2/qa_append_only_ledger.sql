-- Phase 2 isolated QA migration ONLY. Do not apply to production.
-- Prospective append-only ledger. Existing R10 and canonical tables untouched.
BEGIN;
CREATE SCHEMA IF NOT EXISTS alpha_hunter_phase2_qa;
CREATE TABLE IF NOT EXISTS alpha_hunter_phase2_qa.signal_investigations (
  investigation_id text PRIMARY KEY,
  signal_id text NOT NULL,
  contract_version text NOT NULL,
  observed_at_utc timestamptz NOT NULL,
  source_run_id text,
  source_state text,
  strategy_id text,
  direction text,
  disposition text NOT NULL,
  entry_price numeric,
  stop_loss numeric,
  take_profit numeric,
  market_features jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_quality text NOT NULL CHECK (evidence_quality IN ('VERIFIED','PARTIAL','UNKNOWN')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (signal_id, contract_version)
);
CREATE TABLE IF NOT EXISTS alpha_hunter_phase2_qa.investigation_observations (
  observation_id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES alpha_hunter_phase2_qa.signal_investigations(investigation_id),
  observed_at_utc timestamptz NOT NULL,
  recorded_at_utc timestamptz NOT NULL DEFAULT now(),
  source_row_id text,
  source_kind text NOT NULL,
  evidence_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (investigation_id, source_kind, source_row_id)
);
CREATE TABLE IF NOT EXISTS alpha_hunter_phase2_qa.investigation_adjudications (
  adjudication_id text PRIMARY KEY,
  investigation_id text NOT NULL REFERENCES alpha_hunter_phase2_qa.signal_investigations(investigation_id),
  adjudicated_at_utc timestamptz NOT NULL DEFAULT now(),
  ruleset_version text NOT NULL,
  result text NOT NULL CHECK (result IN ('TP_FIRST','SL_FIRST','AMBIGUOUS','UNKNOWN','NO_ENTRY','OPEN_AT_HORIZON','NOT_EVALUABLE')),
  hypothetical boolean NOT NULL,
  reason_code text NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (investigation_id, ruleset_version)
);
-- Block updates/deletes to prevent evidence rewriting, including by owner-level DML.
CREATE OR REPLACE FUNCTION alpha_hunter_phase2_qa.reject_evidence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Phase 2 evidence is append-only'; END $$;
CREATE TRIGGER phase2_no_mutate_investigations BEFORE UPDATE OR DELETE ON alpha_hunter_phase2_qa.signal_investigations FOR EACH ROW EXECUTE FUNCTION alpha_hunter_phase2_qa.reject_evidence_mutation();
CREATE TRIGGER phase2_no_mutate_observations BEFORE UPDATE OR DELETE ON alpha_hunter_phase2_qa.investigation_observations FOR EACH ROW EXECUTE FUNCTION alpha_hunter_phase2_qa.reject_evidence_mutation();
CREATE TRIGGER phase2_no_mutate_adjudications BEFORE UPDATE OR DELETE ON alpha_hunter_phase2_qa.investigation_adjudications FOR EACH ROW EXECUTE FUNCTION alpha_hunter_phase2_qa.reject_evidence_mutation();
REVOKE ALL ON SCHEMA alpha_hunter_phase2_qa FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA alpha_hunter_phase2_qa FROM PUBLIC;
COMMIT;
