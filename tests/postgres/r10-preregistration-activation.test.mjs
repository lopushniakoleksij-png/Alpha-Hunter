import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const read=p=>readFileSync(new URL(p,import.meta.url),'utf8');

test('R10 preregistration and activation surfaces install empty and owner-only',async()=>{
 const db=new PGlite();
 try{
  await db.exec(read('horizon-schema.sql'));
  await db.exec(`
   create table public.alpha_hunter_profitability_test_activations_v01(
    spec_id text,started_at_utc timestamptz,
    baseline_scientific_fingerprint_sha256 text
   );
  `);
  await db.exec(read('../../ops/sql/paper_horizon_successor_v09.sql'));
  await db.exec(read('../../ops/sql/r10_cohort_boundary_v01.sql'));
  await db.exec(read('../../ops/sql/r10_preregistration_activation_v01.sql'));

  for (const table of [
   'alpha_hunter_r10_preregistrations_v01',
   'alpha_hunter_r10_runtime_verifications_v01',
   'alpha_hunter_paper_execution_activation_v10',
   'alpha_hunter_paper_admission_open_v10'
  ]) {
   const n=(await db.query(`select count(*)::int n from ${table}`)).rows[0].n;
   assert.equal(n,0,table);
  }

  const perms=(await db.query(`
   select
    has_table_privilege('service_role','alpha_hunter_r10_preregistrations_v01','INSERT') as prereg_insert,
    has_table_privilege('service_role','alpha_hunter_r10_runtime_verifications_v01','INSERT') as verify_insert,
    has_table_privilege('service_role','alpha_hunter_paper_execution_activation_v10','INSERT') as activation_insert,
    has_function_privilege('service_role','private.alpha_hunter_activate_r10_executed_paper_v01(text,text)','EXECUTE') as activation_execute
  `)).rows[0];
  assert.deepEqual(perms,{
   prereg_insert:false,
   verify_insert:false,
   activation_insert:false,
   activation_execute:false
  });

  assert.equal(
   (await db.query('select count(*)::int n from alpha_hunter_r10_activation_readiness_v01')).rows[0].n,
   0
  );
 }finally{
  await db.close();
 }
});

