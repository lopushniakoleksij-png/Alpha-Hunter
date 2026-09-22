from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from .storage import SupabaseConfig


ENGINE_VERSION = "realtime-test-engine-v0.1"
MAX_LIVE_SCAN_AGE_SECONDS = 5400.0


@dataclass(frozen=True)
class TestEngineReport:
    row: dict[str, Any]

    @property
    def verdict(self) -> str:
        return str(self.row.get("verdict") or "UNKNOWN")


class RealtimeTestEngine:
    """Evaluate the sealed Alpha Hunter profitability test from production evidence.

    This engine is read-only with respect to market/exchange data. It reads only
    canonical Supabase evidence already produced by the production scanner and
    persists one immutable test-engine status row. It never places, amends, or
    cancels an order and cannot grant trade permission.
    """

    def __init__(
        self,
        settings: SupabaseConfig,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.headers = {
            "apikey": settings.key,
            "Authorization": f"Bearer {settings.key}",
            "Content-Type": "application/json",
        }

    def _get_one(
        self,
        relation: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        query = {"select": "*", "limit": "1"}
        if params:
            query.update(params)
        response = self.session.get(
            f"{self.settings.url}/rest/v1/{relation}",
            params=query,
            headers=self.headers,
            timeout=self.settings.timeout_seconds,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Test engine read failed for {relation}: "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        row = payload[0]
        return row if isinstance(row, dict) else None

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int(value: Any) -> int:
        try:
            if value is None or value == "":
                return 0
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _bool(value: Any) -> bool:
        return value is True or str(value).lower() == "true"

    def evaluate(self) -> TestEngineReport:
        realtime = self._get_one(
            "alpha_hunter_realtime_profitability_monitor_v01",
            params={"order": "real_test_requested_at_utc.desc"},
        )
        if realtime is None:
            raise RuntimeError("Real-time profitability monitor has no test spec")

        spec_id = str(realtime.get("spec_id") or "")
        validation = self._get_one(
            "alpha_hunter_profitability_validation_status_v01",
            params={
                "spec_id": f"eq.{spec_id}",
                "order": "started_at_utc.desc.nullslast",
            },
        )
        if validation is None:
            raise RuntimeError(
                f"Profitability validation status missing for spec {spec_id}"
            )

        forward = self._get_one(
            "alpha_hunter_strategy_forward_status_v01",
        ) or {}
        opportunity = self._get_one(
            "alpha_hunter_strategy_opportunity_status_v01",
        ) or {}
        cost = self._get_one(
            "alpha_hunter_execution_cost_floor_status_v01",
            params={"cost_scope": "eq.ALL"},
        ) or {}

        evaluated_at = datetime.now(timezone.utc).isoformat()
        scan_age = self._float(realtime.get("latest_live_scan_age_seconds"))
        latest_commit = str(realtime.get("latest_live_git_commit") or "")
        latest_config = str(realtime.get("latest_live_config_sha256") or "")
        previous_source = str(realtime.get("previous_snapshot_source") or "NONE")
        catalyst_version = str(realtime.get("catalyst_version") or "")
        strategy_count = self._int(realtime.get("configured_strategy_count"))

        operational_blockers: list[str] = []
        economic_blockers: list[str] = []

        if scan_age is None:
            operational_blockers.append("LIVE_SCAN_AGE_UNKNOWN")
        elif scan_age > MAX_LIVE_SCAN_AGE_SECONDS:
            operational_blockers.append("LIVE_SCAN_STALE")

        if not latest_commit:
            operational_blockers.append("LIVE_BUILD_IDENTITY_MISSING")
        if not latest_config:
            operational_blockers.append("LIVE_CONFIG_IDENTITY_MISSING")
        if strategy_count != 10:
            operational_blockers.append("S1_S10_COVERAGE_NOT_10")
        if previous_source in {"", "NONE"}:
            operational_blockers.append("PREVIOUS_CANONICAL_CONTEXT_MISSING")
        if catalyst_version != "0.2":
            operational_blockers.append("CATALYST_EVIDENCE_NOT_V02")

        test_activated = self._bool(validation.get("test_activated"))
        if not test_activated:
            operational_blockers.append("SEALED_TEST_BASELINE_NOT_ACTIVATED")

        drift_ok = self._bool(validation.get("identity_drift_gate_met"))
        if not drift_ok:
            operational_blockers.append("BUILD_OR_CONFIG_DRIFT")

        cost_model_validated = self._bool(validation.get("cost_model_validated"))
        realistic_net_allowed = self._bool(
            validation.get("realistic_net_r_claim_permitted")
        )
        if not cost_model_validated:
            economic_blockers.append("VALIDATED_EXECUTION_COST_MODEL_MISSING")
        if not realistic_net_allowed:
            economic_blockers.append("REALISTIC_NET_R_CLAIM_NOT_PERMITTED")

        operational_status = (
            "PASS"
            if not operational_blockers
            else "BLOCKED"
        )
        blockers = operational_blockers + economic_blockers

        profitability_status = str(
            validation.get("profitability_test_status")
            or "UNKNOWN"
        )

        if profitability_status == "POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_PAPER_TEST":
            verdict = "PAPER_EDGE_DEMONSTRATED"
        elif profitability_status == "NO_POSITIVE_NET_EDGE_DEMONSTRATED":
            verdict = "NO_POSITIVE_PAPER_EDGE_DEMONSTRATED"
        elif profitability_status.startswith("RUNNING_"):
            verdict = "TEST_RUNNING"
        elif profitability_status == "BLOCKED_NO_VALIDATED_REALISTIC_COST_MODEL":
            verdict = "TEST_BLOCKED_COST_MODEL"
        else:
            verdict = "NOT_PROVEN"

        row = {
            "test_engine_run_id": hashlib.sha256(
                (
                    f"{ENGINE_VERSION}|{spec_id}|{evaluated_at}|"
                    f"{realtime.get('latest_live_run_id') or ''}"
                ).encode("utf-8")
            ).hexdigest()[:32],
            "evaluated_at_utc": evaluated_at,
            "engine_version": ENGINE_VERSION,
            "spec_id": spec_id or None,
            "real_test_requested_at_utc": realtime.get(
                "real_test_requested_at_utc"
            ),
            "real_counted_baseline_started_at_utc": realtime.get(
                "real_counted_baseline_started_at_utc"
            ),
            "latest_live_run_id": realtime.get("latest_live_run_id"),
            "latest_live_scan_at_utc": realtime.get("latest_live_scan_at_utc"),
            "latest_live_scan_age_seconds": scan_age,
            "latest_live_git_commit": latest_commit or None,
            "latest_live_config_sha256": latest_config or None,
            "previous_snapshot_source": previous_source,
            "catalyst_version": catalyst_version or None,
            "configured_strategy_count": strategy_count,
            "real_scans_since_registration": self._int(
                realtime.get("real_scans_since_registration")
            ),
            "real_strategy_observations_since_registration": self._int(
                realtime.get("real_strategy_observations_since_registration")
            ),
            "real_shadow_candidates_since_registration": self._int(
                realtime.get("real_shadow_candidates_since_registration")
            ),
            "real_24h_forward_outcomes_since_registration": self._int(
                realtime.get("real_24h_forward_outcomes_since_registration")
            ),
            "completed_paper_trades": self._int(
                validation.get("completed_paper_trades")
            ),
            "test_days_elapsed": self._float(
                validation.get("test_days_elapsed")
            ) or 0.0,
            "minimum_test_days": self._int(
                validation.get("minimum_test_days")
            ),
            "minimum_completed_paper_trades": self._int(
                validation.get("minimum_completed_paper_trades")
            ),
            "avg_gross_r": self._float(validation.get("avg_gross_r")),
            "gross_r_lower_95": self._float(
                validation.get("gross_r_lower_95")
            ),
            "avg_floor_adjusted_r": self._float(
                validation.get("avg_floor_adjusted_r")
            ),
            "floor_adjusted_r_lower_95": self._float(
                validation.get("floor_adjusted_r_lower_95")
            ),
            "floor_profit_factor": self._float(
                validation.get("floor_profit_factor")
            ),
            "avg_modeled_net_r": self._float(
                validation.get("avg_modeled_net_r")
            ),
            "modeled_net_r_lower_95": self._float(
                validation.get("modeled_net_r_lower_95")
            ),
            "modeled_net_profit_factor": self._float(
                validation.get("modeled_net_profit_factor")
            ),
            "cost_model_validated": cost_model_validated,
            "realistic_net_r_claim_permitted": realistic_net_allowed,
            "operational_status": operational_status,
            "profitability_status": profitability_status,
            "verdict": verdict,
            "blockers": blockers,
            "source_status": {
                "realtime_test_status": realtime.get("realtime_test_status"),
                "forward_outcomes": forward.get("forward_outcomes"),
                "strategy_episodes": forward.get("strategy_episodes"),
                "opportunity_path_rows": opportunity.get(
                    "opportunity_path_rows"
                ),
                "operational_blockers": operational_blockers,
                "cost_scientific_status": cost.get("scientific_status"),
                "cost_next_gate": cost.get("next_gate"),
            },
            "economics": {
                "economic_blockers": economic_blockers,
                "duration_gate_met": self._bool(
                    validation.get("duration_gate_met")
                ),
                "sample_gate_met": self._bool(
                    validation.get("sample_gate_met")
                ),
                "conservative_floor_edge_gate_met": self._bool(
                    validation.get("conservative_floor_edge_gate_met")
                ),
                "modeled_net_edge_gate_met": self._bool(
                    validation.get("modeled_net_edge_gate_met")
                ),
            },
            "real_time": True,
            "forward_only": True,
            "historical_replay_counted": False,
            "backtest_counted": False,
            "paper_only": True,
            "live_money_claim_permitted": False,
            "trade_permission": False,
            "threshold_change_permitted": False,
            "production_promotion_permitted": False,
            "order_path": "NONE",
        }
        return TestEngineReport(row=row)

    def persist(self, report: TestEngineReport) -> None:
        response = self.session.post(
            f"{self.settings.url}/rest/v1/alpha_hunter_test_engine_runs_v01",
            params={"on_conflict": "test_engine_run_id"},
            headers={
                **self.headers,
                "Prefer": "resolution=ignore-duplicates,return=minimal",
            },
            data=json.dumps(report.row, separators=(",", ":")),
            timeout=self.settings.timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                "Test engine persistence failed: "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )


def format_report(report: TestEngineReport) -> str:
    row = report.row
    blockers = row.get("blockers") or []
    blocker_text = ",".join(str(item) for item in blockers) if blockers else "NONE"
    return (
        "ALPHA HUNTER REAL-TIME TEST ENGINE\n"
        f"evaluated_at_utc={row.get('evaluated_at_utc')}\n"
        f"spec_id={row.get('spec_id')}\n"
        f"operational_status={row.get('operational_status')}\n"
        f"profitability_status={row.get('profitability_status')}\n"
        f"verdict={row.get('verdict')}\n"
        f"latest_live_scan_at_utc={row.get('latest_live_scan_at_utc')}\n"
        f"real_scans={row.get('real_scans_since_registration')} "
        f"observations={row.get('real_strategy_observations_since_registration')} "
        f"candidates={row.get('real_shadow_candidates_since_registration')} "
        f"outcomes_24h={row.get('real_24h_forward_outcomes_since_registration')}\n"
        f"paper_trades={row.get('completed_paper_trades')}/"
        f"{row.get('minimum_completed_paper_trades')} "
        f"days={row.get('test_days_elapsed'):.4f}/"
        f"{row.get('minimum_test_days')}\n"
        f"blockers={blocker_text}\n"
        "paper_only=true trade_permission=false order_path=NONE"
    )
