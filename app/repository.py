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
from pathlib import Path
from typing import Any, Optional

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

def parse_datetime_range(value: str) -> tuple[Optional[str], Optional[str]]:
    """Parse an OGC 'datetime' parameter: an instant, or 'start/end' where
    either end may be '..' (open). Returns (start, end) ISO strings."""
    if "/" not in value:
        return value, value
    start, end = value.split("/", 1)
    return (None if start == ".." else start), (None if end == ".." else end)


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

    def get_collection(self, collection_id: str) -> Optional[dict[str, Any]]:
        for coll in self.list_collections():
            if coll["id"] == collection_id:
                return coll
        return None

    def query_items(
        self,
        collection_id: str,
        bbox: Optional[tuple[float, float, float, float]] = None,
        datetime_range: Optional[tuple[Optional[str], Optional[str]]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        features = list(self._by_collection.get(collection_id, []))
        dt_prop = COLLECTIONS[collection_id]["datetime_property"]

        if bbox is not None:
            features = [
                f for f in features if _bbox_intersects(_geometry_bbox(f["geometry"]), bbox)
            ]
        if datetime_range is not None:
            start, end = datetime_range

            def in_range(f: dict[str, Any]) -> bool:
                if dt_prop is None:
                    return False
                value = f["properties"].get(dt_prop)
                if value is None:
                    return False
                if start is not None and value < start:
                    return False
                if end is not None and value > end:
                    return False
                return True

            features = [f for f in features if in_range(f)]

        total = len(features)
        return features[offset : offset + limit], total

    def get_item(
        self, collection_id: str, feature_id: str
    ) -> Optional[dict[str, Any]]:
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

        last_error: Optional[Exception] = None
        for _ in range(15):
            try:
                self._conn = psycopg.connect(self._database_url, autocommit=True)
                return self._conn
            except Exception as exc:  # database still starting
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

    def get_collection(self, collection_id: str) -> Optional[dict[str, Any]]:
        for coll in self.list_collections():
            if coll["id"] == collection_id:
                return coll
        return None

    def query_items(
        self,
        collection_id: str,
        bbox: Optional[tuple[float, float, float, float]] = None,
        datetime_range: Optional[tuple[Optional[str], Optional[str]]] = None,
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
                where.append(f"(to_jsonb(t) ->> '{dt_prop}') >= %s")
                params.append(start)
            if end is not None:
                where.append(f"(to_jsonb(t) ->> '{dt_prop}') <= %s")
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

    def get_item(
        self, collection_id: str, feature_id: str
    ) -> Optional[dict[str, Any]]:
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
