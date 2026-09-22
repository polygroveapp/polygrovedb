# %% [markdown]
# # PolygroveDB — trails.geojson: NPS Public Trails for the explorer map
# (user, 2026-09-10: "add trail data")
#
# One national, PUBLIC-DOMAIN dataset (NPS NationalDatasets/NPS_Public_Trails),
# ~31.5k trail segments in US national parks — chosen over OpenStreetMap trails
# (ODbL share-alike would muddy the all-CC-BY/CC0 story) and over the 30+
# scattered per-trail NST/NHT services. Geometry simplified server-side
# (~110 m) — the layer is for park-scale viewing, not navigation.
# Cached: skips the network when the output already exists.

# %%
import json, os, requests

OUT = "../../explorer/data/trails.geojson"
BASE = ("https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/"
        "NPS_Public_Trails_Geographic/FeatureServer/0/query")
if os.path.exists(OUT) and os.path.getsize(OUT) > 100_000:
    print(f"trails.geojson already present ({os.path.getsize(OUT)//1024} KB) — skipping fetch")
else:
    feats, offset = [], 0
    while True:
        r = requests.get(BASE, params={
            "where": "1=1", "outFields": "MAPLABEL,TRLNAME", "outSR": "4326",
            "geometryPrecision": "4", "maxAllowableOffset": "0.001",
            "resultOffset": str(offset), "resultRecordCount": "2000", "f": "geojson",
        }, timeout=180).json()
        page = r.get("features", [])
        for f in page:
            if not f.get("geometry"):
                continue
            p = f.get("properties", {})
            feats.append({"type": "Feature", "geometry": f["geometry"],
                          "properties": {"name": p.get("MAPLABEL") or p.get("TRLNAME") or ""}})
        print(f"  {offset + len(page)} fetched", flush=True)
        if len(page) < 2000:
            break
        offset += 2000
    json.dump({"type": "FeatureCollection", "features": feats},
              open(OUT, "w"), separators=(",", ":"))
    print(f"trails.geojson: {len(feats)} trail segments, {os.path.getsize(OUT)//1024} KB")
