-- ISOLATED POSTGRESQL 16/17 SCIENTIFIC FIXTURE ONLY.
-- Must run ONLY in an ephemeral CI postgres container (never Supabase).
-- No production tables, no migrations, no credentials, no order authority.
BEGIN;
CREATE SCHEMA successor_lab;
REVOKE ALL ON SCHEMA successor_lab FROM PUBLIC;
CREATE ROLE successor_lab_reader NOLOGIN;
GRANT USAGE ON SCHEMA successor_lab TO successor_lab_reader;

CREATE TABLE successor_lab.positions (
  position_id text PRIMARY KEY,
  side text NOT NULL CHECK (side IN ('LONG','SHORT')),
  entry_qty numeric(30,12) NOT NULL CHECK(entry_qty>0),
  entry_price numeric(30,12) NOT NULL CHECK(entry_price>0),
  stop_price numeric(30,12) NOT NULL CHECK(stop_price>0),
  target_price numeric(30,12) NOT NULL CHECK(target_price>0),
  entry_fee numeric(30,12) NOT NULL CHECK(entry_fee>=0),
  remaining_qty numeric(30,12) NOT NULL CHECK(remaining_qty>=0),
  realized_qty numeric(30,12) NOT NULL DEFAULT 0 CHECK(realized_qty>=0),
  allocated_entry_fee numeric(30,12) NOT NULL DEFAULT 0 CHECK(allocated_entry_fee>=0),
  realized_gross numeric(30,12) NOT NULL DEFAULT 0,
  realized_exit_fee numeric(30,12) NOT NULL DEFAULT 0 CHECK(realized_exit_fee>=0),
  revision integer NOT NULL DEFAULT 0 CHECK(revision>=0),
  last_event_at timestamptz NOT NULL,
  state text NOT NULL DEFAULT 'PROTECTED' CHECK(state IN ('PROTECTED','CLOSED','HALTED_UNRESOLVED')),
  CHECK (entry_qty = remaining_qty + realized_qty),
  CHECK (allocated_entry_fee <= entry_fee),
  CHECK ((side='LONG' AND stop_price<entry_price AND entry_price<target_price)
      OR (side='SHORT' AND target_price<entry_price AND entry_price<stop_price)),
  CHECK ((state='CLOSED' AND remaining_qty=0) OR state<>'CLOSED')
);

CREATE TABLE successor_lab.guards (
  position_id text NOT NULL REFERENCES successor_lab.positions(position_id),
  revision integer NOT NULL CHECK(revision>=0),
  covered_qty numeric(30,12) NOT NULL CHECK(covered_qty>=0),
  stop_id text NOT NULL CHECK(length(stop_id)>0),
  target_id text NOT NULL CHECK(length(target_id)>0),
  oco_group text NOT NULL CHECK(length(oco_group)>0),
  stop_ack text NOT NULL CHECK(length(stop_ack)>0),
  target_ack text NOT NULL CHECK(length(target_ack)>0),
  prior_stop_cancel_ack text,
  prior_target_cancel_ack text,
  acknowledged_at timestamptz NOT NULL,
  guard_status text NOT NULL CHECK(guard_status IN ('ARMED','CANCELLED')),
  PRIMARY KEY(position_id, revision),
  UNIQUE(position_id,stop_ack),
  UNIQUE(position_id,target_ack),
  CHECK (stop_id <> target_id AND stop_ack <> target_ack),
  CHECK ((covered_qty>0 AND guard_status='ARMED')
       OR (covered_qty=0 AND guard_status='CANCELLED'))
);

CREATE TABLE successor_lab.synthetic_exit_events (
  position_id text NOT NULL REFERENCES successor_lab.positions(position_id),
  event_id text NOT NULL CHECK(length(event_id)>0),
  revision integer NOT NULL CHECK(revision>0),
  receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[0-9a-f]{64}$'),
  quote_id text NOT NULL CHECK(length(quote_id)>0),
  event_time timestamptz NOT NULL,
  trigger_type text NOT NULL CHECK(trigger_type IN('STOP_LOSS','TAKE_PROFIT')),
  active_trigger_id text NOT NULL,
  quantity numeric(30,12) NOT NULL CHECK(quantity>0),
  price numeric(30,12) NOT NULL CHECK(price>0),
  fee numeric(30,12) NOT NULL CHECK(fee>=0),
  allocated_entry_fee numeric(30,12) NOT NULL CHECK(allocated_entry_fee>=0),
  gross_pnl numeric(30,12) NOT NULL,
  -- No provider-reported actual fills. This table stores isolated test receipts.
  evidence_kind text NOT NULL DEFAULT 'ISOLATED_SYNTHETIC_RECEIPT'
    CHECK(evidence_kind='ISOLATED_SYNTHETIC_RECEIPT'),
  PRIMARY KEY(position_id,event_id),
  UNIQUE(position_id,revision),
  UNIQUE(position_id,receipt_sha256),
  UNIQUE(position_id,quote_id)
);

