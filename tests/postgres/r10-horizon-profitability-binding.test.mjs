import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const read=p=>readFileSync(new URL(p,import.meta.url),'utf8');

async function setup(){
 const db=new PGlite();
 await db.exec(read('horizon-schema.sql'));
 await db.exec('alter table alpha_hunter_paper_orders_v02 add primary key(order_id)');
 await db.exec(`
  create table public.alpha_hunter_profitability_test_activations_v01(
   spec_id text primary key,
   baseline_run_id text,
   started_at_utc timestamptz,
   baseline_config_sha256 text,
   baseline_git_commit text,
   baseline_previous_snapshot_source text,
   baseline_catalyst_version text,
   baseline_symbol_rows integer,
   baseline_strategy_rows integer,
   baseline_microstructure_rows integer,
   baseline_closed_candle_rows integer,
   activation_checks jsonb,
   activated_at_utc timestamptz default clock_timestamp(),
   scientific_role text,
   shadow_only boolean default true,
   trade_permission boolean default false,
   production_promotion_permitted boolean default false,
   order_path text default 'NONE',
   baseline_scientific_fingerprint_sha256 text
  );
  create table public.alpha_hunter_profitability_cadence_contract_v01(
   spec_id text primary key,
   baseline_not_before_utc timestamptz,
   expected_frequency_minutes integer,
   minimum_interval_minutes integer,
   maximum_interval_minutes integer,
   expected_schedule text,
   no_manual_scans_after_baseline boolean,
   scientific_role text,
   frozen boolean,
   trade_permission boolean,
   production_promotion_permitted boolean,
   order_path text
  );
  create table public.alpha_hunter_symbol_snapshots(
   run_id text not null,
   symbol text not null,
   error text,
   payload jsonb not null default '{}'::jsonb,
   primary key(run_id,symbol)
  );
 `);
 await db.exec(read('../../ops/sql/paper_horizon_successor_v09.sql'));
 await db.exec(read('../../ops/sql/r9_management_bridge_v01.sql'));
 await db.exec(read('../../ops/sql/r10_cohort_boundary_v01.sql'));
 await db.exec(read('../../ops/sql/r10_preregistration_activation_v01.sql'));
 await db.exec(read('../../ops/sql/r10_horizon_profitability_binding_v01.sql'));
 return db;
}

async function seedActivations(db){
 const fp9='a'.repeat(64);
 const fp10='d'.repeat(64);
 await db.exec(`
  insert into alpha_hunter_profitability_test_specs_v01(
   spec_id,minimum_test_days,minimum_completed_paper_trades,
   confidence_z,require_validated_cost_model
  ) values
   ('R9',30,100,1.96,true),
   ('R10',30,100,1.96,true);

  insert into alpha_hunter_paper_execution_activation_v09(
   activation_id,spec_id,protocol_version,activated_at_utc,
   runtime_verified_at_utc,admission_cutoff_at_utc,release_git_commit,
   scientific_fingerprint_sha256,evidence
  ) values(
   'PAPER_EXECUTION_R9','R9','paper-horizon-24h-v0.1',
   '2026-10-01T00:00:01Z','2026-10-01T00:00:00Z',
   '2026-10-31T00:00:01Z',repeat('b',40),repeat('a',64),'{}'
  );

  insert into alpha_hunter_paper_admission_halts_v09(
   activation_id,halted_at_utc,reason
  ) values(
   'PAPER_EXECUTION_R9','2026-10-04T20:02:43Z','controlled closure'
  );

  insert into alpha_hunter_paper_execution_activation_v10(
   activation_id,spec_id,protocol_version,activated_at_utc,
   runtime_verified_at_utc,admission_cutoff_at_utc,release_git_commit,
   scientific_fingerprint_sha256,evidence
  ) values(
   'PAPER_EXECUTION_R10','R10','paper-horizon-24h-v0.1',
   '2026-10-05T08:00:01Z','2026-10-05T08:00:00Z',
   '2026-11-04T08:00:01Z',repeat('c',40),repeat('d',64),'{}'
  );
 `);
 return {fp9,fp10};
}

