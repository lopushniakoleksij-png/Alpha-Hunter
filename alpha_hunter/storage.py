from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from .feature_capture import compact_source_payload, extract_feature_rows


class SupabaseStorageError(RuntimeError):
    """Raised when configured Supabase persistence or retrieval fails."""


RETRYABLE_SUPABASE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    snapshot_table: str = "alpha_hunter_snapshots"
    symbol_table: str = "alpha_hunter_symbol_snapshots"
    readiness_table: str = "alpha_hunter_readiness_observations_v01"
    timeout_seconds: int = 15
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0

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
            readiness_table=storage.get(
                "readiness_table",
                "alpha_hunter_readiness_observations_v01",
            ),
            timeout_seconds=int(storage.get("timeout_seconds", 15)),
            max_retries=max(0, int(storage.get("max_retries", 2))),
            retry_backoff_seconds=max(
                0.0,
                float(storage.get("retry_backoff_seconds", 1.0)),
            ),
        )


PARENT_STORAGE_CONTRACT = "snapshot-parent-v0.2"


def compact_readiness_record(item: dict[str, Any]) -> dict[str, Any]:
    setup = item.get("execution_setup", {})
    if not isinstance(setup, dict):
        setup = {}
    return {
        "symbol": item.get("symbol"),
        "state": item.get("state"),
        "direction": setup.get("direction") or item.get("direction"),
        "trade_permission": bool(item.get("trade_permission", False)),
        "v7_trade_ready": bool(item.get("v7_trade_ready", False)),
        "last_price": item.get("last_price"),
        "execution_setup": {
            "direction": setup.get("direction"),
            "entry": setup.get("entry"),
            "stop": setup.get("stop"),
            "target": setup.get("target"),
            "targets": setup.get("targets"),
            "rr": setup.get("rr"),
        },
        "lifecycle_id": item.get("lifecycle_id") or item.get("episode_id"),
        "t1_id": item.get("t1_id"),
        "lifecycle_stage": item.get("lifecycle_stage") or item.get("state"),
        "archetype": item.get("archetype"),
        "capital_risk_status": item.get("capital_risk_status"),
    }


