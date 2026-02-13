"""Integration checks for Module 4 storage + streaming runtime behavior."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _docker_ready() -> bool:
    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        return False
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "info"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def _run(cmd: list[str], env: dict[str, str]) -> str:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        command = shlex.join(cmd)
        raise AssertionError(
            f"Command failed ({proc.returncode}): {command}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def _scalar(sql: str, env: dict[str, str]) -> str:
    out = _run(["bash", "scripts/storage_psql.sh", "-tA", "-c", sql], env)
    return out.strip().splitlines()[-1].strip()


def test_storage_streaming_runtime_end_to_end() -> None:
    if not _docker_ready():
        pytest.skip("Docker daemon is unavailable; skipping Module 4 runtime integration test.")

    suffix = uuid.uuid4().hex[:8]
    env = os.environ.copy()
    env.update(
        {
            "INFRAGUARD_DB_CONTAINER": f"infraguard-postgres-it-{suffix}",
            "INFRAGUARD_DB_VOLUME": f"infraguard_postgres_data_it_{suffix}",
            "INFRAGUARD_DB_PORT": "55432",
            "INFRAGUARD_DB_PORT_SEARCH_MAX": "50",
            "INFRAGUARD_DB_PUBLISH_PORT": "0",
            "POSTGRES_USER": "infraguard",
            "POSTGRES_PASSWORD": "infraguard",
            "POSTGRES_DB": "infraguard",
            "MAX_WAIT_SECONDS": "120",
        }
    )
    down_env = env.copy()
    down_env["INFRAGUARD_DB_REMOVE_VOLUME"] = "1"

    try:
        _run(["bash", "scripts/data_platform_up.sh"], env)
        _run(["bash", "scripts/storage_migrate.sh"], env)

        pending_before = int(_scalar("SELECT COUNT(*) FROM event_outbox WHERE status = 'pending';", env))
        _run(["bash", "scripts/streaming_enqueue_event.sh"], env)
        pending_after_enqueue = int(_scalar("SELECT COUNT(*) FROM event_outbox WHERE status = 'pending';", env))
        assert pending_after_enqueue >= pending_before + 1

        dispatch_env = env.copy()
        dispatch_env["BATCH_SIZE"] = "50"
        _run(["bash", "scripts/streaming_dispatch_outbox.sh"], dispatch_env)

        pending_after_dispatch = int(_scalar("SELECT COUNT(*) FROM event_outbox WHERE status = 'pending';", env))
        published_after_dispatch = int(_scalar("SELECT COUNT(*) FROM event_outbox WHERE status = 'published';", env))
        assert pending_after_dispatch <= pending_after_enqueue - 1
        assert published_after_dispatch >= 1

        status_metrics_rows = int(_scalar("SELECT COUNT(*) FROM outbox_status_metrics();", env))
        assert status_metrics_rows >= 1

        _run(["bash", "scripts/streaming_enqueue_event.sh"], env)
        event_id = int(_scalar("SELECT MAX(id) FROM event_outbox;", env))
        _run(
            [
                "bash",
                "scripts/storage_psql.sh",
                "-c",
                f"SELECT mark_outbox_event_failed({event_id}, 5);",
            ],
            env,
        )

        failed_status = _scalar(f"SELECT status FROM event_outbox WHERE id = {event_id};", env)
        retry_count = int(_scalar(f"SELECT retry_count FROM event_outbox WHERE id = {event_id};", env))
        assert failed_status == "failed"
        assert retry_count >= 1
    finally:
        subprocess.run(
            ["bash", "scripts/data_platform_down.sh"],
            cwd=ROOT,
            env=down_env,
            capture_output=True,
            text=True,
            check=False,
        )
