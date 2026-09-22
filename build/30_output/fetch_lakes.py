# %% [markdown]
# # PolygroveDB — lakes.geojson for the explorer maps (user, 2026-09-10: "blue for lakes")
#
# Natural Earth 50m lakes (public domain), properties stripped to the name.
# Cached: skips the network when the output already exists.

# %%
import json, os, requests

OUT = "../../explorer/data/lakes.geojson"
if os.path.exists(OUT) and os.path.getsize(OUT) > 10_000:
    print(f"lakes.geojson already present ({os.path.getsize(OUT)//1024} KB) — skipping fetch")
else:
    ne = requests.get(
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_lakes.geojson",
        timeout=120).json()
    feats = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {"name": f["properties"].get("name") or ""}}
             for f in ne["features"] if f.get("geometry")]
    json.dump({"type": "FeatureCollection", "features": feats},
              open(OUT, "w"), separators=(",", ":"))
    print(f"lakes.geojson: {len(feats)} lakes, {os.path.getsize(OUT)//1024} KB")
