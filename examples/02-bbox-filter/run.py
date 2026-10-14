"""Example 02: Bounding box filtering with FastAPI."""

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="OGC API - Features with BBox", version="1.0.0")

FEATURES = [
    {"id": 1, "name": "Point A", "lon": -80.93, "lat": 29.02},
    {"id": 2, "name": "Point B", "lon": -80.92, "lat": 29.03},
    {"id": 3, "name": "Point C", "lon": -80.91, "lat": 29.01},
]


@app.get("/collections/points/items")
def get_items(bbox: str | None = None, limit: int = 10):
    items = []
    for f in FEATURES[:limit]:
        if bbox:
            minx, miny, maxx, maxy = [float(x) for x in bbox.split(",")]
            if not (minx <= f["lon"] <= maxx and miny <= f["lat"] <= maxy):
                continue
        items.append(
            {
                "type": "Feature",
                "id": f["id"],
                "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                "properties": {"name": f["name"]},
            }
        )
    return {"type": "FeatureCollection", "features": items}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
