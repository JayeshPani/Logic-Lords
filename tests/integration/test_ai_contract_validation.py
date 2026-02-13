"""Integration test for step-3 AI contract assertions."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "scripts"))

from validate_ai_contracts import run_suite  # noqa: E402


def test_ai_contract_validation_suite(tmp_path: Path) -> None:
    report_out = tmp_path / "ai_contract_validation_report.json"
    args = argparse.Namespace(
        datasets=[
            "data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
            "data-platform/ml/datasets/bridge_dataset.csv",
            "data-platform/ml/datasets/merged_dataset_BearingTest_2.csv",
        ],
        limit_per_dataset=200,
        asset_prefix="test_contract",
        report_out=str(report_out),
        fail_on_invalid=False,
    )

    report = run_suite(args)
    assert report["summary"]["cases_total"] == 3
    assert report["summary"]["all_valid"] is True
    assert report["summary"]["invalid_count"] == 0
    assert Path(report["report_out"]).exists()