def compact_parent_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Store run metadata plus a tiny 7-day traceability projection.

    Full per-symbol science evidence remains in the short-lived child stream.
    """
    payload = dict(snapshot)
    symbols = payload.pop("symbols", [])
    payload["readiness_records"] = [
        compact_readiness_record(item)
        for item in symbols
        if isinstance(item, dict) and not item.get("error")
    ]
    payload["_storage_contract"] = PARENT_STORAGE_CONTRACT
    return payload


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

    def request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Run an idempotent Supabase REST request with bounded retries.

        Canonical writes use deterministic conflict keys, so retrying a timed-out
        request cannot create a second evidence row. Exhaustion still raises and
        leaves the production caller fail-closed.
        """
        request = getattr(self.session, method.lower(), None)
        if request is None:
            raise ValueError(f"Unsupported Supabase request method: {method}")

        attempts = self.settings.max_retries + 1
        for attempt in range(attempts):
            try:
                response = request(url, **kwargs)
            except requests.RequestException as exc:
                if attempt + 1 >= attempts:
                    raise SupabaseStorageError(
                        f"Supabase {method.upper()} failed after {attempts} "
                        f"attempts: {exc}"
                    ) from exc
            else:
                if (
                    response.status_code not in RETRYABLE_SUPABASE_STATUS_CODES
                    or attempt + 1 >= attempts
                ):
                    return response

            delay = self.settings.retry_backoff_seconds * (2 ** attempt)
            if delay > 0:
                time.sleep(delay)

        raise AssertionError("Supabase retry loop exhausted without a result")

    def load_latest_snapshot(
        self,
        *,
        expected_identity: dict[str, Any] | None = None,
        require_strategy_context: bool = False,
        search_limit: int = 25,
    ) -> dict[str, Any] | None:
        filtered = expected_identity is not None or require_strategy_context
        limit = max(1, int(search_limit)) if filtered else 1
        response = self.request_with_retry(
            "get",
            f"{self.settings.url}/rest/v1/{self.settings.snapshot_table}",
            params={
                "select": "run_id,collected_at_utc,payload",
                "order": "collected_at_utc.desc",
                "limit": str(limit),
            },
            headers=self.headers,
            timeout=self.settings.timeout_seconds,
        )
        if response.status_code != 200:
            body = response.text[:500]
            raise SupabaseStorageError(
                "Supabase latest snapshot read failed: "
                f"HTTP {response.status_code}: {body}"
            )

        try:
            rows = response.json()
        except ValueError as exc:
            raise SupabaseStorageError(
                "Supabase latest snapshot read returned invalid JSON"
            ) from exc

        if not isinstance(rows, list) or not rows:
            return None

        for row in rows:
            if not isinstance(row, dict):
                continue

            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue

            if require_strategy_context:
                if not isinstance(payload.get("multi_strategy_summary"), dict):
                    continue
                if not isinstance(payload.get("microstructure_summary"), dict):
                    continue
                if not isinstance(payload.get("catalyst_summary"), dict):
                    continue

            if expected_identity is not None:
                actual_identity = payload.get("validation_identity")
                if not isinstance(actual_identity, dict):
                    continue
                for key in ("test_contract", "config_sha256", "run_source"):
                    expected = expected_identity.get(key)
                    if expected and actual_identity.get(key) != expected:
                        break
                else:
                    return self._hydrate_snapshot(row, payload)
                continue

            return self._hydrate_snapshot(row, payload)

        return None

    def _hydrate_snapshot(
        self,
        row: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = dict(payload)
        snapshot.setdefault("run_id", row.get("run_id"))
        snapshot.setdefault("collected_at_utc", row.get("collected_at_utc"))

        if isinstance(snapshot.get("symbols"), list):
            return snapshot

        run_id = str(snapshot.get("run_id") or "")
        if not run_id:
            raise SupabaseStorageError(
                "Compact snapshot parent is missing run_id"
            )

        response = self.request_with_retry(
            "get",
            f"{self.settings.url}/rest/v1/{self.settings.symbol_table}",
            params={
                "select": "symbol,payload",
                "run_id": f"eq.{run_id}",
                "order": "symbol.asc",
                "limit": "2000",
            },
            headers=self.headers,
            timeout=self.settings.timeout_seconds,
        )
        if response.status_code != 200:
            body = response.text[:500]
            raise SupabaseStorageError(
                "Supabase snapshot hydration failed: "
                f"HTTP {response.status_code}: {body}"
            )

        try:
            rows = response.json()
        except ValueError as exc:
            raise SupabaseStorageError(
                "Supabase snapshot hydration returned invalid JSON"
            ) from exc

        snapshot["symbols"] = [
            child.get("payload")
            for child in rows
            if isinstance(child, dict)
            and isinstance(child.get("payload"), dict)
        ]
        return snapshot

    def _upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
        if not rows:
            return
        response = self.request_with_retry(
            "post",
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
            "payload": compact_parent_snapshot(snapshot),
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

        signal_rows: list[dict[str, Any]] = []
        for item in valid_symbols:
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            setup = item.get("execution_setup", {})
            if not isinstance(setup, dict):
                setup = {}
            intel = item.get("intelligence", {})
            if not isinstance(intel, dict):
                intel = {}
            reference_price = item.get("last_price")
            if reference_price is None:
                continue
            signal_id = hashlib.sha256(
                f"{run_id}|{symbol}".encode("utf-8")
            ).hexdigest()[:32]
            signal_rows.append({
                "signal_id": signal_id,
                "run_id": run_id,
                "symbol": symbol,
                "detected_at_utc": snapshot.get("collected_at_utc"),
                "state": item.get("state"),
                "direction": setup.get("direction") or item.get("direction"),
                "trade_permission": bool(item.get("trade_permission", False)),
                "huge_rr_score": intel.get("huge_rr_score"),
                "confidence_estimate_pct": intel.get("confidence_estimate_pct"),
                "reward_risk": setup.get("rr"),
                "entry_price": setup.get("entry"),
                "stop_loss": setup.get("stop"),
                "take_profit": setup.get("target"),
                "reference_price": reference_price,
                "payload": compact_source_payload(item),
            })

        feature_rows = extract_feature_rows(snapshot)
        signal_id_by_symbol = {
            row["symbol"]: row["signal_id"]
            for row in signal_rows
        }
        readiness_rows: list[dict[str, Any]] = []
        for item in valid_symbols:
            symbol = str(item.get("symbol") or "")
            if not symbol:
                continue
            setup = item.get("execution_setup", {})
            if not isinstance(setup, dict):
                setup = {}
            readiness_rows.append({
                "run_id": run_id,
                "symbol": symbol,
                "observed_at_utc": snapshot.get("collected_at_utc"),
                "state": item.get("state"),
                "direction": setup.get("direction") or item.get("direction"),
                "trade_permission": bool(item.get("trade_permission", False)),
                "v7_trade_ready": bool(item.get("v7_trade_ready", False)),
                "reference_price": item.get("last_price"),
                "entry_price": setup.get("entry"),
                "stop_loss": setup.get("stop"),
                "take_profit": setup.get("target"),
                "reward_risk": setup.get("rr"),
                "lifecycle_id": item.get("lifecycle_id") or item.get("episode_id"),
                "t1_id": item.get("t1_id"),
                "lifecycle_stage": item.get("lifecycle_stage") or item.get("state"),
                "archetype": item.get("archetype"),
                "capital_risk_status": item.get("capital_risk_status"),
            })

        canonical_feature_rows: list[dict[str, Any]] = []
        for row in feature_rows:
            symbol = str(row.get("symbol") or "")
            signal_id = signal_id_by_symbol.get(symbol)
            if signal_id is None:
                continue
            canonical = dict(row)
            canonical["signal_id"] = signal_id
            canonical_feature_rows.append(canonical)

        self._upsert(self.settings.snapshot_table, parent, "run_id")
        self._upsert(self.settings.symbol_table, children, "run_id,symbol")
        self._upsert("alpha_hunter_signals", signal_rows, "signal_id")
        self._upsert(
            "alpha_hunter_signal_features",
            canonical_feature_rows,
            "signal_id",
        )
        self._upsert(
            self.settings.readiness_table,
            readiness_rows,
            "run_id,symbol",
        )
        return run_id
