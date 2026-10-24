"""OGC API - Features (Part 1: Core) reference service.

Endpoints:
    GET /                                        landing page
    GET /conformance                             conformance classes
    GET /collections                             collection list
    GET /collections/{collection_id}             one collection
    GET /collections/{collection_id}/items       features (bbox, datetime,
                                                 limit, offset)
    GET /collections/{collection_id}/items/{id}  one feature
    GET /healthz                                 liveness probe

Run locally (sample data, no database):
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.repository import make_repository, parse_datetime_range

CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]


def _link(request: Request, rel: str, href: str, title: str) -> dict[str, str]:
    return {
        "rel": rel,
        "type": "application/geo+json"
        if href.endswith("items") or "/items" in href
        else "application/json",
        "title": title,
        "href": str(request.base_url).rstrip("/") + href,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="Geospatial API Reference",
        description=(
            "Reference implementation of OGC API - Features over FastAPI, "
            "with interchangeable sample-data and PostGIS backends."
        ),
        version="1.0.0",
    )
    app.state.settings = settings
    app.state.repo = make_repository(settings)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def landing(request: Request) -> dict[str, Any]:
        return {
            "title": "Geospatial API Reference",
            "description": (
                "OGC API - Features reference service. Browse the "
                "collections, then query items as GeoJSON."
            ),
            "links": [
                _link(request, "self", "/", "This document"),
                _link(request, "conformance", "/conformance", "Conformance classes"),
                _link(request, "data", "/collections", "Feature collections"),
            ],
        }

    @app.get("/conformance")
    def conformance() -> dict[str, Any]:
        return {"conformsTo": CONFORMANCE}

    @app.get("/collections")
    def collections(request: Request) -> dict[str, Any]:
        repo = request.app.state.repo
        out = []
        for coll in repo.list_collections():
            item = {
                "id": coll["id"],
                "title": coll["title"],
                "description": coll["description"],
                "itemType": "feature",
                "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                "links": [
                    _link(
                        request,
                        "items",
                        f"/collections/{coll['id']}/items",
                        "Items as GeoJSON",
                    )
                ],
            }
            if coll["bbox"]:
                item["extent"] = {"spatial": {"bbox": [coll["bbox"]]}}
            out.append(item)
        return {
            "collections": out,
            "links": [_link(request, "self", "/collections", "Collections")],
        }

    def _require_collection(request: Request, collection_id: str) -> dict[str, Any]:
        coll = request.app.state.repo.get_collection(collection_id)
        if coll is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown collection: {collection_id}"
            )
        return coll

    @app.get("/collections/{collection_id}")
    def collection(request: Request, collection_id: str) -> dict[str, Any]:
        coll = _require_collection(request, collection_id)
        body: dict[str, Any] = {
            "id": coll["id"],
            "title": coll["title"],
            "description": coll["description"],
            "itemType": "feature",
            "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
            "links": [
                _link(
                    request, "self", f"/collections/{collection_id}", "This collection"
                ),
                _link(
                    request,
                    "items",
                    f"/collections/{collection_id}/items",
                    "Items as GeoJSON",
                ),
            ],
        }
        if coll["bbox"]:
            body["extent"] = {"spatial": {"bbox": [coll["bbox"]]}}
        return body

    @app.get("/collections/{collection_id}/items")
    def items(
        request: Request,
        collection_id: str,
        bbox: str | None = None,
        datetime: str | None = None,
        limit: int | None = Query(default=None, ge=1),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        _require_collection(request, collection_id)
        settings = request.app.state.settings

        bbox_tuple = None
        if bbox is not None:
            parts = bbox.split(",")
            if len(parts) != 4:
                raise HTTPException(
                    status_code=400, detail="bbox must be minx,miny,maxx,maxy"
                )
            try:
                values = tuple(float(p) for p in parts)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="bbox values must be numbers"
                ) from exc
            if not all(isfinite(value) for value in values):
                raise HTTPException(
                    status_code=400, detail="bbox values must be finite numbers"
                )
            minx, miny, maxx, maxy = values
            if not (-180 <= minx <= 180 and -180 <= maxx <= 180):
                raise HTTPException(
                    status_code=400, detail="bbox longitude must be between -180 and 180"
                )
            if not (-90 <= miny <= 90 and -90 <= maxy <= 90):
                raise HTTPException(
                    status_code=400, detail="bbox latitude must be between -90 and 90"
                )
            if minx > maxx or miny > maxy:
                raise HTTPException(
                    status_code=400, detail="bbox minimums must not exceed maximums"
                )
            bbox_tuple = values

        try:
            datetime_range = parse_datetime_range(datetime) if datetime else None
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="datetime must be an ISO-8601 instant or start/end interval; use '..' for an open interval",
            ) from exc
        page_limit = min(limit or settings.default_limit, settings.max_limit)

        features, total = request.app.state.repo.query_items(
            collection_id,
            bbox=bbox_tuple,
            datetime_range=datetime_range,
            limit=page_limit,
            offset=offset,
        )
        return {
            "type": "FeatureCollection",
            "features": features,
            "numberMatched": total,
            "numberReturned": len(features),
            "links": [
                _link(request, "self", f"/collections/{collection_id}/items", "Items")
            ],
        }

    @app.get("/collections/{collection_id}/items/{feature_id}")
    def item(request: Request, collection_id: str, feature_id: str) -> Any:
        _require_collection(request, collection_id)
        feature = request.app.state.repo.get_item(collection_id, feature_id)
        if feature is None:
            raise HTTPException(
                status_code=404, detail=f"Unknown feature: {feature_id}"
            )
        return JSONResponse(content=feature, media_type="application/geo+json")

    return app


app = create_app()
