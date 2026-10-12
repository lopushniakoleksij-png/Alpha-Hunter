// FULL AFFECTED TABLE COLUMN/CHECK/INDEX TEST, NEVER PROD.
// Live DDL and verbatim 2026-10-12 strategy trigger are in separate read-only
// extracted fixture. Only isolated PGlite memory databases are written.
// Values/results of this single-run WASM test must NEVER justify a deployment.
import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const fixture = readFileSync(
  new URL('successor-full-production-schema-fixture.sql', import.meta.url), 'utf8'
);
const candidate = readFileSync(
  new URL('../../ops/reviews/successor_full_schema_set_based_candidate_v01.sql', import.meta.url),
  'utf8'
).split('-- NEXT STATEMENT').map(x=>x.trim()).filter(Boolean);

assert.equal(candidate.length,2,'two explicit SELECT-INSERT statements');
const sizes = [16,48,64,64,64]; // three independent fresh 64-symbol trials
const CLOCK = '2026-10-12T12:00:00Z';

function payload(runId,i,mode='normal') {
  if(mode==='missing-strategies') return {symbol:`SYNTH${i}USDT`,market_phase:'RANGE'};
  if(mode==='invalid-array') return {last_price:2.0,multi_strategy_engine:{strategies:{not_an_array:true}}};
  return {
    symbol:`SYNTH${i}USDT`,
    last_price: i%3===0 ? String(1+i*0.01) : 1+i*0.01,
    market_phase: i%2?'PRE_MOVE':'IGNITION',opportunity_timing:'EARLY',
    timeframes:{'1H':{trend:'UP',candles:['x'.repeat(512)]}},
    multi_strategy_engine:{
      strategies:Array.from({length:10},(_,j)=>{
        const watch=j===0 || j===1;
        const optional=j%4===3;
        return {
          strategy_id:`S${j+1}`,
          strategy_name:`Synthetic candidate ${j+1}`,
          engine_version:'synthetic-isolated-v0.1',
          status:j===0?'WATCH':j===1?'SHADOW_CANDIDATE':'NO_SAFE_TRADE',
          action:watch?'WAIT_FOR_TRIGGER':'NO_SAFE_TRADE',
          direction:optional ? '' : j%2===0?'LONG':'SHORT',
          signal_score:optional?'':(j+1.17),
          score_is_calibrated:j%2===0,entry:optional?'':String(1+i*0.01),
          stop:optional?'':String(.9+i*.01),target:optional?'':String(1.2+i*.01),
          risk:optional?'':String(0.1),reward:optional?'':String(.2),
          rr:optional?'':String(2),distance_to_entry_pct:optional?'':String(.9),
          geometry_valid:j%2===0,
          evidence:{id:`evidence-${j}`,payload:'a'.repeat(340)},
          checks:{risk:j%2===0,source:'SYNTHETIC'},
          reasons:watch?[]:['LOW_QUALITY'],
          persistence:{
            strategy_instance_id:watch?`synthetic-${runId}-${i}-${j}`:'',
            first_seen_at_utc:watch ? CLOCK : '',
            consecutive_scans: watch?'2':'0', state:watch?'PERSISTENT':'NONE'
          }
        };
      }),
    }
  };
}
const sym=i=>`SYNTH${String(i).padStart(3,'0')}USDT`;

function makeRows(runId,count,extra=false){
  let result=Array.from({length:count},(_,i)=>({
    run_id:runId,symbol:sym(i),collected_at_utc:CLOCK,
    payload:payload(runId,i)
  }));
  if(extra){
    result.push({run_id:runId,symbol:'SYNTH_NO_ARRAY',collected_at_utc:CLOCK,
                 payload:payload(runId,999,'missing-strategies')});
    result.push({run_id:runId,symbol:'SYNTH_INVALID_ARRAY',collected_at_utc:CLOCK,
                 payload:payload(runId,998,'invalid-array')});
  }
  return result;
}

async function startDb(setBased){
  const db=new PGlite();
  await db.exec(fixture);
  if(setBased){
    // This disablement is ONLY in an ephemeral PGlite database. Never in Supabase!
    await db.exec('DROP TRIGGER trg_ah_capture_strategy_observations_v01 ON public.alpha_hunter_symbol_snapshots');
  }
  return db;
}
async function runIngest(db,setBased,runId,rows){
  await db.exec('BEGIN');
  try{
    await db.query(`INSERT INTO public.alpha_hunter_snapshots(run_id)
        VALUES($1) ON CONFLICT(run_id) DO NOTHING`,[runId]);
    await db.query(`
      INSERT INTO public.alpha_hunter_symbol_snapshots(
        run_id,symbol,collected_at_utc,payload,trade_permission,state
      )
      SELECT x.run_id,x.symbol,x.collected_at_utc::timestamptz,x.payload,false,'WATCH'
      FROM jsonb_to_recordset($1::jsonb)
        AS x(run_id text,symbol text,collected_at_utc text,payload jsonb)
      ON CONFLICT(run_id,symbol) DO UPDATE SET payload=excluded.payload
    `,[JSON.stringify(rows)]);
    if(setBased) for(const query of candidate) await db.query(query,[runId]);
    await db.exec('COMMIT');
  }catch(err){
    await db.exec('ROLLBACK');
    throw err;
  }
}
async function projection(db,runId){
  const obs=(await db.query(`
    SELECT to_jsonb(o)-'created_at' AS item
    FROM public.alpha_hunter_strategy_observations_v01 o
    WHERE o.run_id=$1 ORDER BY o.observation_id
  `,[runId])).rows.map(z=>z.item);
  const epi=(await db.query(`
    SELECT to_jsonb(e)-'created_at' AS item
    FROM public.alpha_hunter_strategy_episodes_v01 e
    WHERE e.first_observation_id IN (
      SELECT observation_id FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=$1
    ) ORDER BY e.episode_id
  `,[runId])).rows.map(z=>z.item);
  return {obs,epi};
}

