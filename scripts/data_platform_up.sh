#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${INFRAGUARD_DB_CONTAINER:-infraguard-postgres}"
IMAGE="${INFRAGUARD_DB_IMAGE:-docker.io/library/postgres:16}"
DB_USER="${POSTGRES_USER:-infraguard}"
DB_PASSWORD="${POSTGRES_PASSWORD:-infraguard}"
DB_NAME="${POSTGRES_DB:-infraguard}"
DB_PORT="${INFRAGUARD_DB_PORT:-55432}"
PORT_SEARCH_MAX="${INFRAGUARD_DB_PORT_SEARCH_MAX:-25}"
PUBLISH_PORT="${INFRAGUARD_DB_PUBLISH_PORT:-1}"
VOLUME_NAME="${INFRAGUARD_DB_VOLUME:-infraguard_postgres_data}"

if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  if [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}")" = "true" ]; then
    echo "PostgreSQL container already running: ${CONTAINER_NAME}"
  else
    echo "Starting existing PostgreSQL container: ${CONTAINER_NAME}"
    docker start "${CONTAINER_NAME}" >/dev/null
  fi
else
  if [ "${PUBLISH_PORT}" = "1" ]; then
    HOST_PORT="${DB_PORT}"
    ATTEMPTS="${PORT_SEARCH_MAX}"
  else
    HOST_PORT=""
    ATTEMPTS=1
  fi

  echo "Creating PostgreSQL container: ${CONTAINER_NAME}"
  while [ "${ATTEMPTS}" -gt 0 ]; do
    # Defensive cleanup for daemon states where name conflicts appear but lookup is stale.
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

    create_err_file="$(mktemp)"
    create_cmd=(
      docker create
      --name "${CONTAINER_NAME}"
      -e "POSTGRES_USER=${DB_USER}"
      -e "POSTGRES_PASSWORD=${DB_PASSWORD}"
      -e "POSTGRES_DB=${DB_NAME}"
      -v "${VOLUME_NAME}:/var/lib/postgresql/data"
    )
    if [ "${PUBLISH_PORT}" = "1" ]; then
      create_cmd+=(-p "${HOST_PORT}:5432")
    fi
    create_cmd+=("${IMAGE}")

    if "${create_cmd[@]}" >/dev/null 2>"${create_err_file}"; then
      rm -f "${create_err_file}"
    else
      if [ "${PUBLISH_PORT}" = "1" ] && grep -qi "port is already allocated" "${create_err_file}"; then
        HOST_PORT="$((HOST_PORT + 1))"
        ATTEMPTS="$((ATTEMPTS - 1))"
        rm -f "${create_err_file}"
        continue
      fi

      cat "${create_err_file}" >&2
      rm -f "${create_err_file}"
      exit 1
    fi

    start_err_file="$(mktemp)"
    if docker start "${CONTAINER_NAME}" >/dev/null 2>"${start_err_file}"; then
      rm -f "${start_err_file}"

      visible="0"
      for _ in 1 2 3 4 5; do
        if docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
          visible="1"
          break
        fi
        sleep 1
      done

      if [ "${visible}" = "1" ]; then
        break
      fi

      if [ "${PUBLISH_PORT}" = "1" ]; then
        echo "Container '${CONTAINER_NAME}' not visible after start; retrying with next port..." >&2
      else
        echo "Container '${CONTAINER_NAME}' not visible after start." >&2
      fi
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

      if [ "${PUBLISH_PORT}" != "1" ]; then
        exit 1
      fi

      HOST_PORT="$((HOST_PORT + 1))"
      ATTEMPTS="$((ATTEMPTS - 1))"
      continue
    fi

    if [ "${PUBLISH_PORT}" = "1" ] && grep -qi "port is already allocated" "${start_err_file}"; then
      HOST_PORT="$((HOST_PORT + 1))"
      ATTEMPTS="$((ATTEMPTS - 1))"
      rm -f "${start_err_file}"
      docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
      continue
    fi

    cat "${start_err_file}" >&2
    rm -f "${start_err_file}"
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    exit 1
  done

  if [ "${ATTEMPTS}" -eq 0 ] && [ "${PUBLISH_PORT}" = "1" ]; then
    echo "No available host port found in range ${DB_PORT}..$((DB_PORT + PORT_SEARCH_MAX - 1))" >&2
    exit 1
  fi

  if [ "${PUBLISH_PORT}" = "1" ] && [ "${HOST_PORT}" != "${DB_PORT}" ]; then
    echo "Requested host port ${DB_PORT} is unavailable; using ${HOST_PORT}."
  fi
fi

"${ROOT_DIR}/scripts/wait_for_postgres.sh"
docker ps --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
