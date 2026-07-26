from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import requests


class SupabaseStorageError(RuntimeError):
    """Raised when a configured Supabase write fails."""


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    snapshot_table: str = "alpha_hunter_snapshots"
    symbol_table: str = "alpha_hunter_symbol_snapshots"
    timeout_seconds: int = 15

    @classmethod
    def from_environment(cls, config: dict[str, Any]) -> "SupabaseConfig | None":
        storage = config.get("supabase", {})
        if not storage.get("enabled", False):
            return None
        url = os.getenv(storage.get("url_env", "SUPABASE_URL"), "").strip().rstrip("/")
        key = os.getenv(storage.get("key_env", "SUPABASE_SERVICE_ROLE_KEY"), "").strip()
        if not url or not key:
            return None
        return cls(
            url=url,
            key=key,
            snapshot_table=storage.get("snapshot_table", "alpha_hunter_snapshots"),
            symbol_table=storage.get("symbol_table", "alpha_hunter_symbol_snapshots"),
            timeout_seconds=int(storage.get("timeout_seconds", 15)),
        )


def build_run_id(snapshot: dict[str, Any]) -> str:
    raw = "|".join([
        str(snapshot.get("collected_at_utc", "")),
        str(snapshot.get("product_type", "")),
        ",".join(sorted(str(item.get("symbol", "")) for item in snapshot.get("symbols", []))),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class SupabaseStorage:
    def __init__(self, settings: SupabaseConfig, session: requests.Session | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.settings.key,
            "Authorization": f"Bearer {self.settings.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def _upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
        if not rows:
            return
        response = self.session.post(
            f"{self.settings.url}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            headers=self.headers,
            data=json.dumps(rows, separators=(",", ":")),
            timeout=self.settings.timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            body = response.text[:500]
            raise SupabaseStorageError(
                f"Supabase upsert failed for {table}: HTTP {response.status_code}: {body}"
            )

    def save_snapshot(self, snapshot: dict[str, Any]) -> str:
        run_id = snapshot.get("run_id") or build_run_id(snapshot)
        snapshot["run_id"] = run_id
        valid_symbols = [item for item in snapshot.get("symbols", []) if "error" not in item]
        error_count = len(snapshot.get("symbols", [])) - len(valid_symbols)

        parent = [{
            "run_id": run_id,
            "collected_at_utc": snapshot.get("collected_at_utc"),
            "version": snapshot.get("version"),
            "product_type": snapshot.get("product_type"),
            "symbol_count": len(snapshot.get("symbols", [])),
            "error_count": error_count,
            "payload": snapshot,
        }]
        children = []
        for item in snapshot.get("symbols", []):
            children.append({
                "run_id": run_id,
                "symbol": item.get("symbol"),
                "collected_at_utc": snapshot.get("collected_at_utc"),
                "state": item.get("state"),
                "previous_state": item.get("previous_state"),
                "state_changed": item.get("state_changed", False),
                "trade_permission": item.get("trade_permission", False),
                "direction": item.get("execution_setup", {}).get("direction"),
                "reward_risk": item.get("execution_setup", {}).get("rr"),
                "last_price": item.get("last_price"),
                "open_interest": item.get("open_interest"),
                "funding_rate": item.get("funding_rate"),
                "data_integrity_score": item.get("data_integrity_score"),
                "error": item.get("error"),
                "payload": item,
            })

        self._upsert(self.settings.snapshot_table, parent, "run_id")
        self._upsert(self.settings.symbol_table, children, "run_id,symbol")
        return run_id
