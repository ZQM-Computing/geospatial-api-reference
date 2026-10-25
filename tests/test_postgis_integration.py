"""Integration tests for query filters against a real PostGIS service.

These tests are skipped in the database-free default suite. The dedicated
PostGIS integration workflow sets GEOAPI_TEST_DATABASE_URL and initializes
the disposable database from sql/schema.sql before running them.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DATABASE_URL = os.getenv("GEOAPI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="requires a PostGIS database (set GEOAPI_TEST_DATABASE_URL)",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    assert DATABASE_URL is not None
    return TestClient(
        create_app(Settings(data_backend="postgis", database_url=DATABASE_URL))
    )


def test_postgis_bbox_and_datetime_filters(client: TestClient) -> None:
    response = client.get(
        "/collections/service-sites/items",
        params={
            "bbox": "-81.15,29.18,-80.95,29.35",
            "datetime": "2026-01-01T00:00:00Z/2026-01-31T23:59:59Z",
        },
    )
    assert response.status_code == 200
    assert {feature["id"] for feature in response.json()["features"]} == {
        "site-1",
        "site-2",
    }


def test_postgis_antimeridian_bbox_queries_both_edges(client: TestClient) -> None:
    assert DATABASE_URL is not None
    test_ids = ("integration-east", "integration-west")
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                INSERT INTO service_sites (id, name, category, datetime, geom)
                VALUES
                    (%s, 'Integration east', 'test', '2026-01-01T00:00:00Z',
                     ST_SetSRID(ST_MakePoint(175, 0), 4326)),
                    (%s, 'Integration west', 'test', '2026-01-01T00:00:00Z',
                     ST_SetSRID(ST_MakePoint(-175, 0), 4326))
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    datetime = EXCLUDED.datetime,
                    geom = EXCLUDED.geom
                """,
                test_ids,
            )

        response = client.get(
            "/collections/service-sites/items",
            params={"bbox": "160,-20,-170,20"},
        )
        assert response.status_code == 200
        returned = {feature["id"] for feature in response.json()["features"]}
        assert set(test_ids) <= returned
    finally:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "DELETE FROM service_sites WHERE id IN (%s, %s)",
                test_ids,
            )
