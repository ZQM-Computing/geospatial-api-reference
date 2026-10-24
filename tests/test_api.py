"""API tests against the sample backend -- no database required."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(Settings(data_backend="sample")))


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_landing_page(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["title"] == "Geospatial API Reference"
    rels = {link["rel"] for link in body["links"]}
    assert {"self", "conformance", "data"} <= rels


def test_conformance_lists_features_core(client: TestClient) -> None:
    body = client.get("/conformance").json()
    assert any("ogcapi-features-1" in uri for uri in body["conformsTo"])


def test_collections(client: TestClient) -> None:
    body = client.get("/collections").json()
    ids = {coll["id"] for coll in body["collections"]}
    assert ids == {"service-sites", "parcels"}
    sites = next(c for c in body["collections"] if c["id"] == "service-sites")
    assert sites["extent"]["spatial"]["bbox"][0] == [-81.1, 29.08, -80.76, 29.33]


def test_items_returns_all_sites(client: TestClient) -> None:
    body = client.get("/collections/service-sites/items").json()
    assert body["type"] == "FeatureCollection"
    assert body["numberMatched"] == 5
    assert body["numberReturned"] == 5
    assert body["features"][0]["geometry"]["type"] == "Point"


def test_items_bbox_filter(client: TestClient) -> None:
    # Box around the two northern sites only.
    body = client.get(
        "/collections/service-sites/items",
        params={"bbox": "-81.15,29.18,-80.95,29.35"},
    ).json()
    names = {f["properties"]["name"] for f in body["features"]}
    assert names == {"North depot", "North library"}
    assert body["numberMatched"] == 2


def test_items_datetime_filter(client: TestClient) -> None:
    body = client.get(
        "/collections/service-sites/items",
        params={"datetime": "2026-02-01T00:00:00Z/2026-02-28T23:59:59Z"},
    ).json()
    names = {f["properties"]["name"] for f in body["features"]}
    assert names == {"Central depot", "Coastal depot"}


def test_items_limit_and_offset(client: TestClient) -> None:
    page1 = client.get(
        "/collections/parcels/items", params={"limit": 2, "offset": 0}
    ).json()
    page2 = client.get(
        "/collections/parcels/items", params={"limit": 2, "offset": 2}
    ).json()
    assert page1["numberMatched"] == 3
    assert page1["numberReturned"] == 2
    assert page2["numberReturned"] == 1
    ids = {f["id"] for f in page1["features"]} | {f["id"] for f in page2["features"]}
    assert ids == {"parcel-1", "parcel-2", "parcel-3"}


def test_single_item(client: TestClient) -> None:
    response = client.get("/collections/parcels/items/parcel-2")
    assert response.status_code == 200
    body = response.json()
    assert body["properties"]["land_use"] == "conservation"


def test_unknown_collection_404(client: TestClient) -> None:
    assert client.get("/collections/nope/items").status_code == 404


def test_unknown_feature_404(client: TestClient) -> None:
    assert client.get("/collections/parcels/items/parcel-99").status_code == 404


def test_invalid_bbox_400(client: TestClient) -> None:
    response = client.get("/collections/parcels/items", params={"bbox": "1,2,3"})
    assert response.status_code == 400


def test_antimeridian_bbox_is_valid(client: TestClient) -> None:
    # OGC API - Features permits west longitude > east longitude when a bbox
    # crosses the antimeridian (e.g. New Zealand's longitudes).
    response = client.get(
        "/collections/service-sites/items",
        params={"bbox": "160.6,-55.95,-170,-25.89"},
    )
    assert response.status_code == 200
    assert response.json()["numberMatched"] == 0


@pytest.mark.parametrize(
    "bbox",
    [
        "NaN,29,-80,30",
        "inf,29,80,30",
        "-181,29,-80,30",
        "-81,91,-80,30",
        "-80,29,-81,30",
        "-81,31,-80,30",
        "-81,29,-80",
        "west,29,-80,30",
    ],
)
def test_invalid_bbox_values_return_400(client: TestClient, bbox: str) -> None:
    response = client.get("/collections/parcels/items", params={"bbox": bbox})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date",
        "2026-02-30T00:00:00Z",
        "2026-03-01T00:00:00Z/2026-02-01T00:00:00Z",
        "2026-01-01T00:00:00Z/2026-02-01T00:00:00Z/2026-03-01T00:00:00Z",
        "/",
    ],
)
def test_invalid_datetime_returns_400(client: TestClient, value: str) -> None:
    response = client.get(
        "/collections/service-sites/items", params={"datetime": value}
    )
    assert response.status_code == 400


def test_open_datetime_interval_is_supported(client: TestClient) -> None:
    response = client.get(
        "/collections/service-sites/items",
        params={"datetime": "../2026-02-28T23:59:59Z"},
    )
    assert response.status_code == 200

def test_datetime_offsets_compare_as_instants(client: TestClient) -> None:
    response = client.get(
        "/collections/service-sites/items",
        params={"datetime": "2026-01-15T13:00:00+01:00/2026-01-20T13:00:00+01:00"},
    )
    assert response.status_code == 200
    assert {feature["id"] for feature in response.json()["features"]} == {"site-1", "site-2"}


def test_datetime_requires_timezone(client: TestClient) -> None:
    response = client.get(
        "/collections/service-sites/items",
        params={"datetime": "2026-01-15T12:00:00/2026-01-20T12:00:00"},
    )
    assert response.status_code == 400
