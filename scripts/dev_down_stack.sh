#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${INFRA_GUARD_LOG_DIR:-/tmp/infraguard}"

stop_pidfile() {
  local name="$1"
  local pidfile="${LOG_DIR}/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "[skip] ${name} (no pidfile)"
    return 0
  fi

  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    echo "[skip] ${name} (empty pidfile)"
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[..] stopping ${name} (pid ${pid})"
    kill "$pid" >/dev/null 2>&1 || true
  else
    echo "[skip] ${name} (pid ${pid} not running)"
  fi
}

stop_pidfile "api-gateway"
stop_pidfile "sensor-ingestion"
stop_pidfile "orchestration-service"
stop_pidfile "notification-service"
stop_pidfile "report-generation"
stop_pidfile "blockchain-verification"

echo "[ok] done"

