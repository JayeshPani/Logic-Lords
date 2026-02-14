# Sensor Ingestion Service

## Purpose
Receive telemetry from IoT gateways/Firebase and normalize into canonical schema.

## Responsibilities
- Pull latest and recent telemetry windows from Firebase Realtime Database
- Compute live operational metrics from DHT11 + accelerometer streams
- Expose normalized telemetry for API gateway and dashboard consumption
- Optional ingest endpoint that writes payloads into Firebase (`latest` + `history`)

## Out of Scope
- Risk scoring
- Workflow orchestration

## Firebase Data Shape
The service expects readings under:

`/<prefix>/telemetry/<asset_id>/latest`

and optionally:

`/<prefix>/telemetry/<asset_id>/history/<push-id>`

with payload:

```json
{
  "device_id": "esp32-node-01",
  "captured_at": "2026-02-14T12:30:00Z",
  "firmware_version": "1.0.0",
  "dht11": {
    "temperature_c": 28.4,
    "humidity_pct": 61.2
  },
  "accelerometer": {
    "x_g": 0.02,
    "y_g": -0.01,
    "z_g": 0.98
  }
}
```

## Environment Variables
- `SENSOR_INGESTION_FIREBASE_DB_URL` (required for Firebase calls)
- `SENSOR_INGESTION_FIREBASE_AUTH_TOKEN` (optional, if DB rules require token)
- `SENSOR_INGESTION_FIREBASE_PATH_PREFIX` (default: `infraguard`)
- `SENSOR_INGESTION_FIREBASE_TIMEOUT_SECONDS` (default: `8.0`)
- `SENSOR_INGESTION_TELEMETRY_WINDOW_SIZE` (default: `8`)

## Run
```bash
cd apps/sensor-ingestion-service
export SENSOR_INGESTION_FIREBASE_DB_URL="https://<project-id>-default-rtdb.firebaseio.com"
# export SENSOR_INGESTION_FIREBASE_AUTH_TOKEN="<optional-token>"
python3 -m uvicorn src.main:app --reload --port 8100
```

## API
- `GET /health`
- `GET /telemetry/assets/{asset_id}/latest`
- `POST /telemetry/assets/{asset_id}/ingest?persist_history=true`
