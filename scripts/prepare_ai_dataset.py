#!/usr/bin/env python3
"""Prepare local datasets into canonical AI JSONL format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dataset_adapters import load_canonical_records, records_to_dicts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare dataset for InfraGuard AI modules")
    parser.add_argument("--dataset", required=True, help="Path to dataset CSV file")
    parser.add_argument(
        "--kind",
        default="auto",
        choices=["auto", "bridge", "digital_twin", "bearing"],
        help="Dataset kind",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows to load")
    parser.add_argument(
        "--output",
        default="data-platform/ml/datasets/prepared_canonical.jsonl",
        help="Output JSONL path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    records, summary = load_canonical_records(
        dataset_path=args.dataset,
        dataset_kind=args.kind,
        limit=args.limit,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as fh:
        for row in records_to_dicts(records):
            fh.write(json.dumps(row) + "\n")

    print(
        json.dumps(
            {
                "dataset_path": summary.dataset_path,
                "dataset_kind": summary.dataset_kind,
                "rows_loaded": summary.rows_loaded,
                "started_at": summary.started_at,
                "ended_at": summary.ended_at,
                "output": str(output_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
