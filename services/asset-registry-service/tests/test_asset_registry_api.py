"""API tests for asset registry service."""

from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from asset_registry.db import Base, get_db_session
from asset_registry.main import app


@contextmanager
def _build_test_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_create_get_and_list_asset() -> None:
    with _build_test_client() as client:
        create_payload = {
            "asset_id": "asset_w12_bridge_42",
            "name": "Central Bridge Span A",
            "asset_type": "bridge",
            "zone": "w12",
            "location": {"lat": 19.0760, "lon": 72.8777},
            "metadata": {"owner": "city-corp"},
        }

        create_response = client.post("/assets", json=create_payload)
        assert create_response.status_code == 201
        assert create_response.json()["data"]["asset_id"] == create_payload["asset_id"]

        get_response = client.get("/assets/asset_w12_bridge_42")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["name"] == "Central Bridge Span A"

        list_response = client.get("/assets?page=1&page_size=10&zone=w12")
        assert list_response.status_code == 200
        body = list_response.json()
        assert len(body["data"]) == 1
        assert body["pagination"]["total_items"] == 1
        assert body["pagination"]["total_pages"] == 1


def test_create_asset_conflict_returns_409() -> None:
    with _build_test_client() as client:
        payload = {
            "asset_id": "asset_w12_road_1",
            "name": "Ring Road Segment",
            "asset_type": "road",
            "zone": "w12",
            "location": {"lat": 19.1, "lon": 72.8},
            "metadata": {},
        }

        first = client.post("/assets", json=payload)
        second = client.post("/assets", json=payload)

        assert first.status_code == 201
        assert second.status_code == 409


def test_update_status_and_sensor_mapping() -> None:
    with _build_test_client() as client:
        asset_payload = {
            "asset_id": "asset_w15_tunnel_7",
            "name": "Harbor Tunnel",
            "asset_type": "tunnel",
            "zone": "w15",
            "location": {"lat": 19.2, "lon": 72.9},
            "metadata": {},
        }
        create_asset = client.post("/assets", json=asset_payload)
        assert create_asset.status_code == 201

        update_status = client.patch(
            "/assets/asset_w15_tunnel_7/status",
            json={"status": "maintenance"},
        )
        assert update_status.status_code == 200
        assert update_status.json()["data"]["status"] == "maintenance"

        map_sensor = client.post(
            "/assets/asset_w15_tunnel_7/sensors",
            json={
                "sensor_id": "sensor_t7_strain_1",
                "gateway_id": "gw_w15_01",
                "firmware_version": "1.2.3",
                "status": "active",
                "calibration": {"offset": 0.03},
            },
        )
        assert map_sensor.status_code == 201
        assert map_sensor.json()["data"]["asset_id"] == "asset_w15_tunnel_7"

        list_sensors = client.get("/assets/asset_w15_tunnel_7/sensors")
        assert list_sensors.status_code == 200
        assert len(list_sensors.json()["data"]) == 1


def test_map_sensor_for_unknown_asset_returns_404() -> None:
    with _build_test_client() as client:
        response = client.post(
            "/assets/asset_unknown_bridge_1/sensors",
            json={
                "sensor_id": "sensor_u1_strain_1",
                "status": "active",
                "calibration": {},
            },
        )
        assert response.status_code == 404
