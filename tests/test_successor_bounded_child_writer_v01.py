"""Research only. No network, no production persistence, no order authority."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/"ops/reviews/successor_bounded_child_writer_v01.py"
spec=importlib.util.spec_from_file_location("successor_bounded_child_writer",SCRIPT)
lib=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)

def example(n=63):
    return [{"run_id":"synthetic-p2-batch-1","symbol":f"SYNTH{i:03d}USDT",
             "payload":{"symbol":f"SYNTH{i:03d}USDT",
                         "multi_strategy_engine":{"strategies":[{"strategy_id":f"S{j}","status":"WATCH"} for j in range(1,11)]},
                         "data":{"index":i,"tail":"z"*15000}}} for i in range(n)]

def adapter(rows):
    db={}
    calls=[]
    def write(batch):
        calls.append([r["symbol"] for r in batch])
        for row in batch:
            db[row["symbol"]]=dict(row["payload"])
    def read(rid):
        assert rid==rows[0]["run_id"]
        return [{"symbol":k,"payload":v} for k,v in reversed(list(db.items()))]
    return db,calls,write,read

def test_63_symbol_10_strategy_batch_manifest_retains_every_payload():
    rows=example(63)
    before=lib.child_manifest_sha256(rows)
    db,calls,write,read=adapter(rows)
    receipt=lib.persist_and_verify_bounded_children(rows,write_batch=write,
                                                    read_back=read,batch_size=12)
    assert receipt["batch_count"]==6
    assert [len(v) for v in calls]==[12,12,12,12,12,3]
    assert receipt["expected_symbol_count"]==receipt["persisted_symbol_count"]==63
    assert receipt["child_manifest_sha256"]==before
    assert len(db)==63
    assert sum(len(v["multi_strategy_engine"]["strategies"]) for v in db.values())==630
    assert receipt["scientific_pass_permitted"] is False
    assert receipt["trade_permission"] is False
    assert receipt["exchange_authority"] is False

def test_failure_after_two_successful_batches_is_unknown_no_completion_receipt():
    rows=example(63)
    db,calls,write,read=adapter(rows)
    def fails_on_third(batch):
        if len(calls)==2:raise TimeoutError("HTTP 15s read timeout after 3 retries")
        write(batch)
    with pytest.raises(lib.SuccessorChildStageIncomplete,match="WRITE_FAILED"):
        lib.persist_and_verify_bounded_children(rows,write_batch=fails_on_third,
                                               read_back=read,batch_size=12)
    assert len(db)==24

def test_false_204_or_lost_child_after_all_batches_fails_closed():
    rows=example(24)
    db,calls,write,read=adapter(rows)
    def lost_last(batch):
        if len(calls)==0:write(batch)
        else:calls.append([])
    with pytest.raises(lib.SuccessorChildStageIncomplete,match="CARDINALITY"):
        lib.persist_and_verify_bounded_children(rows,write_batch=lost_last,
                                               read_back=read,batch_size=12)

def test_readback_wrong_payload_even_when_counts_match_refused():
    rows=example(24)
    db,calls,write,read=adapter(rows)
    def tampered(rid):
        result=read(rid)
        result[0]["payload"]=dict(result[0]["payload"],state="FORGED")
        return result
    with pytest.raises(lib.SuccessorChildStageIncomplete,match="PAYLOAD_MISMATCH"):
        lib.persist_and_verify_bounded_children(rows,write_batch=write,
                                               read_back=tampered,batch_size=12)

def test_readback_timeout_or_different_run_or_duplicate_symbol_fails():
    rows=example(3)
    db,calls,write,read=adapter(rows)
    def timeout(_):
        raise TimeoutError("readback failed")
    with pytest.raises(lib.SuccessorChildStageIncomplete,match="READBACK_FAILED"):
        lib.persist_and_verify_bounded_children(rows,write_batch=write,read_back=timeout)
    for bad in (rows+[dict(rows[0])],rows+[dict(rows[0],run_id="mixed")]):
        with pytest.raises(ValueError,match="MIXED_RUN_OR_DUPLICATE_SYMBOL"):
            lib.persist_and_verify_bounded_children(bad,write_batch=write,read_back=read)
    with pytest.raises(ValueError,match="SOURCE_SYMBOL_IDENTITY_INVALID"):
        lib.validated_child_batches([dict(rows[0],payload={"symbol":"DIFFERENT"})])
    with pytest.raises(ValueError,match="EXPECTED_SYMBOL_MANIFEST_MISSING"):
        lib.validated_child_batches([])
    with pytest.raises(ValueError,match="INVALID_REVIEW_ONLY_BATCH_SIZE"):
        lib.validated_child_batches(rows,batch_size=0)
    with pytest.raises(ValueError,match="INVALID_REVIEW_ONLY_BATCH_SIZE"):
        lib.validated_child_batches(rows,batch_size=100)

def test_local_retries_idempotently_preserve_exact_same_receipt_identity():
    rows=example(13)
    db,calls,write,read=adapter(rows)
    a=lib.persist_and_verify_bounded_children(rows,write_batch=write,read_back=read,batch_size=8)
    b=lib.persist_and_verify_bounded_children(rows,write_batch=write,read_back=read,batch_size=8)
    assert a==b and len(db)==13 and len(calls)==4

def test_never_imported_by_running_cron_without_review():
    root=SCRIPT.parents[2]
    text=SCRIPT.read_text()
    assert "requests.post(" not in text
    assert "supabase" not in text.lower()
    assert "BITGET_API" not in text
    for file in ("alpha_hunter/storage.py","hourly.py","app.py"):
        assert "successor_bounded_child_writer_v01" not in (root/file).read_text()