test('verbatim production trigger vs full-column set-based candidate on 3 sizes and 3 repeated 64-symbol trials: exact evidence and rollback parity',async()=>{
  const baseline=await startDb(false);
  const challenger=await startDb(true);
  let results=[];
  try{
    for(let n=0;n<sizes.length;n++){
      const count=sizes[n],runId=`synthetic-full-parity-run-${n}`;
      const rows=makeRows(runId,count,n===sizes.length-1);
      // Alternate first-execution order to reduce simple warm-cache ordering bias.
      // This remains an in-memory illustrative workload, NOT production profiling.
      let aMs,bMs;
      if(n%2===1){
        const b0=performance.now();
        await runIngest(challenger,true,runId,rows);
        bMs=performance.now()-b0;
        const a0=performance.now();
        await runIngest(baseline,false,runId,rows);
        aMs=performance.now()-a0;
      }else{
        const a0=performance.now();
        await runIngest(baseline,false,runId,rows);
        aMs=performance.now()-a0;
        const b0=performance.now();
        await runIngest(challenger,true,runId,rows);
        bMs=performance.now()-b0;
      }
      const left=await projection(baseline,runId);
      const right=await projection(challenger,runId);
      assert.equal(left.obs.length,count*10);
      assert.equal(left.epi.length,count*2);
      assert.deepEqual(right,left,`FULL ROW PROJECTION DIFFERENCE AT SIZE ${count}`);
      for(let e of left.obs){
        assert.equal(e.shadow_only,true);
        assert.equal(e.trade_permission,false);
        assert.equal(e.production_permission,false);
        assert.equal(e.production_promotion_permitted,false);
        assert.equal(e.order_path,'NONE');
      }
      for(let e of left.epi){
        assert.equal(e.shadow_only,true);
        assert.equal(e.trade_permission,false);
        assert.equal(e.order_path,'NONE');
      }
      // At largest size retry the EXACT same run: no duplicate, no mutation of
      // immutable strategies, even after the symbol payload UPDATE trigger fires.
      if(n===sizes.length-1){
        await runIngest(baseline,false,runId,rows);
        await runIngest(challenger,true,runId,rows);
        assert.deepEqual(await projection(baseline,runId),left);
        assert.deepEqual(await projection(challenger,runId),right);
      }
      results.push({
        symbolCount:count,observationCount:left.obs.length,
        episodeCount:left.epi.length,
        baselineMs:Number(aMs.toFixed(2)),candidateMs:Number(bMs.toFixed(2))
      });
    }

    for(const db of [baseline,challenger]){
      const badRunId='synthetic-rollback-invalid-direction';
      const bad=makeRows(badRunId,2);
      bad[0].payload.multi_strategy_engine.strategies[0].direction='INVALID_DIRECTION';
      // Expect constraint error. Transaction must roll back every parent/child/
      // observation/episode (including earlier rows in same insert).
      await assert.rejects(runIngest(db,db===challenger,badRunId,bad),/constraint/i);
      const q=(await db.query(`SELECT count(*)::int n FROM public.alpha_hunter_symbol_snapshots WHERE run_id=$1`,[badRunId])).rows[0];
      assert.equal(q.n,0);
      assert.equal((await db.query(`SELECT count(*)::int n FROM public.alpha_hunter_snapshots WHERE run_id=$1`,[badRunId])).rows[0].n,0);
      assert.equal((await db.query(`SELECT count(*)::int n FROM public.alpha_hunter_strategy_observations_v01 WHERE run_id=$1`,[badRunId])).rows[0].n,0);
    }
    console.log('P0_FULL_SCHEMA_PARITY '+JSON.stringify({
      evidence:'ISOLATED_PGLITE_SYNTHETIC_EXACT_PRODUCTION_TRIGGER_FULL_3_TARGET_TABLE_COLUMNS',
      benchmarkSets:results,
      allDeterministicColumnsEqualExceptCreatedAt:true,
      retriesStable:true,atomicRollbacks:true,
      productionLatencyGainProved:false,realPostgrestLoadTest:false,
      noProductionDdl:true,noR10Activation:true,permissionForOrders:false
    }));
  }finally{
    await baseline.close();await challenger.close();
  }
});

test('verbatim production strategy trigger and full 3-table schema fixture have immutable scope',()=>{
  assert.match(fixture,/CREATE OR REPLACE FUNCTION private\.alpha_hunter_capture_strategy_observations_v01\(\)/);
  assert.match(fixture,/SET search_path TO ''/);
  assert.match(fixture,/CREATE TRIGGER trg_ah_capture_strategy_observations_v01 AFTER INSERT OR UPDATE OF payload/);
  for(const table of ['alpha_hunter_symbol_snapshots','alpha_hunter_strategy_observations_v01','alpha_hunter_strategy_episodes_v01']){
    assert.match(fixture,new RegExp(`CREATE TABLE public\\."${table}"`));
  }
  assert.match(fixture,/FOREIGN KEY \(run_id\)/);
  assert.match(fixture,/UNIQUE \(run_id, symbol, strategy_id\)/);
  assert.match(fixture,/CHECK \(\(trade_permission = false\)\)/);
  assert.match(fixture,/CHECK \(\(order_path = 'NONE'::text\)\)/);
  assert.equal(candidate.length,2);
  assert.ok(candidate.every(x=>x.includes('WHERE c.run_id=$1')));
  assert.ok(!candidate.some(x=>/drop trigger|alter role|disable trigger|create extension|truncate/i.test(x)));
});
