"""Example 01: Basic OGC API - Features with FastAPI."""

import uvicorn
from fastapi import FastAPI, HTTPException

app = FastAPI(title="OGC API - Features", version="1.0.0")

# In-memory feature store
FEATURES = [
    {"id": 1, "name": "Point A", "lon": -80.93, "lat": 29.02, "type": "point"},
    {"id": 2, "name": "Point B", "lon": -80.92, "lat": 29.03, "type": "point"},
    {"id": 3, "name": "Point C", "lon": -80.91, "lat": 29.01, "type": "point"},
]


@app.get("/collections")
def get_collections():
    return [{"id": "points", "title": "Sample Points", "links": []}]


@app.get("/collections/points/items")
def get_items(bbox: str | None = None, limit: int = 10):
    items = []
    for f in FEATURES[:limit]:
        items.append(
            {
                "type": "Feature",
                "id": f["id"],
                "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                "properties": {"name": f["name"], "type": f["type"]},
            }
        )
    return {"type": "FeatureCollection", "features": items}


@app.get("/collections/points/items/{item_id}")
def get_item(item_id: int):
    for f in FEATURES:
        if f["id"] == item_id:
            return {
                "type": "Feature",
                "id": f["id"],
                "geometry": {"type": "Point", "coordinates": [f["lon"], f["lat"]]},
                "properties": {"name": f["name"], "type": f["type"]},
            }
    raise HTTPException(status_code=404, detail="Item not found")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
