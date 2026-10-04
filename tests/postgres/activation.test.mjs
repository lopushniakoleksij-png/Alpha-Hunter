import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
const read=n=>readFileSync(new URL(n,import.meta.url),'utf8');
const commit='b'.repeat(40),fp='a'.repeat(64);
async function setup(){
 const db=new PGlite();
 for(const f of ['horizon-schema.sql','activation-schema.sql','../../ops/sql/paper_horizon_successor_v09.sql','../../ops/sql/paper_successor_activation_v09.sql'])await db.exec(read(f));
 await db.query('select private.alpha_hunter_preregister_r9_v01($1,$2)',[commit,fp]);return db;
}
async function baseline(db){
 const payload={validation_identity:{git_commit:commit,scientific_fingerprint_sha256:fp,run_source:'RENDER_CRON',runtime_role:'RENDER_CRON',config_sha256:'config'},previous_snapshot_context:{source:'LOCAL_LATEST'},catalyst_summary:{version:'0.2'},multi_strategy_summary:{configured_strategy_count:10}};
 await db.query(`insert into alpha_hunter_snapshots(run_id,collected_at_utc,payload) values('baseline',clock_timestamp(),$1)`,[JSON.stringify(payload)]);
 await db.exec(`insert into alpha_hunter_symbol_snapshots(run_id,payload) values('baseline','{"multi_strategy_engine":{},"microstructure":{},"timeframes":{"1H":{"last_closed_candle":{}}}}');`);
 await db.query(`insert into alpha_hunter_production_deployment_runtime_status_v03(deployment_status,live_runtime_git_commit) values('MATCHED',$1)`,[commit]);
}
const activate=db=>db.query('select private.alpha_hunter_activate_r9_v01($1,$2)',[commit,fp]);
test('preregistration alone never opens paper admission',async()=>{const db=await setup();try{
 assert.equal((await db.query('select count(*) n from alpha_hunter_paper_admission_open_v09')).rows[0].n,0);
 await assert.rejects(activate(db),/Fresh corrected canonical runtime/);
}finally{await db.close();}});
test('verified activation aligns identities after verification and is idempotent',async()=>{const db=await setup();try{
 await baseline(db);await activate(db);await activate(db);
 const e=(await db.query('select * from alpha_hunter_paper_execution_activation_v09')).rows[0];
 const p=(await db.query('select * from alpha_hunter_profitability_test_activations_v01')).rows[0];
 assert.equal(e.activated_at_utc.toISOString(),p.started_at_utc.toISOString());
 assert.equal(e.scientific_fingerprint_sha256,p.baseline_scientific_fingerprint_sha256);
 const guards=(await db.query(`select activated_at_utc>runtime_verified_at_utc ok,admission_cutoff_at_utc=activated_at_utc+interval '30 days' cut from alpha_hunter_paper_execution_activation_v09`)).rows[0];
 assert.equal(guards.ok,true);assert.equal(guards.cut,true);
 assert.equal((await db.query('select count(*) n from alpha_hunter_paper_execution_activation_v09')).rows[0].n,1);
}finally{await db.close();}});
for(const defect of ['incomplete','stale','fingerprint','deployment'])test(`activation rejects ${defect} without partial identity`,async()=>{const db=await setup();try{
 await baseline(db);
 if(defect==='incomplete')await db.exec('delete from alpha_hunter_symbol_snapshots');
 if(defect==='stale')await db.exec(`update alpha_hunter_snapshots set collected_at_utc=clock_timestamp()-interval '1 hour'`);
 if(defect==='fingerprint')await db.exec(`update alpha_hunter_snapshots set payload=jsonb_set(payload,'{validation_identity,scientific_fingerprint_sha256}','"wrong"')`);
 if(defect==='deployment')await db.exec(`update alpha_hunter_production_deployment_runtime_status_v03 set deployment_status='DRIFT'`);
 await assert.rejects(activate(db));
 assert.equal((await db.query('select count(*) n from alpha_hunter_paper_execution_activation_v09')).rows[0].n,0);
 assert.equal((await db.query('select count(*) n from alpha_hunter_profitability_test_activations_v01')).rows[0].n,0);
}finally{await db.close();}});
