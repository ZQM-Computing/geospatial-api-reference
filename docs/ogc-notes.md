# OGC API – Features: how this service maps to the standard

This service implements the essentials of **OGC API – Features Part 1: Core** — the successor pattern to WFS — in plain FastAPI.

| Standard concept | Here |
|---|---|
| Landing page | `GET /` with `self`, `conformance`, and `data` links |
| Conformance declaration | `GET /conformance` listing the Core, OpenAPI 3.0, and GeoJSON classes |
| Collections | `GET /collections`, `GET /collections/{id}` with spatial extent |
| Items query | `GET /collections/{id}/items` with `bbox`, `datetime`, `limit`, `offset` |
| Single feature | `GET /collections/{id}/items/{featureId}` |
| Response media type | GeoJSON (`application/geo+json`) |
| CRS | CRS84 (longitude/latitude), declared on each collection |

## Intentionally out of scope (and where they'd go)

- **Transactions (create/update/delete)** — Part 4 of the standard; add as a separate router with authentication in front, never bolt writes onto the read path.
- **CQL2 filtering** — Part 3; the natural extension once basic `bbox`/`datetime` no longer suffice. Parse CQL2 into parameterized SQL — never string-concatenate user input into a query.
- **Vector tiles** — a different standard (OGC API – Tiles); in this architecture, serve tiles from the same PostGIS store with `ST_AsMVT` (see [postgis-cookbook](https://github.com/ZQM-Computing/postgis-cookbook)) behind a cache.
- **HTML responses** — content negotiation to an HTML map view is pleasant for demos; JSON-first keeps the reference honest.

## Production checklist

- Put authentication and rate limiting at a gateway or FastAPI middleware; OGC Core assumes an open read API, your data may not be.
- Pool PostGIS connections (psycopg3 pool or PgBouncer) instead of one connection per process state.
- Add `ETag`/`Cache-Control` on items responses — feature data is cache-friendly and CDNs do the heavy lifting.
- Keep the collection registry data-driven: in a real deployment, generate it from the database catalog rather than a code constant.
- Log slow queries with their `bbox`/`limit` parameters; spatial APIs fail in interesting ways at the extremes (world-size bboxes, million-row pages).

## Datetime filtering and collections without a temporal property

The `datetime` query parameter is parsed as a timezone-aware instant or interval and normalized to UTC before backend filtering. Collections that do not declare a temporal property (for example, the synthetic `parcels` collection) return an empty FeatureCollection when a valid datetime filter is supplied; the sample and PostGIS backends must behave consistently. This behavior is an implementation contract, not a claim of full OGC API conformance.