test('legacy R9 and R10 horizon identities are mutually exclusive',async()=>{
 const db=await setup();
 try{
  const {fp9,fp10}=await seedActivations(db);
  await db.exec(`
   insert into alpha_hunter_paper_orders_v02(
    order_id,decision_id,submitted_at_utc,symbol,direction
   ) values
    ('legacy','d-legacy','2026-09-30T00:00:00Z','LEGACYUSDT','LONG'),
    ('r9','d-r9','2026-10-02T00:00:00Z','R9USDT','LONG'),
    ('r9-delayed','d-r9-delayed','2026-10-03T00:00:00Z','DELAYUSDT','LONG'),
    ('post-halt-unstamped','d-post','2026-10-05T07:30:00Z','POSTUSDT','LONG');

   insert into alpha_hunter_paper_orders_v02(
    order_id,decision_id,submitted_at_utc,symbol,direction,
    successor_activation_id,successor_spec_id,
    successor_scientific_fingerprint_sha256,successor_source_run_id
   ) values(
    'r10','d-r10','2026-10-05T08:20:00Z','R10USDT','SHORT',
    'PAPER_EXECUTION_R10','R10',repeat('d',64),'r10-source'
   );

   insert into alpha_hunter_paper_protection_open_v04(
    entry_order_id,decision_id,symbol,direction,entry_completed_at_utc
   ) values
    ('legacy','d-legacy','LEGACYUSDT','LONG','2026-09-30T00:01:00Z'),
    ('r9','d-r9','R9USDT','LONG','2026-10-02T00:01:00Z'),
    ('r9-delayed','d-r9-delayed','DELAYUSDT','LONG','2026-10-05T08:30:00Z'),
    ('post-halt-unstamped','d-post','POSTUSDT','LONG','2026-10-05T07:31:00Z'),
    ('r10','d-r10','R10USDT','SHORT','2026-10-05T08:21:00Z');
  `);

  await db.query(`
   insert into alpha_hunter_r9_management_approvals_v01(
    entry_order_id,activation_id,scientific_fingerprint_sha256,
    release_git_commit,reason
   ) values(
    'r9','PAPER_EXECUTION_R9',$1,repeat('e',40),'management only'
   )
  `,['c'.repeat(64)]);

  const rows=(await db.query(`
   select entry_order_id,horizon_protocol,
          horizon_scientific_fingerprint_sha256,
          horizon_management_fingerprints
   from alpha_hunter_paper_protection_horizon_open_v09
   order by entry_order_id
  `)).rows;
  const byId=Object.fromEntries(rows.map(r=>[r.entry_order_id,r]));

  assert.equal(byId.legacy.horizon_protocol,null);
  assert.equal(byId.legacy.horizon_scientific_fingerprint_sha256,null);

  assert.equal(byId.r9.horizon_protocol,'paper-horizon-24h-v0.1');
  assert.equal(byId.r9.horizon_scientific_fingerprint_sha256,fp9);
  assert.deepEqual(byId.r9.horizon_management_fingerprints,['c'.repeat(64)]);

  assert.equal(byId['r9-delayed'].horizon_scientific_fingerprint_sha256,fp9);
  assert.deepEqual(byId['r9-delayed'].horizon_management_fingerprints,[]);

  assert.equal(byId['post-halt-unstamped'].horizon_protocol,null);
  assert.equal(byId['post-halt-unstamped'].horizon_scientific_fingerprint_sha256,null);

  assert.equal(byId.r10.horizon_protocol,'paper-horizon-24h-v0.1');
  assert.equal(byId.r10.horizon_scientific_fingerprint_sha256,fp10);
  assert.deepEqual(byId.r10.horizon_management_fingerprints,[]);
  assert.notEqual(byId.r10.horizon_scientific_fingerprint_sha256,fp9);
 }finally{await db.close();}
});

