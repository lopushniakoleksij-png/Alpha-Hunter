from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from alpha_hunter.scientific_validation import evaluate_hypothesis


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_observations(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError("observations JSON must contain a list")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Alpha Hunter scientific validation in read-only shadow mode."
    )
    parser.add_argument("--hypothesis", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--bootstrap-iterations", type=int, default=2000)
    parser.add_argument("--permutation-iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    result = evaluate_hypothesis(
        load_json(args.hypothesis),
        load_observations(args.observations),
        bootstrap_iterations=args.bootstrap_iterations,
        permutation_iterations=args.permutation_iterations,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))

    hard_failures = {
        "INVALID_HYPOTHESIS",
        "DATA_INTEGRITY_FAILURE",
        "SAFETY_BOUNDARY_VIOLATION",
        "INVALID_ANALYSIS_CONFIG",
    }
    return 2 if result.get("status") in hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
