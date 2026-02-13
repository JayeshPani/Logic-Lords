#!/usr/bin/env python3
"""Quick validation for local dataset adapters."""

from __future__ import annotations

import argparse
import json

from dataset_adapters import load_canonical_records, records_to_dicts


REQUIRED_FIELDS = {
    "strain_value",
    "vibration_rms",
    "temperature",
    "humidity",
    "traffic_density",
    "rainfall_intensity",
    "timestamp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical mapping for a dataset")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--kind", default="auto", choices=["auto", "bridge", "digital_twin", "bearing"])
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records, summary = load_canonical_records(args.dataset, args.kind, args.limit)
    rows = records_to_dicts(records)

    if not rows:
        raise SystemExit("No rows loaded")

    keys = set(rows[0].keys())
    missing = REQUIRED_FIELDS - keys
    if missing:
        raise SystemExit(f"Missing required canonical fields: {sorted(missing)}")

    humidity_ok = all(0 <= float(row["humidity"]) <= 100 for row in rows)
    if not humidity_ok:
        raise SystemExit("Humidity values out of range [0,100]")

    print(
        json.dumps(
            {
                "dataset": summary.dataset_path,
                "kind": summary.dataset_kind,
                "rows_checked": len(rows),
                "canonical_fields": sorted(keys),
                "status": "ok",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
