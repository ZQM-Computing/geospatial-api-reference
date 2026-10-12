"""Application settings.

Environment variables use the GEOAPI_ prefix, e.g. GEOAPI_DATA_BACKEND=postgis
and GEOAPI_DATABASE_URL=postgresql://user:pass@host:5432/dbname.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # "sample" serves the bundled GeoJSON dataset (no database needed --
    # the mode the tests and the quick demo run in).
    # "postgis" serves live tables from PostgreSQL/PostGIS.
    data_backend: str = "sample"

    # Used only by the PostGIS backend.
    database_url: str = "postgresql://geoapi:geoapi@localhost:54329/geoapi"

    # OGC API "limit" handling: default page size and hard ceiling.
    default_limit: int = 50
    max_limit: int = 500

    model_config = {"env_prefix": "GEOAPI_"}
