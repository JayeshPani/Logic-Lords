#!/usr/bin/env python3
"""Step-3 integration assertions for AI pipeline contracts."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import jsonschema
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPTS_DIR))
sys.path.append(str(ROOT / "services/lstm-forecast-service/src"))
sys.path.append(str(ROOT / "services/anomaly-detection-service/src"))
sys.path.append(str(ROOT / "services/fuzzy-inference-service/src"))
sys.path.append(str(ROOT / "services/health-score-service/src"))

from anomaly_detection.config import Settings as AnomalySettings
from anomaly_detection.engine import AnomalyDetector
from dataset_adapters import detect_dataset_kind, load_canonical_records, records_to_dicts
from fuzzy_inference.config import Settings as FuzzySettings
from fuzzy_inference.engine import MamdaniFuzzyEngine
from health_score.engine import OutputComposer
from lstm_forecast.config import Settings as ForecastSettings
from lstm_forecast.predictor import PredictorFactory, SurrogateLSTMPredictor
from lstm_forecast.preprocessing import SensorNormalizer, SequenceBuilder


ML_SCHEMAS = {
    "forecast_response": "contracts/ml/forecast.response.schema.json",
    "anomaly_response": "contracts/ml/anomaly.detect.response.schema.json",
    "fuzzy_response": "contracts/ml/fuzzy.infer.response.schema.json",
    "health_response": "contracts/ml/health.score.response.schema.json",
}

EVENT_SCHEMAS = {
    "asset_failure_predicted_event": "contracts/events/asset.failure.predicted.schema.json",
    "asset_anomaly_detected_event": "contracts/events/asset.anomaly.detected.schema.json",
    "asset_risk_computed_event": "contracts/events/asset.risk.computed.schema.json",
}


@dataclass(frozen=True)
class ValidationResult:
    name: str
    valid: bool
    error: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AI pipeline payloads against contracts")
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=[
            "data-platform/ml/datasets/bridge_digital_twin_dataset.csv",
            "data-platform/ml/datasets/bridge_dataset.csv",
            "data-platform/ml/datasets/merged_dataset_BearingTest_2.csv",
        ],
    )
    parser.add_argument("--limit-per-dataset", type=int, default=500)
    parser.add_argument("--asset-prefix", default="asset_contract")
    parser.add_argument(
        "--report-out",
        default="data-platform/ml/reports/ai_contract_validation_report.json",
    )
    parser.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="Exit with non-zero status when any validation fails",
    )
    return parser.parse_args(argv)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_optional_context(latest: dict[str, Any]) -> tuple[float, float]:
    traffic_density = _clamp(float(latest.get("traffic_density", 0.0) or 0.0))
    rainfall_raw = float(latest.get("rainfall_intensity", 0.0) or 0.0)
    rainfall_intensity = _clamp(rainfall_raw / 100.0)
    return traffic_density, rainfall_intensity


def _event_envelope(event_type: str, data: dict[str, Any], trace_id: str) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_version": "v1",
        "occurred_at": _now_iso(),
        "produced_by": "scripts/validate-ai-contracts",
        "trace_id": trace_id,
        "data": data,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _to_jsonable(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=_json_default))


def _absolutize_refs(schema: Any, schema_path: Path) -> Any:
    """Convert local relative $ref values to absolute file URIs."""

    if isinstance(schema, dict):
        updated: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "$ref" and isinstance(value, str):
                if value.startswith("#") or "://" in value:
                    updated[key] = value
                else:
                    updated[key] = (schema_path.parent / value).resolve().as_uri()
            else:
                updated[key] = _absolutize_refs(value, schema_path)
        return updated

    if isinstance(schema, list):
        return [_absolutize_refs(item, schema_path) for item in schema]

    return schema


def _build_schema_store() -> dict[str, dict]:
    store: dict[str, dict] = {}
    for schema_path in (ROOT / "contracts").rglob("*.json"):
        schema = _absolutize_refs(json.loads(schema_path.read_text()), schema_path.resolve())
        store[schema_path.resolve().as_uri()] = schema
        if "$id" in schema and isinstance(schema["$id"], str):
            store[schema["$id"]] = schema
    return store


def _validate_against_schema(
    instance: dict[str, Any],
    schema_path: Path,
    schema_store: dict[str, dict],
    schema_registry: Registry,
) -> ValidationResult:
    schema_uri = schema_path.resolve().as_uri()
    schema = schema_store[schema_uri]
    validator = jsonschema.Draft202012Validator(
        schema=schema,
        registry=schema_registry,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return ValidationResult(name=schema_path.name, valid=True)

    first = errors[0]
    path = ".".join(str(part) for part in first.absolute_path) or "<root>"
    return ValidationResult(
        name=schema_path.name,
        valid=False,
        error=f"{path}: {first.message}",
    )


def _build_pipeline_payloads(asset_id: str, history: list[dict[str, Any]]) -> dict[str, dict]:
    forecast_settings = ForecastSettings()
    normalizer = SensorNormalizer(forecast_settings)
    sequence_builder = SequenceBuilder(forecast_settings, normalizer)
    try:
        predictor = PredictorFactory.create(forecast_settings)
    except Exception:
        predictor = SurrogateLSTMPredictor()

    anomaly_detector = AnomalyDetector(AnomalySettings())
    fuzzy_engine = MamdaniFuzzyEngine(FuzzySettings())
    output_composer = OutputComposer()

    sequence = sequence_builder.build_last_48h_sequence(history)
    forecast_result = predictor.predict(sequence)

    latest = history[-1]
    latest_norm = normalizer.normalize_record(latest)
    baseline_norm = [normalizer.normalize_record(point) for point in history[:-1]]
    anomaly_result = anomaly_detector.detect(current=latest_norm, baseline_window=baseline_norm)

    traffic_density, rainfall_intensity = _normalize_optional_context(latest)
    fuzzy_result = fuzzy_engine.evaluate(
        {
            "strain": latest_norm["strain"],
            "vibration": latest_norm["vibration"],
            "temperature": latest_norm["temperature"],
            "rainfall_intensity": rainfall_intensity,
            "traffic_density": traffic_density,
            "failure_probability": forecast_result.failure_probability,
            "anomaly_score": anomaly_result.anomaly_score,
        }
    )

    composed = output_composer.compose(fuzzy_result.final_risk_score)
    timestamp = _now_iso()

    forecast_response = {
        "data": {
            "asset_id": asset_id,
            "generated_at": timestamp,
            "horizon_hours": forecast_settings.horizon_hours,
            "failure_probability_72h": forecast_result.failure_probability,
            "confidence": forecast_result.confidence,
            "time_steps_used": len(sequence),
            "features_used": sequence_builder.FEATURES,
            "normalized": True,
            "model": {
                "name": forecast_result.model_name,
                "version": forecast_result.model_version,
                "mode": forecast_result.model_mode,
                "architecture": forecast_result.architecture,
            },
        }
    }

    anomaly_response = {
        "data": {
            "asset_id": asset_id,
            "anomaly_score": anomaly_result.anomaly_score,
            "anomaly_flag": anomaly_result.anomaly_flag,
            "threshold": anomaly_result.threshold,
            "detector_mode": anomaly_result.detector_mode,
            "evaluated_at": timestamp,
        }
    }

    fuzzy_response = {
        "data": {
            "asset_id": asset_id,
            "evaluated_at": timestamp,
            "final_risk_score": fuzzy_result.final_risk_score,
            "risk_level": fuzzy_result.risk_level,
            "rule_activations": fuzzy_result.rule_activations,
            "method": "mamdani_centroid",
        }
    }

    health_response = {
        "health_score": composed.health_score,
        "failure_probability_72h": forecast_result.failure_probability,
        "anomaly_flag": anomaly_result.anomaly_flag,
        "risk_level": composed.risk_level,
        "timestamp": timestamp,
    }

    trace_id = uuid4().hex
    failure_event = _event_envelope(
        "asset.failure.predicted",
        {
            "asset_id": asset_id,
            "generated_at": timestamp,
            "horizon_hours": forecast_settings.horizon_hours,
            "failure_probability_72h": forecast_result.failure_probability,
            "confidence": forecast_result.confidence,
        },
        trace_id=trace_id,
    )
    anomaly_event = _event_envelope(
        "asset.anomaly.detected",
        {
            "asset_id": asset_id,
            "evaluated_at": timestamp,
            "anomaly_score": anomaly_result.anomaly_score,
            "anomaly_flag": anomaly_result.anomaly_flag,
            "detector_mode": anomaly_result.detector_mode,
        },
        trace_id=trace_id,
    )
    risk_event = _event_envelope(
        "asset.risk.computed",
        {
            "asset_id": asset_id,
            "evaluated_at": timestamp,
            "health_score": composed.health_score,
            "risk_level": composed.risk_level,
            "failure_probability_72h": forecast_result.failure_probability,
            "anomaly_flag": anomaly_result.anomaly_flag,
        },
        trace_id=trace_id,
    )

    return {
        "forecast_response": forecast_response,
        "anomaly_response": anomaly_response,
        "fuzzy_response": fuzzy_response,
        "health_response": health_response,
        "asset_failure_predicted_event": failure_event,
        "asset_anomaly_detected_event": anomaly_event,
        "asset_risk_computed_event": risk_event,
    }


def run_suite(args: argparse.Namespace) -> dict:
    schema_store = _build_schema_store()
    registry = Registry()
    for uri, schema in schema_store.items():
        if not isinstance(uri, str) or "://" not in uri:
            continue
        registry = registry.with_resource(uri, Resource.from_contents(schema))
    report_out = ROOT / args.report_out
    cases = []

    for idx, dataset in enumerate(args.datasets):
        dataset_path = ROOT / dataset if not Path(dataset).is_absolute() else Path(dataset)
        kind = detect_dataset_kind(dataset_path)
        records, summary = load_canonical_records(
            dataset_path=dataset_path,
            dataset_kind=kind,
            limit=args.limit_per_dataset,
        )
        history = records_to_dicts(records)
        if len(history) < 16:
            raise RuntimeError(f"Dataset has insufficient rows for pipeline: {dataset_path}")

        asset_id = f"{args.asset_prefix}_{kind}_{idx+1}"
        payloads = _build_pipeline_payloads(asset_id=asset_id, history=history)

        validations: list[ValidationResult] = []
        for key, relative_path in {**ML_SCHEMAS, **EVENT_SCHEMAS}.items():
            schema_path = ROOT / relative_path
            result = _validate_against_schema(
                instance=_to_jsonable(payloads[key]),
                schema_path=schema_path,
                schema_store=schema_store,
                schema_registry=registry,
            )
            validations.append(result)

        cases.append(
            {
                "dataset_path": str(dataset_path),
                "dataset_kind": kind,
                "rows_loaded": summary.rows_loaded,
                "asset_id": asset_id,
                "validations": [
                    {
                        "schema": result.name,
                        "valid": result.valid,
                        "error": result.error,
                    }
                    for result in validations
                ],
                "sample_outputs": {
                    "forecast_mode": payloads["forecast_response"]["data"]["model"]["mode"],
                    "failure_probability_72h": payloads["forecast_response"]["data"]["failure_probability_72h"],
                    "anomaly_score": payloads["anomaly_response"]["data"]["anomaly_score"],
                    "health_score": payloads["health_response"]["health_score"],
                    "risk_level": payloads["health_response"]["risk_level"],
                },
            }
        )

    invalid = [
        {
            "dataset_path": case["dataset_path"],
            "schema": validation["schema"],
            "error": validation["error"],
        }
        for case in cases
        for validation in case["validations"]
        if not validation["valid"]
    ]

    report = {
        "generated_at": _now_iso(),
        "summary": {
            "cases_total": len(cases),
            "checks_per_case": len(ML_SCHEMAS) + len(EVENT_SCHEMAS),
            "invalid_count": len(invalid),
            "all_valid": len(invalid) == 0,
            "datasets": [case["dataset_path"] for case in cases],
        },
        "invalid": invalid,
        "cases": cases,
    }

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, indent=2))
    report["report_out"] = str(report_out)
    return report


def main() -> None:
    args = parse_args()
    report = run_suite(args)
    print(json.dumps(report, indent=2))

    if args.fail_on_invalid and not report["summary"]["all_valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
