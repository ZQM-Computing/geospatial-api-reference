"""Data access for the API, behind one small interface.

Two backends implement the same contract:

- SampleRepository serves the bundled GeoJSON file. It exists so the API
  (and its test suite) runs anywhere with zero infrastructure -- and so the
  response shapes can be reviewed without standing up a database.
- PostGISRepository serves live tables from PostgreSQL/PostGIS, using
  ST_AsGeoJSON for geometry and to_jsonb() for properties.

Both return plain GeoJSON-shaped dicts. The HTTP layer never knows which
backend is behind it.
"""

from __future__ import annotations

import json
import time
from datetime import datetime as DateTime, timezone
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_features.geojson"

# Collection registry. For the PostGIS backend, "table" is the source table;
# every table is expected to have an "id" column and a "geom" geometry
# column (geometry(..., 4326)). See sql/schema.sql.
COLLECTIONS: dict[str, dict[str, Any]] = {
    "service-sites": {
        "table": "service_sites",
        "title": "Service sites",
        "description": "Synthetic municipal service locations (points).",
        "datetime_property": "datetime",
    },
    "parcels": {
        "table": "parcels",
        "title": "Parcels",
        "description": "Synthetic parcel-like polygons (not real property data).",
        "datetime_property": None,
    },
}


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def parse_datetime_range(value: str) -> tuple[str | None, str | None]:
    """Parse an OGC 'datetime' parameter: an instant, or 'start/end' where
    either end may be '..' (open). Returns (start, end) ISO strings."""
    if not value or value.count("/") > 1:
        raise ValueError("datetime must be an instant or one start/end interval")

    if "/" in value:
        start, end = value.split("/", 1)
        if not start and not end:
            raise ValueError("datetime interval cannot have two empty endpoints")
        start = None if start == ".." else start
        end = None if end == ".." else end
    else:
        start = end = value

    def validate_endpoint(endpoint: str | None) -> DateTime | None:
        if endpoint is None:
            return None
        try:
            # RFC 3339 instants must identify their timezone. Canonicalizing to
            # UTC avoids lexicographic mis-ordering for equivalent instants
            # written with different offsets.
            parsed = DateTime.fromisoformat(endpoint.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid RFC 3339 datetime: {endpoint}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("datetime endpoints must include a timezone")
        return parsed.astimezone(timezone.utc)

    start_dt = validate_endpoint(start)
    end_dt = validate_endpoint(end)
    if start_dt is not None and end_dt is not None:
        # Avoid comparing a naive timestamp with an offset-aware timestamp.
        if (start_dt.tzinfo is None) != (end_dt.tzinfo is None):
            raise ValueError("datetime interval endpoints must use compatible timezone notation")
        if start_dt > end_dt:
            raise ValueError("datetime interval start must not exceed its end")

    def canonical(endpoint: str | None) -> str | None:
        if endpoint is None:
            return None
        parsed = validate_endpoint(endpoint)
        assert parsed is not None
        return parsed.isoformat().replace("+00:00", "Z")

    return canonical(start), canonical(end)


def _geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    coords: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list) and node and isinstance(node[0], (int, float)):
            coords.append((float(node[0]), float(node[1])))
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_intersects(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


# --------------------------------------------------------------------------
# Sample backend
# --------------------------------------------------------------------------


class SampleRepository:
    def __init__(self, data_file: Path = DATA_FILE) -> None:
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        self._by_collection: dict[str, list[dict[str, Any]]] = {
            cid: [] for cid in COLLECTIONS
        }
        for feature in raw["features"]:
            cid = feature["properties"]["collection"]
            feature = {k: v for k, v in feature.items()}
            props = dict(feature["properties"])
            props.pop("collection", None)
            feature["properties"] = props
            feature["id"] = props["id"]
            self._by_collection[cid].append(feature)

    def list_collections(self) -> list[dict[str, Any]]:
        out = []
        for cid, meta in COLLECTIONS.items():
            features = self._by_collection[cid]
            bbox = None
            if features:
                boxes = [_geometry_bbox(f["geometry"]) for f in features]
                bbox = [
                    min(b[0] for b in boxes),
                    min(b[1] for b in boxes),
                    max(b[2] for b in boxes),
                    max(b[3] for b in boxes),
                ]
            out.append(
                {
                    "id": cid,
                    "title": meta["title"],
                    "description": meta["description"],
                    "bbox": bbox,
                    "count": len(features),
                }
            )
        return out

    def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        for coll in self.list_collections():
            if coll["id"] == collection_id:
                return coll
        return None

    def query_items(
        self,
        collection_id: str,
        bbox: tuple[float, float, float, float] | None = None,
        datetime_range: tuple[str | None, str | None] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        features = list(self._by_collection.get(collection_id, []))
        dt_prop = COLLECTIONS[collection_id]["datetime_property"]

        if bbox is not None:
            features = [
                f
                for f in features
                if _bbox_intersects(_geometry_bbox(f["geometry"]), bbox)
            ]
        if datetime_range is not None:
            start, end = datetime_range

            def in_range(f: dict[str, Any]) -> bool:
                if dt_prop is None:
                    return False
                value = f["properties"].get(dt_prop)
                if value is None:
                    return False
                try:
                    feature_dt = DateTime.fromisoformat(value.replace("Z", "+00:00"))
                except (AttributeError, TypeError, ValueError):
                    return False
                if feature_dt.tzinfo is None or feature_dt.utcoffset() is None:
                    return False
                feature_dt = feature_dt.astimezone(timezone.utc)
                start_dt = DateTime.fromisoformat(start.replace("Z", "+00:00")) if start else None
                end_dt = DateTime.fromisoformat(end.replace("Z", "+00:00")) if end else None
                if start_dt is not None and feature_dt < start_dt:
                    return False
                return not (end_dt is not None and feature_dt > end_dt)

            features = [f for f in features if in_range(f)]

        total = len(features)
        return features[offset : offset + limit], total

    def get_item(self, collection_id: str, feature_id: str) -> dict[str, Any] | None:
        for feature in self._by_collection.get(collection_id, []):
            if feature["properties"]["id"] == feature_id:
                return feature
        return None


# --------------------------------------------------------------------------
# PostGIS backend
# --------------------------------------------------------------------------


class PostGISRepository:
    """Serves the registered collections from PostGIS tables.

    The connection is opened lazily and retried briefly, so the API can
    start alongside its database (e.g. under docker compose) without a
    separate orchestration step.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._conn = None

    def _connection(self):
        if self._conn is not None and not self._conn.closed:
            return self._conn
        import psycopg  # imported lazily: the sample backend needs no driver

        last_error: Exception | None = None
        for _ in range(15):
            try:
                self._conn = psycopg.connect(self._database_url, autocommit=True)
                return self._conn
            except psycopg.Error as exc:  # database still starting
                last_error = exc
                time.sleep(2)
        raise RuntimeError(f"Could not connect to PostGIS: {last_error}")

    def list_collections(self) -> list[dict[str, Any]]:
        conn = self._connection()
        out = []
        for cid, meta in COLLECTIONS.items():
            table = meta["table"]
            row = conn.execute(
                f"""
                SELECT count(*),
                       ST_XMin(ST_Extent(geom)), ST_YMin(ST_Extent(geom)),
                       ST_XMax(ST_Extent(geom)), ST_YMax(ST_Extent(geom))
                FROM {table}
                """
            ).fetchone()
            count = row[0]
            bbox = list(row[1:]) if count and row[1] is not None else None
            out.append(
                {
                    "id": cid,
                    "title": meta["title"],
                    "description": meta["description"],
                    "bbox": bbox,
                    "count": count,
                }
            )
        return out

    def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        for coll in self.list_collections():
            if coll["id"] == collection_id:
                return coll
        return None

    def query_items(
        self,
        collection_id: str,
        bbox: tuple[float, float, float, float] | None = None,
        datetime_range: tuple[str | None, str | None] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conn = self._connection()
        table = COLLECTIONS[collection_id]["table"]
        where: list[str] = []
        params: list[Any] = []

        if bbox is not None:
            where.append(
                "geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) "
                "AND ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))"
            )
            params.extend([*bbox, *bbox])
        dt_prop = COLLECTIONS[collection_id]["datetime_property"]
        if datetime_range is not None and dt_prop is not None:
            start, end = datetime_range
            if start is not None:
                where.append(f"((to_jsonb(t) ->> '{dt_prop}')::timestamptz) >= %s::timestamptz")
                params.append(start)
            if end is not None:
                where.append(f"((to_jsonb(t) ->> '{dt_prop}')::timestamptz) <= %s::timestamptz")
                params.append(end)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(
            f"SELECT count(*) FROM {table} t {where_sql}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT t.id,
                   ST_AsGeoJSON(t.geom)::json AS geometry,
                   to_jsonb(t) - 'geom' AS properties
            FROM {table} t
            {where_sql}
            ORDER BY t.id
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        ).fetchall()

        features = [
            {
                "type": "Feature",
                "id": row[0],
                "geometry": row[1],
                "properties": row[2],
            }
            for row in rows
        ]
        return features, total

    def get_item(self, collection_id: str, feature_id: str) -> dict[str, Any] | None:
        conn = self._connection()
        table = COLLECTIONS[collection_id]["table"]
        row = conn.execute(
            f"""
            SELECT t.id,
                   ST_AsGeoJSON(t.geom)::json AS geometry,
                   to_jsonb(t) - 'geom' AS properties
            FROM {table} t
            WHERE t.id = %s
            """,
            (feature_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "type": "Feature",
            "id": row[0],
            "geometry": row[1],
            "properties": row[2],
        }


def make_repository(settings) -> SampleRepository | PostGISRepository:
    if settings.data_backend == "postgis":
        return PostGISRepository(settings.database_url)
    return SampleRepository()
