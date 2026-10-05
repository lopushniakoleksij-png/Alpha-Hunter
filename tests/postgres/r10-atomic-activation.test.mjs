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
   baseline_run_id text not null,
   started_at_utc timestamptz not null,
   baseline_config_sha256 text not null,
   baseline_git_commit text not null,
   baseline_previous_snapshot_source text not null,
   baseline_catalyst_version text not null,
   baseline_symbol_rows integer not null,
   baseline_strategy_rows integer not null,
   baseline_microstructure_rows integer not null,
   baseline_closed_candle_rows integer not null,
   activation_checks jsonb not null,
   activated_at_utc timestamptz not null default clock_timestamp(),
   scientific_role text not null,
   shadow_only boolean not null default true,
   trade_permission boolean not null default false,
   production_promotion_permitted boolean not null default false,
   order_path text not null default 'NONE',
   baseline_scientific_fingerprint_sha256 text
  );
  create table public.alpha_hunter_profitability_cadence_contract_v01(
   spec_id text primary key,
   baseline_not_before_utc timestamptz not null,
   expected_frequency_minutes integer not null,
   minimum_interval_minutes integer not null,
   maximum_interval_minutes integer not null,
   expected_schedule text not null,
   no_manual_scans_after_baseline boolean not null,
   scientific_role text not null,
   frozen boolean not null,
   trade_permission boolean not null,
   production_promotion_permitted boolean not null,
   order_path text not null
  );
  create table public.alpha_hunter_symbol_snapshots(
   run_id text not null,
   symbol text not null,
   error text,
   payload jsonb not null,
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

test('R10 owner activation creates execution cadence and profitability atomically',async()=>{
 const db=await setup();
 try{
  const fp='f'.repeat(64);
  const commit='c'.repeat(40);
  const spec='SEALED-R10-ATOMIC';

  await db.exec(`
   insert into alpha_hunter_profitability_test_specs_v01(spec_id)
   values('R9-FIXTURE');

   with t as (
    select clock_timestamp()-interval '2 days' as activated
   )
   insert into alpha_hunter_paper_execution_activation_v09(
    activation_id,spec_id,protocol_version,activated_at_utc,
    runtime_verified_at_utc,admission_cutoff_at_utc,release_git_commit,
    scientific_fingerprint_sha256,evidence
   )
   select
    'PAPER_EXECUTION_R9','R9-FIXTURE','paper-horizon-24h-v0.1',
    activated,activated-interval '1 second',activated+interval '30 days',
    repeat('9',40),repeat('8',64),'{}'
   from t;

   insert into alpha_hunter_paper_admission_halts_v09(
    activation_id,halted_at_utc,reason
   ) values(
    'PAPER_EXECUTION_R9',
    clock_timestamp()-interval '1 day',
    'controlled closure'
   );
  `);

  await db.query(`
   insert into alpha_hunter_profitability_test_specs_v01(
    spec_id,protocol_version,frozen_git_commit,required_strategy_count,
    required_minimum_rr,evaluation_horizon_hours,minimum_test_days,
    minimum_completed_paper_trades,confidence_z,require_validated_cost_model,
    preregistered_at_utc,scientific_role,shadow_only,trade_permission,
    production_promotion_permitted,order_path,required_run_source,
    frozen_scientific_fingerprint_sha256
   ) values(
    $1,'paper-horizon-24h-v0.1',$2,10,5,24,30,100,1.96,true,
    clock_timestamp()-interval '3 minutes',
    'SUCCESSOR_EXECUTED_PAPER_24H_R10',
    true,false,false,'NONE','RENDER_CRON',$3
   )
  `,[spec,commit,fp]);

  await db.query(`
   insert into alpha_hunter_r10_preregistrations_v01(
    registration_id,spec_id,preregistered_at_utc,
    frozen_git_commit,frozen_scientific_fingerprint_sha256,
    protocol_version,evidence
   )
   select
    'PAPER_EXECUTION_R10',spec_id,preregistered_at_utc,
    frozen_git_commit,frozen_scientific_fingerprint_sha256,
    protocol_version,'{}'::jsonb
   from alpha_hunter_profitability_test_specs_v01
   where spec_id=$1
  `,[spec]);

  await db.query(`
   insert into alpha_hunter_snapshots(
    run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload
   )
   select
    'r10-baseline',
    s.preregistered_at_utc+interval '1 minute',
    '0.7.1','USDT-FUTURES',1,0,
    jsonb_build_object(
     'validation_identity',jsonb_build_object(
      'git_commit',$2::text,
      'run_source','RENDER_CRON',
      'runtime_role','RENDER_CRON',
      'config_sha256',repeat('1',64),
      'scientific_fingerprint_sha256',$3::text
     ),
     'previous_snapshot_context',jsonb_build_object(
      'source','SUPABASE','run_id','prior-canonical'
     ),
     'catalyst_summary',jsonb_build_object('version','0.2'),
     'multi_strategy_summary',jsonb_build_object(
      'configured_strategy_count',10,
      'total_evaluations',10
     )
    )
   from alpha_hunter_profitability_test_specs_v01 s
   where s.spec_id=$1
  `,[spec,commit,fp]);

  await db.exec(`
   insert into alpha_hunter_symbol_snapshots(run_id,symbol,error,payload)
   values(
    'r10-baseline','TESTUSDT',null,
    jsonb_build_object(
     'multi_strategy_engine','{}'::jsonb,
     'microstructure','{}'::jsonb,
     'timeframes',jsonb_build_object(
      '1H',jsonb_build_object(
       'last_closed_candle','{}'::jsonb
      )
     )
    )
   );
  `);

  await db.query(`
   insert into alpha_hunter_r10_runtime_verifications_v01(
    verification_id,registration_id,spec_id,run_id,
    verified_at_utc,scan_collected_at_utc,
    git_commit,scientific_fingerprint_sha256,
    run_source,runtime_role,previous_snapshot_source,previous_snapshot_run_id,
    configured_strategy_count,total_strategy_evaluations,
    protected_open_positions,unprotected_open_positions,
    r9_admission_open_rows,orders_after_r9_halt,
    r9_cohort_rows,r9_integrity_failed_orders,
    trade_permission_any,exchange_authority_any,order_path_all_none,
    r10_spec_rows,r10_activation_rows_before,evidence
   )
   select
    'verify-r10','PAPER_EXECUTION_R10',$1,'r10-baseline',
    p.collected_at_utc+interval '30 seconds',
    p.collected_at_utc,
    $2,$3,'RENDER_CRON','RENDER_CRON','SUPABASE','prior-canonical',
    10,10,0,0,0,0,0,0,false,false,true,1,0,'{}'
   from alpha_hunter_snapshots p
   where p.run_id='r10-baseline'
  `,[spec,commit,fp]);

  const before=(await db.query(`
   select
    (select count(*)::int from alpha_hunter_paper_execution_activation_v10) exec_n,
    (select count(*)::int from alpha_hunter_profitability_cadence_contract_v01) cadence_n,
    (select count(*)::int from alpha_hunter_profitability_test_activations_v01) profit_n
  `)).rows[0];
  assert.deepEqual(before,{exec_n:0,cadence_n:0,profit_n:0});

  const result=(await db.query(`
   select private.alpha_hunter_activate_r10_executed_paper_v01(
    'PAPER_EXECUTION_R10','verify-r10'
   ) as result
  `)).rows[0].result;
  assert.equal(result.status,'ACTIVATED');

  const state=(await db.query(`
   select
    e.activated_at_utc,
    e.admission_cutoff_at_utc,
    p.started_at_utc,
    p.baseline_run_id,
    p.baseline_scientific_fingerprint_sha256,
    c.baseline_not_before_utc,
    c.expected_frequency_minutes,
    c.minimum_interval_minutes,
    c.maximum_interval_minutes,
    c.expected_schedule,
    (e.admission_cutoff_at_utc-e.activated_at_utc=interval '30 days') exact_cutoff
   from alpha_hunter_paper_execution_activation_v10 e
   join alpha_hunter_profitability_test_activations_v01 p using(spec_id)
   join alpha_hunter_profitability_cadence_contract_v01 c using(spec_id)
  `)).rows[0];

  assert.equal(state.activated_at_utc.toISOString(),state.started_at_utc.toISOString());
  assert.equal(state.activated_at_utc.toISOString(),state.baseline_not_before_utc.toISOString());
  assert.equal(state.baseline_run_id,'r10-baseline');
  assert.equal(state.baseline_scientific_fingerprint_sha256,fp);
  assert.equal(state.expected_frequency_minutes,20);
  assert.equal(state.minimum_interval_minutes,15);
  assert.equal(state.maximum_interval_minutes,35);
  assert.equal(state.expected_schedule,'RENDER_CRON_ALIGNED_00_20_40');
  assert.equal(state.exact_cutoff,true);

  assert.equal(
   (await db.query('select count(*)::int n from alpha_hunter_paper_admission_open_v10')).rows[0].n,
   1
  );

  await assert.rejects(
   db.query(`
    select private.alpha_hunter_activate_r10_executed_paper_v01(
     'PAPER_EXECUTION_R10','verify-r10'
    )
   `),
   /already exists or is partial/
  );
 }finally{await db.close();}
});
