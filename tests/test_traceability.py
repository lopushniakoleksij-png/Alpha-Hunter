from datetime import datetime, timezone

from alpha_hunter.traceability import (
    ReadyEpisode,
    attach_fill_matches,
    make_ready_id,
    rolling_summary,
    strict_production_ready,
    update_ready_ledger,
)


def test_strict_production_ready_requires_both_gates():
    assert strict_production_ready({"trade_permission": True, "v7_trade_ready": True}) is True
    assert strict_production_ready({"trade_permission": True, "v7_trade_ready": False}) is False
    assert strict_production_ready({"trade_permission": False, "v7_trade_ready": True}) is False
    assert strict_production_ready({"trade_permission": False, "v7_trade_ready": False}) is False


def test_ready_id_is_deterministic_and_episode_specific():
    when = "2026-08-30T12:00:00+00:00"
    a = make_ready_id("HYPEUSDT", "LONG", when, "episode-a")
    b = make_ready_id("HYPEUSDT", "LONG", when, "episode-a")
    c = make_ready_id("HYPEUSDT", "LONG", when, "episode-b")
    assert a == b
    assert a != c
    assert a.startswith("RDY-")


def test_update_ledger_creates_and_ends_distinct_ready_episode():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "LONG", "entry": 1.0, "rr": 6.0},
        "last_price": 1.0,
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    assert len(episodes) == 1
    assert episodes[0].ready_status == "READY"
    assert episodes[0].direction == "LONG"

    blocked = dict(ready)
    blocked["v7_trade_ready"] = False
    update_ready_ledger(episodes, [blocked], "2026-08-30T11:00:00+00:00")
    assert episodes[0].ready_status == "READY_ENDED"
    assert episodes[0].ended_at_utc == "2026-08-30T11:00:00+00:00"

    update_ready_ledger(episodes, [ready], "2026-08-30T12:00:00+00:00")
    assert len(episodes) == 2
    assert episodes[1].ready_status == "READY"
    assert episodes[0].ready_id != episodes[1].ready_id


def test_missing_symbol_does_not_terminate_ready_episode():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "SHORT"},
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    update_ready_ledger(episodes, [{"symbol": "OTHERUSDT"}], "2026-08-30T11:00:00+00:00")
    assert episodes[0].ready_status == "READY"


def test_fill_match_is_heuristic_not_verified():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "SHORT"},
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    fills = [
        {
            "tradeId": "t1",
            "orderId": "o1",
            "symbol": "TESTUSDT",
            "side": "sell",
            "tradeSide": "sell_single",
            "profit": "0",
            "price": "0.99",
            "cTime": str(int(datetime(2026, 8, 30, 10, 5, tzinfo=timezone.utc).timestamp() * 1000)),
            "enterPointSource": "ios",
        }
    ]
    attach_fill_matches(episodes, fills)
    assert episodes[0].first_execution_at_utc is not None
    assert episodes[0].execution_match_quality == "HEURISTIC_FILL_MATCH"
    assert episodes[0].execution_trade_ids == ["t1"]


def test_rolling_summary_separates_symbols_from_episodes():
    episodes = [
        ReadyEpisode(
            ready_id="RDY-1",
            symbol="HYPEUSDT",
            direction="LONG",
            first_ready_at_utc="2026-08-29T10:00:00+00:00",
            last_ready_at_utc="2026-08-29T10:00:00+00:00",
        ),
        ReadyEpisode(
            ready_id="RDY-2",
            symbol="HYPEUSDT",
            direction="SHORT",
            first_ready_at_utc="2026-08-30T10:00:00+00:00",
            last_ready_at_utc="2026-08-30T10:00:00+00:00",
        ),
        ReadyEpisode(
            ready_id="RDY-3",
            symbol="ADAUSDT",
            direction="LONG",
            first_ready_at_utc="2026-08-30T11:00:00+00:00",
            last_ready_at_utc="2026-08-30T11:00:00+00:00",
        ),
    ]
    summary = rolling_summary(
        episodes,
        now_utc="2026-08-30T12:00:00+00:00",
        hours=168,
    )
    assert summary["distinct_trade_ready_coins"] == 2
    assert summary["distinct_trade_ready_episodes"] == 3
    assert summary["trade_ready_long"] == 2
    assert summary["trade_ready_short"] == 1