CREATE TABLE successor_lab.custody_ledger (
  position_id text NOT NULL REFERENCES successor_lab.positions(position_id),
  revision integer NOT NULL CHECK(revision>0),
  event_id text NOT NULL,
  receipt_sha256 text NOT NULL,
  guard_revision integer NOT NULL,
  remaining_before numeric(30,12) NOT NULL,
  remaining_after numeric(30,12) NOT NULL,
  recorded_at timestamptz NOT NULL,
  synthetic_only boolean NOT NULL DEFAULT true CHECK(synthetic_only=true),
  PRIMARY KEY(position_id,revision),
  UNIQUE(position_id,event_id),
  FOREIGN KEY(position_id,event_id)
    REFERENCES successor_lab.synthetic_exit_events(position_id,event_id),
  FOREIGN KEY(position_id,guard_revision)
    REFERENCES successor_lab.guards(position_id,revision),
  CHECK(remaining_before>remaining_after AND remaining_after>=0)
);

-- A read-only source-of-truth cross-check for "write may have committed".
-- A response timeout alone must NEVER be taken as successful reconciliation.
CREATE FUNCTION successor_lab.verify_event(p_id text, p_event text, p_receipt text)
RETURNS text LANGUAGE plpgsql STABLE SET search_path=pg_catalog,successor_lab AS $$
DECLARE
  pos successor_lab.positions%ROWTYPE;
  ev successor_lab.synthetic_exit_events%ROWTYPE;
  lg successor_lab.custody_ledger%ROWTYPE;
  gd successor_lab.guards%ROWTYPE;
  latest successor_lab.guards%ROWTYPE;
  n_fill bigint; n_guard bigint; n_ledger bigint;
  qty_total numeric;
  fee_total numeric;
  gross_total numeric;
  entry_fee_total numeric;
