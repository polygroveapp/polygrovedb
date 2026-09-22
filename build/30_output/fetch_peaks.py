# %% [markdown]
# # PolygroveDB — peaks.geojson: named mountains for the explorer map
# (user, 2026-09-16: "are there mountain names")
#
# Natural Earth 10m geography elevation points (public domain): 633 named
# mountains worldwide with elevations, ranked by importance (scalerank 1 =
# Everest-class). Depressions/passes/capes are dropped — the ▲ glyph asserts
# a summit. Cached: skips the network when the output already exists.

# %%
import json, os, requests

OUT = "../../explorer/data/peaks.geojson"
if os.path.exists(OUT) and os.path.getsize(OUT) > 10_000:
    print(f"peaks.geojson already present ({os.path.getsize(OUT)//1024} KB) — skipping fetch")
else:
    ne = requests.get(
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
        "ne_10m_geography_regions_elevation_points.geojson", timeout=120).json()
    feats = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {"name": f["properties"].get("name") or "",
                             "elev": f["properties"].get("elevation"),
                             "rank": f["properties"].get("scalerank", 9)}}
             for f in ne["features"]
             if f.get("geometry") and f["properties"].get("featurecla") == "mountain"
             and f["properties"].get("name")]
    json.dump({"type": "FeatureCollection", "features": feats},
              open(OUT, "w"), separators=(",", ":"))
    print(f"peaks.geojson: {len(feats)} named mountains, {os.path.getsize(OUT)//1024} KB")
