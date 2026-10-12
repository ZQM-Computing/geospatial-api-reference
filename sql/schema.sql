-- Schema + sample data for the PostGIS backend.
--
-- Each OGC collection is one table with an "id" text column and a "geom"
-- geometry column in EPSG:4326. The repository turns rows into GeoJSON with
-- ST_AsGeoJSON(geom) for geometry and to_jsonb(row) - 'geom' for properties,
-- so any additional columns you add become feature properties automatically.
--
-- Load with:  psql "$DATABASE_URL" -f sql/schema.sql
-- (Under docker compose this file runs automatically on first database
-- start via /docker-entrypoint-initdb.d.)

CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS service_sites;
CREATE TABLE service_sites (
    id text PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL,
    datetime timestamptz,
    geom geometry(Point, 4326) NOT NULL
);

DROP TABLE IF EXISTS parcels;
CREATE TABLE parcels (
    id text PRIMARY KEY,
    land_use text NOT NULL,
    acres numeric NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL
);

CREATE INDEX service_sites_geom_gist ON service_sites USING gist (geom);
CREATE INDEX parcels_geom_gist ON parcels USING gist (geom);

-- Same synthetic features as data/sample_features.geojson.
INSERT INTO service_sites (id, name, category, datetime, geom) VALUES
    ('site-1', 'North depot',   'operations', '2026-01-15T12:00:00Z', ST_SetSRID(ST_MakePoint(-81.10, 29.28), 4326)),
    ('site-2', 'North library', 'civic',      '2026-01-20T12:00:00Z', ST_SetSRID(ST_MakePoint(-81.02, 29.22), 4326)),
    ('site-3', 'Central depot', 'operations', '2026-02-01T12:00:00Z', ST_SetSRID(ST_MakePoint(-81.10, 29.08), 4326)),
    ('site-4', 'Coastal depot', 'operations', '2026-02-10T12:00:00Z', ST_SetSRID(ST_MakePoint(-80.85, 29.28), 4326)),
    ('site-5', 'Coastal clinic','health',     '2026-03-01T12:00:00Z', ST_SetSRID(ST_MakePoint(-80.76, 29.33), 4326));

INSERT INTO parcels (id, land_use, acres, geom) VALUES
    ('parcel-1', 'residential', 610.5, ST_MakeEnvelope(-81.16, 29.02, -81.12, 29.06, 4326)),
    ('parcel-2', 'conservation', 545.2, ST_MakeEnvelope(-81.05, 29.10, -81.01, 29.14, 4326)),
    ('parcel-3', 'commercial',   402.8, ST_MakeEnvelope(-80.90, 29.20, -80.86, 29.24, 4326));