test('R10 quality is explicit and R10 trades never enter R9 quality',async()=>{
 const db=await setup();
 try{
  const {fp10}=await seedActivations(db);
  const goodEvidence=JSON.stringify({
   paper_authority_source_gate:{
    passed:true,
    observed_run_source:'RENDER_CRON',
    observed_runtime_role:'RENDER_CRON'
   },
   validation_identity:{scientific_fingerprint_sha256:fp10}
  });
  const badEvidence=JSON.stringify({
   paper_authority_source_gate:{
    passed:true,
    observed_run_source:'RENDER_CRON',
    observed_runtime_role:'RENDER_CRON'
   },
   validation_identity:{scientific_fingerprint_sha256:'e'.repeat(64)}
  });

  await db.query(`
   insert into alpha_hunter_paper_decisions_v01(
    decision_id,run_id,observed_at_utc,symbol,strategy_id,strategy_name,
    direction,evidence,paper_only,paper_authority,
    exchange_authority,trade_permission,order_path
   ) values
    ('d-good','run-good','2026-10-05T08:20:00Z','GOODUSDT','S2','test',
     'LONG',$1::jsonb,true,true,false,false,'NONE'),
    ('d-bad','run-bad','2026-10-05T08:22:00Z','BADUSDT','S2','test',
     'LONG',$2::jsonb,true,true,false,false,'NONE'),
    ('d-r9-quality','run-r9','2026-10-02T08:00:00Z','R9QUSDT','S2','test',
     'LONG',jsonb_build_object(
       'paper_authority_source_gate',jsonb_build_object(
        'passed',true,'observed_run_source','RENDER_CRON',
        'observed_runtime_role','RENDER_CRON'
       ),
       'validation_identity',jsonb_build_object(
        'scientific_fingerprint_sha256',repeat('a',64)
       )
     ),true,true,false,false,'NONE');
  `,[goodEvidence,badEvidence]);

  await db.exec(`
   insert into alpha_hunter_paper_orders_v02(
    order_id,decision_id,submitted_at_utc,symbol,direction,quantity,
    successor_activation_id,successor_spec_id,
    successor_scientific_fingerprint_sha256,successor_source_run_id
   ) values
    ('good','d-good','2026-10-05T08:20:00Z','GOODUSDT','LONG',1,
     'PAPER_EXECUTION_R10','R10',repeat('d',64),'run-good'),
    ('bad','d-bad','2026-10-05T08:22:00Z','BADUSDT','LONG',1,
     'PAPER_EXECUTION_R10','R10',repeat('d',64),'run-bad');

   insert into alpha_hunter_paper_orders_v02(
    order_id,decision_id,submitted_at_utc,symbol,direction,quantity
   ) values(
    'r9-quality','d-r9-quality','2026-10-02T08:00:00Z','R9QUSDT','LONG',1
   );

   insert into alpha_hunter_paper_fills_v02(
    fill_id,order_id,decision_id,fill_sequence,filled_at_utc,quantity
   ) values
    ('fg','good','d-good',1,'2026-10-05T08:21:00Z',1),
    ('fb','bad','d-bad',1,'2026-10-05T08:23:00Z',1),
    ('fr9','r9-quality','d-r9-quality',1,'2026-10-02T08:01:00Z',1);

   insert into alpha_hunter_paper_protective_orders_v03(
    protective_order_id,entry_order_id,decision_id,created_at_utc
   ) values
    ('pg','good','d-good','2026-10-05T08:21:00Z'),
    ('pb','bad','d-bad','2026-10-05T08:23:00Z'),
    ('pr9','r9-quality','d-r9-quality','2026-10-02T08:01:00Z');

   insert into alpha_hunter_paper_exit_attempts_v04(
    attempt_id,entry_order_id,decision_id,source_run_id,observed_at_utc,
    symbol,direction,outcome,blockers,evidence,
    paper_only,exchange_authority,trade_permission,order_path
   ) values
    ('ag','good','d-good','exit-good','2026-10-05T08:30:00Z',
     'GOODUSDT','LONG','NO_TRIGGER','[]','{}',true,false,false,'NONE'),
    ('ab','bad','d-bad','exit-bad','2026-10-05T08:31:00Z',
     'BADUSDT','LONG','NO_TRIGGER','[]','{}',true,false,false,'NONE'),
    ('ar9','r9-quality','d-r9-quality','exit-r9','2026-10-02T08:10:00Z',
     'R9QUSDT','LONG','NO_TRIGGER','[]','{}',true,false,false,'NONE');

   insert into alpha_hunter_paper_completed_trades_valid_v05(
    exit_fill_id,entry_order_id,decision_id,entry_decision_run_id,
    exit_source_run_id,symbol,direction,exit_reason,closed_at_utc,
    quantity,entry_average_fill_price,exit_price,paper_net_pnl_ex_funding,
    planned_risk_usdt,net_r_ex_funding,paper_only,
    exchange_authority,trade_permission,order_path
   ) values
    ('xg','good','d-good','run-good','exit-good','GOODUSDT','LONG',
     'TAKE_PROFIT','2026-10-05T08:31:00Z',1,10,11,1,1,1,
     true,false,false,'NONE'),
    ('xb','bad','d-bad','run-bad','exit-bad','BADUSDT','LONG',
     'TAKE_PROFIT','2026-10-05T08:32:00Z',1,10,11,1,1,1,
     true,false,false,'NONE'),
    ('xr9','r9-quality','d-r9-quality','run-r9','exit-r9','R9QUSDT','LONG',
     'TAKE_PROFIT','2026-10-02T08:11:00Z',1,10,11,1,1,1,
     true,false,false,'NONE');
  `);

  const valid=(await db.query(`
   select entry_order_id
   from alpha_hunter_paper_completed_trades_valid_v10
   order by entry_order_id
  `)).rows.map(r=>r.entry_order_id);
  assert.deepEqual(valid,['good']);

  const quarantine=(await db.query(`
   select entry_order_id,quarantine_reasons
   from alpha_hunter_paper_completed_trades_quarantine_v10
   order by entry_order_id
  `)).rows;
  assert.equal(quarantine.length,1);
  assert.equal(quarantine[0].entry_order_id,'bad');
  assert.ok(quarantine[0].quarantine_reasons.includes('SCIENTIFIC_FINGERPRINT_MISMATCH'));

  const r9Quality=(await db.query(`
   select entry_order_id
   from alpha_hunter_paper_completed_trade_quality_v09
   order by entry_order_id
  `)).rows.map(r=>r.entry_order_id);
  assert.deepEqual(r9Quality,['r9-quality']);

  const r10Quality=(await db.query(`
   select entry_order_id
   from alpha_hunter_paper_completed_trade_quality_v10
   order by entry_order_id
  `)).rows.map(r=>r.entry_order_id);
  assert.deepEqual(r10Quality,['bad','good']);
 }finally{await db.close();}
});