BEGIN
  SELECT * INTO pos FROM successor_lab.positions WHERE position_id=p_id;
  IF NOT FOUND THEN RETURN 'NO_PARENT_NEEDS_INDEPENDENT_RECHECK'; END IF;
  SELECT * INTO ev FROM successor_lab.synthetic_exit_events
    WHERE position_id=p_id AND event_id=p_event;
  IF NOT FOUND THEN
    IF EXISTS(SELECT 1 FROM successor_lab.custody_ledger
      WHERE position_id=p_id AND event_id=p_event)
    THEN RETURN 'HALTED_INCONSISTENT_CUSTODY'; END IF;
    RETURN 'NO_COMMIT_VISIBLE_NEEDS_SOURCE_RECHECK';
  END IF;
  IF ev.receipt_sha256 IS DISTINCT FROM p_receipt
    THEN RETURN 'HALTED_CONFLICTING_RECEIPT'; END IF;
  SELECT * INTO lg FROM successor_lab.custody_ledger
    WHERE position_id=p_id AND revision=ev.revision AND event_id=p_event;
  IF NOT FOUND THEN RETURN 'HALTED_MISSING_CUSTODY_LEDGER'; END IF;
  SELECT * INTO gd FROM successor_lab.guards
    WHERE position_id=p_id AND revision=ev.revision;
  IF NOT FOUND THEN RETURN 'HALTED_MISSING_RESIDUAL_PROTECTION'; END IF;
  SELECT * INTO latest FROM successor_lab.guards
    WHERE position_id=p_id AND revision=pos.revision;
  IF NOT FOUND THEN RETURN 'HALTED_NO_CURRENT_GUARD'; END IF;

  IF pos.state='HALTED_UNRESOLVED' OR ev.revision>pos.revision
     OR lg.guard_revision<>ev.revision OR lg.receipt_sha256<>ev.receipt_sha256
     OR lg.remaining_before-lg.remaining_after<>ev.quantity
     OR gd.covered_qty<>lg.remaining_after
     OR gd.acknowledged_at<ev.event_time
     OR latest.covered_qty<>pos.remaining_qty
     OR latest.guard_status<>(CASE WHEN pos.remaining_qty=0 THEN 'CANCELLED' ELSE 'ARMED' END)
  THEN RETURN 'HALTED_INCONSISTENT_POSITION_OR_GUARD'; END IF;

  SELECT count(*),coalesce(sum(quantity),0),coalesce(sum(fee),0),
         coalesce(sum(gross_pnl),0),coalesce(sum(allocated_entry_fee),0)
  INTO n_fill,qty_total,fee_total,gross_total,entry_fee_total
  FROM successor_lab.synthetic_exit_events WHERE position_id=p_id;
  SELECT count(*) INTO n_guard FROM successor_lab.guards WHERE position_id=p_id;
  SELECT count(*) INTO n_ledger FROM successor_lab.custody_ledger WHERE position_id=p_id;
  IF n_fill<>pos.revision OR n_ledger<>pos.revision
    OR n_guard<>(pos.revision+1) OR qty_total<>pos.realized_qty
    OR fee_total<>pos.realized_exit_fee OR gross_total<>pos.realized_gross
    OR entry_fee_total<>pos.allocated_entry_fee
  THEN RETURN 'HALTED_AGGREGATE_RECONCILIATION_FAILURE'; END IF;

  IF EXISTS (
    SELECT 1 FROM successor_lab.synthetic_exit_events e
    LEFT JOIN successor_lab.custody_ledger l
      ON e.position_id=l.position_id AND e.revision=l.revision
    LEFT JOIN successor_lab.guards g
      ON e.position_id=g.position_id AND e.revision=g.revision
    WHERE e.position_id=p_id AND
      (l.event_id IS NULL OR l.event_id<>e.event_id
       OR l.receipt_sha256<>e.receipt_sha256
       OR l.remaining_before-l.remaining_after<>e.quantity
       OR g.covered_qty<>l.remaining_after
       OR g.acknowledged_at<e.event_time)
  ) THEN RETURN 'HALTED_BROKEN_PARENT_CHILD_CHAIN'; END IF;
  RETURN 'VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL';
END $$;

-- One call runs as one database transaction. Unlike an external sequence of
-- HTTP calls, either event/guard/ledger/position all commit, or none commit.
CREATE FUNCTION successor_lab.apply_synthetic_exit(p_id text, payload jsonb)
RETURNS text LANGUAGE plpgsql VOLATILE SET search_path=pg_catalog,successor_lab AS $$
DECLARE
 p successor_lab.positions%ROWTYPE;
 prev successor_lab.guards%ROWTYPE;
 oldev successor_lab.synthetic_exit_events%ROWTYPE;
 v_event_id text := payload->>'event_id';
 receipt text := payload->>'receipt_sha256';
 quote text := payload->>'quote_id';
 evt_at timestamptz;
 q numeric; px numeric; bid numeric; ask numeric; displayed numeric;
 bps numeric; slip numeric; cross_px numeric; fee numeric; gross numeric;
 alloc numeric; rem_qty numeric; trg text; gid text;
 ng jsonb := payload->'next_guard';
 gd_at timestamptz; stop_id text; target_id text; oco text;
 stop_ack text; target_ack text; cancel_stop text; cancel_target text;
 status text;
