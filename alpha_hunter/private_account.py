from __future__ import annotations
from typing import Any
from .bitget import BitgetAPIError, BitgetClient

def collect_private_account_snapshot(client: BitgetClient, product_type: str, margin_coin: str = "USDT") -> dict[str, Any]:
    if not client.private_api_configured:
        return {"status": "NOT_CONFIGURED", "accounts": [], "open_positions": [], "open_position_count": 0}
    try:
        accounts = client.futures_accounts(product_type)
        positions = client.futures_positions(product_type, margin_coin)
    except BitgetAPIError as exc:
        return {"status": "FAILED", "error": str(exc), "accounts": [], "open_positions": [], "open_position_count": 0}

    open_positions = []
    for p in positions:
        try:
            total = float(p.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total == 0:
            continue
        open_positions.append({
            "symbol": p.get("symbol"),
            "hold_side": p.get("holdSide"),
            "total": p.get("total"),
            "available": p.get("available"),
            "leverage": p.get("leverage"),
            "margin_mode": p.get("marginMode"),
            "open_price_avg": p.get("openPriceAvg"),
            "mark_price": p.get("markPrice"),
            "unrealized_pl": p.get("unrealizedPL"),
            "break_even_price": p.get("breakEvenPrice"),
            "liquidation_price": p.get("liquidationPrice"),
            "take_profit": p.get("takeProfit"),
            "stop_loss": p.get("stopLoss"),
        })
    safe_accounts = [{
        "margin_coin": a.get("marginCoin"),
        "available": a.get("available"),
        "locked": a.get("locked"),
        "account_equity": a.get("accountEquity"),
        "unrealized_pl": a.get("unrealizedPL"),
    } for a in accounts]
    return {"status": "CONNECTED", "accounts": safe_accounts, "open_positions": open_positions, "open_position_count": len(open_positions)}
