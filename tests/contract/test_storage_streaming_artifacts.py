"""Contract-level checks for Module 4 storage/streaming artifacts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_postgres_compose_service_defined() -> None:
    compose = (ROOT / "infra/docker/docker-compose.local.yml").read_text()
    assert "postgres:" in compose
    assert "docker.io/library/postgres:16" in compose


def test_storage_runtime_migration_exists() -> None:
    path = ROOT / "data-platform/storage/migrations/001_storage_runtime.sql"
    text = path.read_text()
    assert "schema_migrations" in text


def test_streaming_runtime_migration_contains_outbox_functions() -> None:
    path = ROOT / "data-platform/streaming/migrations/001_outbox_runtime.sql"
    text = path.read_text()
    assert "notify_event_outbox_insert" in text
    assert "dequeue_outbox_events" in text
    assert "mark_outbox_event_failed" in text
    assert "outbox_status_metrics" in text


def test_module4_scripts_exist() -> None:
    expected = [
        "scripts/data_platform_up.sh",
        "scripts/data_platform_down.sh",
        "scripts/storage_psql.sh",
        "scripts/storage_migrate.sh",
        "scripts/storage_seed_dev.sh",
        "scripts/storage_status.sh",
        "scripts/wait_for_postgres.sh",
        "scripts/streaming_enqueue_event.sh",
        "scripts/streaming_dispatch_outbox.sh",
    ]
    for rel in expected:
        path = ROOT / rel
        assert path.exists(), rel