BEGIN
 SELECT * INTO p FROM successor_lab.positions WHERE position_id=p_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'POSITION_NOT_FOUND'; END IF;
 IF coalesce(payload->>'evidence_kind','') <> 'ISOLATED_SYNTHETIC_RECEIPT'
   THEN RAISE EXCEPTION 'ONLY_SYNTHETIC_TEST_RECEIPTS_ALLOWED'; END IF;
 IF v_event_id IS NULL OR length(v_event_id)=0 OR receipt !~ '^[0-9a-f]{64}$'
   OR quote IS NULL OR quote='' THEN RAISE EXCEPTION 'MISSING_RECEIPT_IDENTITY'; END IF;
 SELECT * INTO oldev FROM successor_lab.synthetic_exit_events
   WHERE position_id=p_id AND event_id=v_event_id;
 IF FOUND THEN
   IF oldev.receipt_sha256<>receipt THEN RAISE EXCEPTION 'CONFLICTING_EVENT_ID'; END IF;
   status := successor_lab.verify_event(p_id,v_event_id,receipt);
   IF status <> 'VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL'
     THEN RAISE EXCEPTION 'REPLAY_NOT_PROVEN: %',status; END IF;
   RETURN 'DUPLICATE_VERIFIED_NOOP';
 END IF;
 IF p.state<>'PROTECTED' THEN RAISE EXCEPTION 'POSITION_NOT_PROTECTED'; END IF;
 IF (payload->>'expected_revision')::int <> p.revision
   THEN RAISE EXCEPTION 'STALE_POSITION_REVISION'; END IF;
 IF EXISTS(SELECT 1 FROM successor_lab.synthetic_exit_events
    WHERE position_id=p_id AND (receipt_sha256=receipt OR quote_id=quote))
   THEN RAISE EXCEPTION 'REUSED_RECEIPT_OR_QUOTE'; END IF;
 SELECT * INTO prev FROM successor_lab.guards
   WHERE position_id=p_id AND revision=p.revision;
 IF NOT FOUND OR prev.covered_qty<>p.remaining_qty OR prev.guard_status<>'ARMED'
   THEN RAISE EXCEPTION 'ORIGINAL_PROTECTION_NOT_CONFIRMED'; END IF;
 IF ng IS NULL OR jsonb_typeof(ng)<>'object' THEN RAISE EXCEPTION 'RESIDUAL_GUARD_MISSING'; END IF;

 evt_at := (payload->>'event_time')::timestamptz;
 q := (payload->>'quantity')::numeric;
 px := (payload->>'exit_price')::numeric;
 bid := (payload->>'best_bid')::numeric;
 ask := (payload->>'best_ask')::numeric;
 displayed := (payload->>'visible_exit_size')::numeric;
 bps := (payload->>'fee_bps')::numeric;
 trg := payload->>'trigger_type';
 gid := payload->>'trigger_guard_id';
 IF evt_at<=p.last_event_at OR q IS NULL OR q<=0 OR q>p.remaining_qty
    OR px IS NULL OR px<=0 OR bid IS NULL OR bid<=0
    OR ask IS NULL OR ask<bid OR displayed IS NULL OR displayed<q
    OR bps IS NULL OR bps<0 OR bps>20
 THEN RAISE EXCEPTION 'INVALID_FILL_OR_LIQUIDITY_OR_FEE'; END IF;
 IF trg NOT IN ('STOP_LOSS','TAKE_PROFIT')
   OR gid<>(CASE WHEN trg='STOP_LOSS' THEN prev.stop_id ELSE prev.target_id END)
 THEN RAISE EXCEPTION 'TRIGGER_NOT_LINKED_TO_PROTECTION'; END IF;
 IF NOT (
   (trg='STOP_LOSS' AND
       (CASE WHEN p.side='LONG' THEN bid<=p.stop_price ELSE ask>=p.stop_price END))
   OR (trg='TAKE_PROFIT' AND
       (CASE WHEN p.side='LONG' THEN bid>=p.target_price ELSE ask<=p.target_price END))
 ) THEN RAISE EXCEPTION 'TRIGGER_NOT_SEEN_ON_EXIT_SIDE'; END IF;
 cross_px := CASE WHEN p.side='LONG' THEN bid ELSE ask END;
 slip := (CASE WHEN p.side='LONG' THEN cross_px-px ELSE px-cross_px END)
         /cross_px*10000;
 IF slip<0 OR slip>25 THEN RAISE EXCEPTION 'SLIPPAGE_OUTSIDE_SYNTHETIC_BOUND'; END IF;

 rem_qty := p.remaining_qty-q;
 stop_id := ng->>'stop_id'; target_id := ng->>'target_id';
 stop_ack := ng->>'stop_ack'; target_ack := ng->>'target_ack';
 oco := ng->>'oco_group';
 cancel_stop := ng->>'prior_stop_cancel_ack';
 cancel_target := ng->>'prior_target_cancel_ack';
 gd_at := (ng->>'acknowledged_at')::timestamptz;
 IF coalesce(stop_id,'')='' OR coalesce(target_id,'')=''
    OR stop_id=target_id OR coalesce(stop_ack,'')=''
    OR coalesce(target_ack,'')='' OR stop_ack=target_ack
    OR coalesce(cancel_stop,'')='' OR coalesce(cancel_target,'')=''
    OR cancel_stop=cancel_target OR oco IS DISTINCT FROM prev.oco_group
    OR gd_at<evt_at OR stop_ack=prev.stop_ack OR target_ack=prev.target_ack
    OR (ng->>'revision')::int<>p.revision+1
    OR (ng->>'covered_qty')::numeric<>rem_qty
    OR (ng->>'guard_status')<>(CASE WHEN rem_qty=0 THEN 'CANCELLED' ELSE 'ARMED' END)
 THEN RAISE EXCEPTION 'RESIDUAL_OCO_ACKS_INVALID'; END IF;
 IF stop_id=prev.stop_id OR target_id=prev.target_id
 THEN RAISE EXCEPTION 'ORIGINAL_GUARD_LEG_NOT_REPLACED'; END IF;

 fee := round(q*px*bps/10000,12);
 alloc := CASE WHEN rem_qty=0 THEN p.entry_fee-p.allocated_entry_fee
      ELSE round(p.entry_fee*q/p.entry_qty,12) END;
 gross := round(q*(CASE WHEN p.side='LONG' THEN px-p.entry_price
                         ELSE p.entry_price-px END),12);

 INSERT INTO successor_lab.synthetic_exit_events
 (position_id,event_id,revision,receipt_sha256,quote_id,event_time,
  trigger_type,active_trigger_id,quantity,price,fee,allocated_entry_fee,gross_pnl)
 VALUES (p_id,v_event_id,p.revision+1,receipt,quote,evt_at,trg,gid,q,px,fee,alloc,gross);
 IF payload->>'inject_fault'='AFTER_FILL'
 THEN RAISE EXCEPTION 'INJECTED_FAILURE_AFTER_FILL'; END IF;
 INSERT INTO successor_lab.guards
 (position_id,revision,covered_qty,stop_id,target_id,oco_group,stop_ack,target_ack,
 prior_stop_cancel_ack,prior_target_cancel_ack,acknowledged_at,guard_status)
 VALUES(p_id,p.revision+1,rem_qty,stop_id,target_id,oco,stop_ack,target_ack,
        cancel_stop,cancel_target,gd_at,
        CASE WHEN rem_qty=0 THEN 'CANCELLED' ELSE 'ARMED' END);
 IF payload->>'inject_fault'='AFTER_GUARD'
 THEN RAISE EXCEPTION 'INJECTED_FAILURE_AFTER_GUARD'; END IF;
 INSERT INTO successor_lab.custody_ledger
 (position_id,revision,event_id,receipt_sha256,guard_revision,
 remaining_before,remaining_after,recorded_at)
 VALUES(p_id,p.revision+1,v_event_id,receipt,p.revision+1,p.remaining_qty,rem_qty,evt_at);
 IF payload->>'inject_fault'='AFTER_LEDGER'
 THEN RAISE EXCEPTION 'INJECTED_FAILURE_AFTER_LEDGER'; END IF;
 UPDATE successor_lab.positions SET
   remaining_qty=rem_qty,
   realized_qty=realized_qty+q,
   allocated_entry_fee=allocated_entry_fee+alloc,
   realized_gross=realized_gross+gross,
   realized_exit_fee=realized_exit_fee+fee,
   revision=revision+1,
   last_event_at=evt_at,
   state=CASE WHEN rem_qty=0 THEN 'CLOSED' ELSE 'PROTECTED' END
 WHERE position_id=p_id;
 status := successor_lab.verify_event(p_id,v_event_id,receipt);
 IF status<>'VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL'
 THEN RAISE EXCEPTION 'SELF_VERIFICATION_FAILED: %',status; END IF;
 RETURN 'ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL';
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA successor_lab FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA successor_lab FROM PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA successor_lab TO successor_lab_reader;
GRANT EXECUTE ON FUNCTION successor_lab.verify_event(text,text,text)
  TO successor_lab_reader;
COMMIT;