test('R10 owner activation requires post-prereg canonical context and exact freeze',async()=>{
 const db=new PGlite();
 try{
  await db.exec(read('horizon-schema.sql'));
  await db.exec(`
   create table public.alpha_hunter_profitability_test_activations_v01(
    spec_id text,started_at_utc timestamptz,
    baseline_scientific_fingerprint_sha256 text
   );
  `);
  await db.exec(read('../../ops/sql/paper_horizon_successor_v09.sql'));
  await db.exec(read('../../ops/sql/r10_cohort_boundary_v01.sql'));
  await db.exec(read('../../ops/sql/r10_preregistration_activation_v01.sql'));

  const fp='f'.repeat(64);
  const commit='c'.repeat(40);
  const spec='SEALED-R10-TEST';

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
    '2026-10-05T08:10:00Z','SUCCESSOR_EXECUTED_PAPER_24H_R10',
    true,false,false,'NONE','RENDER_CRON',$3
   )
  `,[spec,commit,fp]);

  await db.query(`
   insert into alpha_hunter_r10_preregistrations_v01(
    registration_id,spec_id,preregistered_at_utc,frozen_git_commit,
    frozen_scientific_fingerprint_sha256,protocol_version,evidence
   ) values(
    'PAPER_EXECUTION_R10',$1,'2026-10-05T08:10:00Z',$2,$3,
    'paper-horizon-24h-v0.1','{}'
   )
  `,[spec,commit,fp]);

  await db.query(`
   insert into alpha_hunter_snapshots(
    run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload
   ) values(
    'baseline-none','2026-10-05T08:11:00Z','0.7.1','USDT-FUTURES',50,0,
    jsonb_build_object(
     'validation_identity',jsonb_build_object(
      'git_commit',$1,'run_source','RENDER_CRON','runtime_role','RENDER_CRON',
      'scientific_fingerprint_sha256',$2
     ),
     'previous_snapshot_context',jsonb_build_object('source','NONE','run_id',null),
     'multi_strategy_summary',jsonb_build_object(
      'configured_strategy_count',10,'total_evaluations',500
     )
    )
   )
  `,[commit,fp]);

  await assert.rejects(
   db.query(`
    insert into alpha_hunter_r10_runtime_verifications_v01(
     verification_id,registration_id,spec_id,run_id,verified_at_utc,
     scan_collected_at_utc,git_commit,scientific_fingerprint_sha256,
     run_source,runtime_role,previous_snapshot_source,previous_snapshot_run_id,
     configured_strategy_count,total_strategy_evaluations,
     protected_open_positions,unprotected_open_positions,
     r9_admission_open_rows,orders_after_r9_halt,
     trade_permission_any,exchange_authority_any,order_path_all_none,
     r10_spec_rows,r10_activation_rows_before,evidence
    ) values(
     'bad-none','PAPER_EXECUTION_R10',$1,'baseline-none',
     '2026-10-05T08:12:00Z','2026-10-05T08:11:00Z',$2,$3,
     'RENDER_CRON','RENDER_CRON','NONE','',
     10,500,19,0,0,0,false,false,true,1,0,'{}'
    )
   `,[spec,commit,fp])
  );

  await db.query(`
   insert into alpha_hunter_snapshots(
    run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload
   ) values(
    'baseline-good','2026-10-05T08:20:00Z','0.7.1','USDT-FUTURES',50,0,
    jsonb_build_object(
     'validation_identity',jsonb_build_object(
      'git_commit',$1,'run_source','RENDER_CRON','runtime_role','RENDER_CRON',
      'scientific_fingerprint_sha256',$2
     ),
     'previous_snapshot_context',jsonb_build_object(
      'source','SUPABASE','run_id','prior-run'
     ),
     'multi_strategy_summary',jsonb_build_object(
      'configured_strategy_count',10,'total_evaluations',500
     )
    )
   )
  `,[commit,fp]);

  await db.query(`
   insert into alpha_hunter_r10_runtime_verifications_v01(
    verification_id,registration_id,spec_id,run_id,verified_at_utc,
    scan_collected_at_utc,git_commit,scientific_fingerprint_sha256,
    run_source,runtime_role,previous_snapshot_source,previous_snapshot_run_id,
    configured_strategy_count,total_strategy_evaluations,
    protected_open_positions,unprotected_open_positions,
    r9_admission_open_rows,orders_after_r9_halt,
    trade_permission_any,exchange_authority_any,order_path_all_none,
    r10_spec_rows,r10_activation_rows_before,evidence
   ) values(
    'verify-good','PAPER_EXECUTION_R10',$1,'baseline-good',
    '2026-10-05T08:21:00Z','2026-10-05T08:20:00Z',$2,$3,
    'RENDER_CRON','RENDER_CRON','SUPABASE','prior-run',
    10,500,19,0,0,0,false,false,true,1,0,'{}'
   )
  `,[spec,commit,fp]);

  const ready=(await db.query(`
   select ready_for_owner_activation
   from alpha_hunter_r10_activation_readiness_v01
  `)).rows[0].ready_for_owner_activation;
  assert.equal(ready,true);

  await db.exec(`
   create table if not exists public.alpha_hunter_paper_admission_halts_v09(
    activation_id text primary key,halted_at_utc timestamptz,reason text
   );
   insert into public.alpha_hunter_paper_admission_halts_v09
   values('PAPER_EXECUTION_R9','2026-10-04T20:02:43Z','halt');
  `);

  const activated=(await db.query(`
   select private.alpha_hunter_activate_r10_executed_paper_v01(
    'PAPER_EXECUTION_R10','verify-good'
   ) as result
  `)).rows[0].result;
  assert.equal(activated.status,'ACTIVATED');

  const open=(await db.query(`
   select count(*)::int n from alpha_hunter_paper_admission_open_v10
  `)).rows[0].n;
  assert.equal(open,1);

  const timing=(await db.query(`
   select
    admission_cutoff_at_utc-activated_at_utc = interval '30 days' as exact_cutoff,
    activated_at_utc>runtime_verified_at_utc as verification_precedes_activation
   from alpha_hunter_paper_execution_activation_v10
  `)).rows[0];
  assert.deepEqual(timing,{
   exact_cutoff:true,
   verification_precedes_activation:true
  });
 }finally{
  await db.close();
 }
});
