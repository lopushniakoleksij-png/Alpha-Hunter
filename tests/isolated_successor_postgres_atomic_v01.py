"""Run ONLY against disposable GitHub Actions postgres:16/17 service.

Never connect to Supabase/Render/Bitget; synthetic paper research only.
All source events and protective acknowledgments are invented fixture values.
"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

import psycopg

CONN = os.environ.get(
    "SUCCESSOR_LAB_TEST_DSN",
    "host=localhost port=5432 dbname=postgres user=postgres password=isolated_research_only",
)
D = Decimal


def db():
    return psycopg.connect(CONN, autocommit=True)


def create_position(position_id, side="LONG"):
    entry,stop,target = ("0.6992","0.6923","0.7867") if side=="LONG" else ("1","1.1","0.8")
    with db() as c:
        c.execute(
            """INSERT INTO successor_lab.positions
            (position_id,side,entry_qty,entry_price,stop_price,target_price,
             entry_fee,remaining_qty,last_event_at)
             VALUES (%s,%s,362,%s,%s,%s,0.25,362,'2026-10-02T16:07:20Z')""",
            (position_id,side,entry,stop,target),
        )
        c.execute(
            """INSERT INTO successor_lab.guards
            (position_id,revision,covered_qty,stop_id,target_id,oco_group,
             stop_ack,target_ack,acknowledged_at,guard_status)
            VALUES (%s,0,362,'stop-0','target-0','group-A','stop-ack-0',
              'target-ack-0','2026-10-02T16:07:20Z','ARMED')""",
            (position_id,),
        )


def packet(revision=0, quantity="100", *, side="LONG", terminal=False):
    n=revision+1
    times=["2026-10-02T23:03:32Z","2026-10-02T23:23:04Z",
           "2026-10-02T23:42:58Z"]
    prices=[("0.8053","0.8078","0.805"),
            ("0.8327","0.8353","0.832"),
            ("0.824","0.8268","0.8234")]
    if side=="LONG":
        bid,ask,price=prices[revision]
        typ="TAKE_PROFIT"
        active=f"target-{revision}"
    else:
        bid,ask,price=("0.798","0.799","0.7995")
        typ="TAKE_PROFIT"
        active=f"target-{revision}"
    remaining=D("362")-sum(
        (D("100"), D("200"), D("62"))[:revision+1]
    ) if quantity in ("100","200","62") and side=="LONG" else D("362")-D(quantity)
    # For custom nondefault quantities tests, override covered_qty explicitly.
    return {
        "event_id":f"synthetic-event-{revision+1}",
        "receipt_sha256":f"{revision+1:064x}",
        "quote_id":f"synthetic-quote-{revision+1}",
        "evidence_kind":"ISOLATED_SYNTHETIC_RECEIPT",
        "expected_revision":revision,
        "event_time":times[revision],
        "quantity":quantity,
        "exit_price":price,
        "best_bid":bid,
        "best_ask":ask,
        "visible_exit_size":"100" if revision==0 else ("276" if revision==1 else "70"),
        "fee_bps":"6",
        "trigger_type":typ,
        "trigger_guard_id":active,
        "next_guard":{
            "revision":n,"covered_qty":str(remaining),
            "stop_id":f"stop-{n}","target_id":f"target-{n}",
            "stop_ack":f"stop-ack-{n}","target_ack":f"target-ack-{n}",
            "prior_stop_cancel_ack":f"stop-cancel-rev-{revision}",
            "prior_target_cancel_ack":f"target-cancel-rev-{revision}",
            "oco_group":"group-A",
            "acknowledged_at":times[revision].replace(":32Z",":33Z")
                            .replace(":04Z",":05Z").replace(":58Z",":59Z"),
            "guard_status":"CANCELLED" if terminal else "ARMED",
        }
    }


def exec_exit(position_id,p):
    with db() as c:
        return c.execute(
          "SELECT successor_lab.apply_synthetic_exit(%s,%s::jsonb)",
          (position_id,psycopg.types.json.Jsonb(p)),
        ).fetchone()[0]


def verify(position_id,event_id="synthetic-event-1",receipt=f"{1:064x}"):
    with db() as c:
        return c.execute(
            "SELECT successor_lab.verify_event(%s,%s,%s)",
            (position_id,event_id,receipt),
        ).fetchone()[0]


def snapshot(pid):
    with db() as c:
        return c.execute(
            """SELECT entry_qty,remaining_qty,realized_qty,allocated_entry_fee,
            realized_gross,realized_exit_fee,revision,state
            FROM successor_lab.positions WHERE position_id=%s""",(pid,)
        ).fetchone()


def counts(pid):
    with db() as c:
        return [
            c.execute(f"SELECT count(*) FROM successor_lab.{table} WHERE position_id=%s",(pid,)).fetchone()[0]
            for table in ("synthetic_exit_events","guards","custody_ledger")
        ]


class IsolatedAtomicReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.id="fixture_"+uuid4().hex
        create_position(self.id)

    def test_three_partial_exits_atomic_residual_cover_and_net_cost(self):
        p1=packet(0)
        self.assertEqual(exec_exit(self.id,p1),"ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(verify(self.id),"VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(snapshot(self.id)[1],D("262"))
        self.assertEqual(counts(self.id),[1,2,1])
        p2=packet(1,"200")
        self.assertEqual(exec_exit(self.id,p2),"ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(snapshot(self.id)[1],D("62"))
        self.assertEqual(verify(self.id,p2["event_id"],p2["receipt_sha256"]),
                         "VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        p3=packet(2,"62",terminal=True)
        self.assertEqual(exec_exit(self.id,p3),"ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        eq,remaining,realized,entry_fees,gross,exit_fees,rev,state=snapshot(self.id)
        self.assertEqual((eq,remaining,realized,rev,state),(D("362"),D(0),D("362"),3,"CLOSED"))
        self.assertEqual(counts(self.id),[3,4,3])
        self.assertEqual(entry_fees,D(".25"))
        expected_gross=sum((D(px)-D(".6992"))*D(q) for px,q in [
                            (".805","100"),(".832","200"),(".8234","62")])
        self.assertEqual(gross,expected_gross)
        expected_exit_fees=sum((D(px)*D(q)*D(6)/D(10000)) for px,q in [
                               (".805","100"),(".832","200"),(".8234","62")])
        self.assertEqual(exit_fees,expected_exit_fees)
        self.assertGreater(gross-entry_fees-exit_fees,D(0))
        self.assertEqual(verify(self.id,p1["event_id"],p1["receipt_sha256"]),
                         "VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(verify(self.id,p3["event_id"],p3["receipt_sha256"]),
                         "VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        with db() as c:
            rows=c.execute(
                """SELECT revision,covered_qty,guard_status,
                prior_stop_cancel_ack,prior_target_cancel_ack
                FROM successor_lab.guards WHERE position_id=%s
                ORDER BY revision""",(self.id,),
            ).fetchall()
        self.assertEqual([x[1] for x in rows],list(map(D,["362","262","62","0"])))
        self.assertEqual([x[2] for x in rows],["ARMED","ARMED","ARMED","CANCELLED"])
        self.assertTrue(all(r[3] and r[4] for r in rows[1:]))

    def test_lost_http_response_after_commit_verifies_full_chain_then_idempotent(self):
        p=packet()
        # Simulated response loss: send autocommit write, deliberately discard
        # its returned result and close the connection.
        with db() as c:
            c.execute("SELECT successor_lab.apply_synthetic_exit(%s,%s::jsonb)",
                      (self.id,psycopg.types.json.Jsonb(p)))
        self.assertEqual(verify(self.id),"VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(exec_exit(self.id,p),"DUPLICATE_VERIFIED_NOOP")
        self.assertEqual(counts(self.id),[1,2,1])
        self.assertEqual(snapshot(self.id)[1],D("262"))

    def test_terminal_duplicate_retry_remains_verifiable(self):
        exec_exit(self.id,packet(0))
        exec_exit(self.id,packet(1,"200"))
        p3=packet(2,"62",terminal=True)
        exec_exit(self.id,p3)
        self.assertEqual(exec_exit(self.id,p3),"DUPLICATE_VERIFIED_NOOP")
        self.assertEqual(snapshot(self.id)[7],"CLOSED")
        self.assertEqual(counts(self.id),[3,4,3])

    def test_injected_crash_after_each_child_rolls_back_everything(self):
        for fault in ("AFTER_FILL","AFTER_GUARD","AFTER_LEDGER"):
            p=packet()
            p["inject_fault"]=fault
            with self.assertRaises(psycopg.Error):
                exec_exit(self.id,p)
            self.assertEqual(snapshot(self.id)[1],D("362"))
            self.assertEqual(counts(self.id),[0,1,0])
            self.assertEqual(verify(self.id),"NO_COMMIT_VISIBLE_NEEDS_SOURCE_RECHECK")

    def test_missing_guard_ack_does_not_record_any_partial_fill(self):
        for missing in ("stop_ack","target_ack","prior_stop_cancel_ack",
                        "prior_target_cancel_ack"):
            p=packet()
            p["next_guard"][missing]=""
            with self.assertRaises(psycopg.Error):
                exec_exit(self.id,p)
            self.assertEqual(counts(self.id),[0,1,0])
        self.assertEqual(snapshot(self.id)[1],D("362"))

    def test_never_overfill_from_one_top_book_quote(self):
        p=packet()
        p["quantity"]="362"
        p["next_guard"]["covered_qty"]="0"
        p["next_guard"]["guard_status"]="CANCELLED"
        with self.assertRaises(psycopg.Error):
            exec_exit(self.id,p)
        self.assertEqual(counts(self.id),[0,1,0])

    def test_duplicate_id_conflicting_receipt_is_not_accepted(self):
        p=packet()
        exec_exit(self.id,p)
        different=dict(p)
        different["receipt_sha256"]="f"*64
        with self.assertRaises(psycopg.Error):
            exec_exit(self.id,different)
        self.assertEqual(verify(self.id),"VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(counts(self.id),[1,2,1])

    def test_reused_quote_or_digest_under_new_event_id_rejected(self):
        p=packet()
        exec_exit(self.id,p)
        for k in ("receipt_sha256","quote_id"):
            other=packet(1,"20")
            other["next_guard"]["covered_qty"]="242"
            other[k]=p[k]
            with self.assertRaises(psycopg.Error):
                exec_exit(self.id,other)
        self.assertEqual(counts(self.id),[1,2,1])

    def test_corrupt_missing_ledger_prevents_claim_of_complete_after_timeout(self):
        p=packet()
        exec_exit(self.id,p)
        with db() as c:
            c.execute("DELETE FROM successor_lab.custody_ledger WHERE position_id=%s",(self.id,))
        self.assertEqual(verify(self.id),"HALTED_MISSING_CUSTODY_LEDGER")
        with self.assertRaises(psycopg.Error):
            exec_exit(self.id,p)
        self.assertEqual(counts(self.id),[1,2,0])

    def test_corrupt_remaining_parent_rejected_even_with_present_children(self):
        exec_exit(self.id,packet())
        with db() as c:
            c.execute("""UPDATE successor_lab.positions
                          SET remaining_qty=261, realized_qty=101
                          WHERE position_id=%s""",(self.id,))
        self.assertTrue(verify(self.id).startswith("HALTED_"))

    def test_wrong_guard_residual_not_applied(self):
        p=packet()
        p["next_guard"]["covered_qty"]="263"
        with self.assertRaises(psycopg.Error):
            exec_exit(self.id,p)
        self.assertEqual(counts(self.id),[0,1,0])

    def test_stale_revision_two_distinct_fills_cannot_double_spend(self):
        p=packet()
        other=packet()
        other["event_id"]="synthetic-concurrent-2"
        other["receipt_sha256"]="e"*64
        other["quote_id"]="synthetic-quote-other"
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks=[pool.submit(exec_exit,self.id,x) for x in (p,other)]
            values=[]
            for task in tasks:
                try: values.append(task.result(timeout=25))
                except psycopg.Error as e: values.append(type(e).__name__)
        self.assertEqual(sum(x=="ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL" for x in values),1,values)
        self.assertEqual(counts(self.id),[1,2,1])
        self.assertEqual(snapshot(self.id)[1],D("262"))

    def test_serializable_isolation_separate_commit_verified(self):
        p=packet()
        with db() as c:
            with c.transaction():
                c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                result=c.execute("SELECT successor_lab.apply_synthetic_exit(%s,%s::jsonb)",
                                 (self.id,psycopg.types.json.Jsonb(p))).fetchone()[0]
                self.assertEqual(result,"ATOMIC_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
        self.assertEqual(verify(self.id),"VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")

    def test_signed_quote_and_provider_execution_not_accidentally_accepted(self):
        for source in ("BITGET_LIVE",None,"UNVERIFIED_QUOTE"):
            p=packet()
            p["evidence_kind"]=source
            with self.assertRaises(psycopg.Error):
                exec_exit(self.id,p)
        self.assertEqual(counts(self.id),[0,1,0])

    def test_reader_can_reconcile_but_never_mutate_positions_or_call_apply(self):
        exec_exit(self.id,packet())
        with db() as c:
            c.execute("SET ROLE successor_lab_reader")
            self.assertEqual(c.execute(
                "SELECT successor_lab.verify_event(%s,%s,%s)",
                (self.id,"synthetic-event-1",f"{1:064x}"),
            ).fetchone()[0],"VERIFIED_SYNTHETIC_COMMIT_NOT_A_PROVIDER_FILL")
            for sql,args in [
                ("UPDATE successor_lab.positions SET state='CLOSED' WHERE position_id=%s",(self.id,)),
                ("SELECT successor_lab.apply_synthetic_exit(%s,%s::jsonb)",
                 (self.id,psycopg.types.json.Jsonb(packet(1,"200")))),
            ]:
                with self.assertRaises(psycopg.Error):
                    c.execute(sql,args)
        self.assertEqual(snapshot(self.id)[1],D("262"))


if __name__=="__main__":
    unittest.main(verbosity=2)
