# Asset Registry Service

Master data service for assets and sensor-node mapping.

## Responsibilities

- Asset CRUD and lifecycle state.
- Sensor mapping and calibration metadata.
- Zone-level filtering for downstream services.

## API (v0.1)

- `GET /health`
- `POST /assets`
- `GET /assets`
- `GET /assets/{asset_id}`
- `PATCH /assets/{asset_id}/status`
- `POST /assets/{asset_id}/sensors`
- `GET /assets/{asset_id}/sensors`

## Project Structure

- `src/asset_registry/config.py`: environment settings.
- `src/asset_registry/db.py`: SQLAlchemy engine/session wiring.
- `src/asset_registry/models.py`: DB models (asset + sensor node).
- `src/asset_registry/schemas.py`: request/response models.
- `src/asset_registry/repositories.py`: persistence operations.
- `src/asset_registry/routes/`: HTTP route handlers.
- `src/asset_registry/main.py`: FastAPI app assembly.
- `tests/test_asset_registry_api.py`: API-level tests.

## Run

```bash
cd services/asset-registry-service
python3 -m uvicorn src.main:app --reload --port 8101
```

Environment variables (optional):

- `ASSET_REGISTRY_DATABASE_URL` (default: `sqlite:///./asset_registry.db`)
- `ASSET_REGISTRY_SQL_ECHO` (`true`/`false`)
