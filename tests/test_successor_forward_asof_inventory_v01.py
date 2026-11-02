"""Synthetic prospective fill-minus-exit evidence, including unknown legacy partials."""
from copy import deepcopy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/reviews/successor_forward_asof_inventory_v01.py"
spec = importlib.util.spec_from_file_location("successor_forward_asof_inventory", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CUTOFF = "2026-10-12T12:00:00Z"
CAPTURE = "2026-10-12T12:00:08Z"


def source():
    fields = dict(paper_only=True, exchange_authority=False,
                  trade_permission=False, order_path="NONE")
    orders = [
        dict(order_id="nmr-old-partial", symbol="NMRUSDT", direction="LONG",
             submitted_at_utc="2026-10-03T10:00:00Z",
             created_at="2026-10-03T10:00:00Z", **fields),
        dict(order_id="q-new", symbol="QUSDT", direction="LONG",
             submitted_at_utc="2026-10-12T11:45:00Z",
             created_at="2026-10-12T11:45:00Z", **fields),
        dict(order_id="fully-closed", symbol="ETHUSDT", direction="SHORT",
             submitted_at_utc="2026-10-12T11:30:00Z",
             created_at="2026-10-12T11:30:00Z", **fields),
    ]
    entries = [
        dict(fill_id="nmr-fill", order_id="nmr-old-partial", quantity="1.5",
             filled_at_utc="2026-10-03T10:01:00Z", created_at="2026-10-03T10:01:02Z",
             source_run_id="old-run", **fields),
        dict(fill_id="q-fill-1", order_id="q-new", quantity="2",
             filled_at_utc="2026-10-12T11:46:00Z", created_at="2026-10-12T11:46:02Z",
             source_run_id="new-run", **fields),
        dict(fill_id="q-fill-2", order_id="q-new", quantity="3",
             filled_at_utc="2026-10-12T11:47:00Z", created_at="2026-10-12T11:47:02Z",
             source_run_id="new-run", **fields),
        dict(fill_id="eth-entry", order_id="fully-closed", quantity="0.5",
             filled_at_utc="2026-10-12T11:35:00Z", created_at="2026-10-12T11:35:05Z",
             source_run_id="new-run", **fields),
    ]
    exits = [
        dict(exit_fill_id="q-exit-partial", entry_order_id="q-new", quantity="1.25",
             symbol="QUSDT", direction="LONG",
             filled_at_utc="2026-10-12T11:56:00Z", created_at="2026-10-12T11:56:01Z",
             source_run_id="new-run", **fields),
        dict(exit_fill_id="eth-exit", entry_order_id="fully-closed", quantity="0.5",
             symbol="ETHUSDT", direction="SHORT",
             filled_at_utc="2026-10-12T11:39:00Z", created_at="2026-10-12T11:39:01Z",
             source_run_id="new-run", **fields),
    ]
    tables = ["alpha_hunter_paper_orders_v02","alpha_hunter_paper_fills_v02",
              "alpha_hunter_paper_exit_fills_v04"]
    receipts = {t: dict(source_table=t,complete=True,
                        consistent_snapshot_id="synthetic-repeatable-read-tx-1",
                        captured_at_utc=CAPTURE) for t in tables}
    return orders, entries, exits, receipts


def build(inp=None):
    return mod.build_forward_asof_inventory(
        *(inp if inp is not None else source()),
        asof_utc=CUTOFF,max_source_capture_lag_seconds=20
    )


def test_partial_legacy_is_included_regardless_of_managed_view_or_cohort():
    raw = source()
    before = deepcopy(raw)
    result = build(raw)
    assert raw == before
    assert result == build(raw)
    assert result["status"] == "SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"
    assert result["expected_position_count"] == 2
    assert [p["entry_order_id"] for p in result["positions"]] == ["nmr-old-partial","q-new"]
    assert result["positions"][0]["residual_qty"] == "1.5"
    assert result["positions"][1]["residual_qty"] == "3.75"
    assert result["positions"][1]["entry_fill_ids"] == ["q-fill-1","q-fill-2"]
    assert result["manifest_sha256"] and len(result["manifest_sha256"]) == 64
    assert result["scientific_pass_permitted"] is False
    assert result["trade_permission"] is False


def test_later_exit_never_retroactively_removes_open_position():
    inp = list(source())
    inp[2].append(dict(inp[2][0],exit_fill_id="future-exit",
                       entry_order_id="nmr-old-partial",symbol="NMRUSDT",
                       direction="LONG",quantity="1.5",
                       filled_at_utc="2026-10-12T12:20:00Z",
                       created_at="2026-10-12T12:20:01Z"))
    result = build(tuple(inp))
    assert result["expected_position_count"] == 2
    assert result["positions"][0]["entry_order_id"] == "nmr-old-partial"


def test_late_arriving_fill_fails_instead_of_hindsight_inventory():
    inp = list(source())
    inp[1][0]["created_at"] = "2026-10-12T12:05:00Z"
    assert "LATE_OR_UNSAFE_FILL_EVIDENCE" in build(tuple(inp))["blockers"]


def test_missing_one_source_capture_or_non_atomic_read_fails():
    inp = list(source())
    del inp[3]["alpha_hunter_paper_exit_fills_v04"]
    assert build(tuple(inp))["status"] == "SOURCE_EVIDENCE_UNKNOWN_OR_INVALID"
    inp = list(source())
    inp[3]["alpha_hunter_paper_exit_fills_v04"]["consistent_snapshot_id"] = "different-snapshot"
    assert "SOURCE_TABLES_NOT_ONE_CONSISTENT_READ" in build(tuple(inp))["blockers"]


def test_stale_source_capture_fails_closed():
    inp = list(source())
    inp[3]["alpha_hunter_paper_fills_v02"]["captured_at_utc"] = "2026-10-12T12:01:00Z"
    assert "SOURCE_CAPTURE_TIME_NOT_PROSPECTIVE" in build(tuple(inp))["blockers"]


def test_over_exit_and_duplicate_source_ids_fail():
    inp = list(source())
    inp[2][0]["quantity"]="9"
    assert "OVER_EXIT_OR_ORPHAN_RESIDUAL" in build(tuple(inp))["blockers"]
    inp = list(source())
    inp[1].append(dict(inp[1][0]))
    assert "DUPLICATE_FILL_ID" in build(tuple(inp))["blockers"]


def test_entry_or_exit_missing_parent_is_not_hidden():
    inp = list(source())
    inp[0].pop(0)
    assert "ORPHAN_FILL_ORDER" in build(tuple(inp))["blockers"]
    inp = list(source())
    inp[2].append(dict(inp[2][0],exit_fill_id="orphan",entry_order_id="missing-order"))
    assert "ORPHAN_FILL_ORDER" in build(tuple(inp))["blockers"]


def test_source_ids_and_direction_integrity_required():
    inp = list(source())
    inp[1][0]["source_run_id"] = None
    assert "FILL_SOURCE_RUN_ID_MISSING" in build(tuple(inp))["blockers"]
    inp = list(source())
    inp[2][0]["direction"] = "SHORT"
    assert "EXIT_POSITION_IDENTITY_MISMATCH" in build(tuple(inp))["blockers"]
    inp = list(source())
    inp[0][0]["exchange_authority"] = True
    assert "ORDER_ID_TIME_AUTHORITY_INVALID" in build(tuple(inp))["blockers"]


def test_no_source_data_is_not_a_certified_empty_inventory():
    inp = list(source())
    inp[0].clear()
    inp[1].clear()
    inp[2].clear()
    res=build(tuple(inp))
    assert res["expected_position_count"] == 0
    assert res["status"] == "SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"
    assert "NO INDEPENDENT SOURCE COMPLETENESS" in res["caveat"]


def test_no_runtime_import_or_live_connection():
    code = SOURCE.read_text(encoding="utf-8")
    for bad in ("supabase.", "requests.", "bitget_client", "create_order", "execute_sql("):
        assert bad not in code
    assert "alpha_hunter_paper_protection_open_v04" not in code
    for p in ("alpha_hunter/storage.py","alpha_hunter/paper_exit.py","hourly.py"):
        assert "successor_forward_asof_inventory_v01" not in (ROOT/p).read_text()
