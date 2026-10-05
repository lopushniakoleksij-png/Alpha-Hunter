import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const read=p=>readFileSync(new URL(p,import.meta.url),'utf8');

test('R10 boundary is inactive, explicit and disjoint from halted R9',async()=>{
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

  assert.equal(
   (await db.query('select count(*)::int n from alpha_hunter_paper_execution_activation_v10')).rows[0].n,
   0
  );
  assert.equal(
   (await db.query('select count(*)::int n from alpha_hunter_paper_admission_open_v10')).rows[0].n,
   0
  );

  const perms=(await db.query(`
   select
    has_table_privilege('service_role','alpha_hunter_paper_execution_activation_v10','INSERT') as can_activate,
    has_table_privilege('service_role','alpha_hunter_paper_execution_activation_v10','SELECT') as can_read
  `)).rows[0];
  assert.deepEqual(perms,{can_activate:false,can_read:true});

  await db.exec(`
   insert into alpha_hunter_profitability_test_specs_v01(spec_id,scientific_role)
   values('R9','SUCCESSOR_EXECUTED_PAPER_24H'),
         ('R10','SUCCESSOR_EXECUTED_PAPER_24H_R10');

   insert into alpha_hunter_paper_execution_activation_v09
   (activation_id,spec_id,protocol_version,activated_at_utc,runtime_verified_at_utc,
    admission_cutoff_at_utc,release_git_commit,scientific_fingerprint_sha256,evidence)
   values('PAPER_EXECUTION_R9','R9','paper-horizon-24h-v0.1',
    '2026-10-01 00:00:01Z','2026-10-01Z','2026-10-31 00:00:01Z',
    repeat('b',40),repeat('a',64),'{}');

   insert into alpha_hunter_paper_admission_halts_v09(activation_id,halted_at_utc,reason)
   values('PAPER_EXECUTION_R9','2026-10-04T20:02:43Z','controlled R9 closure');

   insert into alpha_hunter_paper_decisions_v01
   (decision_id,run_id,observed_at_utc,symbol,direction)
   values
    ('d-r9','run-r9','2026-10-02Z','OLDUSDT','LONG'),
    ('d-late','run-late','2026-10-05Z','LATEUSDT','LONG');

   insert into alpha_hunter_paper_orders_v02
   (order_id,decision_id,submitted_at_utc,symbol,direction)
   values
    ('r9-order','d-r9','2026-10-02Z','OLDUSDT','LONG'),
    ('post-halt-unstamped','d-late','2026-10-05Z','LATEUSDT','LONG');
  `);

  const r9=(await db.query('select order_id from alpha_hunter_paper_cohort_members_v09 order by order_id')).rows;
  assert.deepEqual(r9.map(r=>r.order_id),['r9-order']);

  await db.query(`
   insert into alpha_hunter_profitability_test_activations_v01
   (spec_id,started_at_utc,baseline_scientific_fingerprint_sha256)
   values('R10','2026-10-05T08:00:01Z',$1)
  `,['d'.repeat(64)]);
  assert.equal(
   (await db.query("select count(*)::int n from alpha_hunter_profitability_test_activations_v01 where spec_id='R10'")).rows[0].n,
   0
  );

  await db.exec(`
   insert into alpha_hunter_paper_execution_activation_v10
   (activation_id,spec_id,protocol_version,activated_at_utc,runtime_verified_at_utc,
    admission_cutoff_at_utc,release_git_commit,scientific_fingerprint_sha256,evidence)
   values('PAPER_EXECUTION_R10','R10','paper-horizon-24h-v0.1',
    '2026-10-05T08:00:01Z','2026-10-05T08:00:00Z','2026-11-04T08:00:01Z',
    repeat('c',40),repeat('d',64),'{}');

   insert into alpha_hunter_paper_decisions_v01
   (decision_id,run_id,observed_at_utc,symbol,direction)
   values
    ('d-r10','run-r10','2026-10-05T08:20:00Z','NEWUSDT','SHORT'),
    ('d-wrong','run-wrong','2026-10-05T08:21:00Z','WRONGUSDT','SHORT');

   insert into alpha_hunter_paper_orders_v02
   (order_id,decision_id,submitted_at_utc,symbol,direction,
    successor_activation_id,successor_spec_id,
    successor_scientific_fingerprint_sha256,successor_source_run_id)
   values
    ('r10-order','d-r10','2026-10-05T08:20:00Z','NEWUSDT','SHORT',
     'PAPER_EXECUTION_R10','R10',repeat('d',64),'run-r10'),
    ('wrong-fingerprint','d-wrong','2026-10-05T08:21:00Z','WRONGUSDT','SHORT',
     'PAPER_EXECUTION_R10','R10',repeat('e',64),'run-wrong');
  `);

  const r10=(await db.query('select order_id from alpha_hunter_paper_cohort_membership_v10 order by order_id')).rows;
  assert.deepEqual(r10.map(r=>r.order_id),['r10-order']);

  assert.equal(
   (await db.query("select count(*)::int n from alpha_hunter_paper_cohort_members_v09 where order_id='r9-order'")).rows[0].n,
   1
  );
  assert.equal(
   (await db.query("select count(*)::int n from alpha_hunter_paper_cohort_membership_v10 where order_id='r9-order'")).rows[0].n,
   0
  );

  await assert.rejects(
   db.query(`
    insert into alpha_hunter_profitability_test_activations_v01
    (spec_id,started_at_utc,baseline_scientific_fingerprint_sha256)
    values('R10','2026-10-05T08:00:01Z',$1)
   `,['e'.repeat(64)]),
   /fingerprint must match/
  );

  await db.query(`
   insert into alpha_hunter_profitability_test_activations_v01
   (spec_id,started_at_utc,baseline_scientific_fingerprint_sha256)
   values('R10','2026-10-05T08:00:01Z',$1)
  `,['d'.repeat(64)]);
  assert.equal(
   (await db.query("select count(*)::int n from alpha_hunter_profitability_test_activations_v01 where spec_id='R10'")).rows[0].n,
   1
  );

  await assert.rejects(
   db.exec(`
    insert into alpha_hunter_paper_orders_v02
    (order_id,decision_id,submitted_at_utc,symbol,direction,successor_activation_id)
    values('partial','d-wrong','2026-10-05T08:22:00Z','PARTIALUSDT','LONG','PAPER_EXECUTION_R10')
   `)
  );
 }finally{
  await db.close();
 }
});
