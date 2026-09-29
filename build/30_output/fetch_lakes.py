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

# %% [markdown]
# ## Names for the unnamed (2026-09-29: "lake names for the lakes you can see")
# 91 of the 412 drawn lakes have no name in the 50m file. Natural Earth's 10m
# lakes (same project, public domain) name most of them: each unnamed 50m lake
# takes the name of the 10m lake whose centre sits closest to its own, within
# a quarter of a degree. Cached like the rest: runs only while names are missing.

# %%
def _cen(geo):
    polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
    pts = [p for poly in polys for p in poly[0]]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

fc = json.load(open(OUT))
missing = [f for f in fc["features"] if not f["properties"].get("name")]
if missing and not fc.get("names_filled"):
    ne10 = requests.get(
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_lakes.geojson",
        timeout=180).json()
    named10 = [(f["properties"].get("name"), _cen(f["geometry"])) for f in ne10["features"]
               if f.get("geometry") and f["properties"].get("name")]
    n = 0
    for f in missing:
        x, y = _cen(f["geometry"])
        best = min(named10, key=lambda t: (t[1][0] - x) ** 2 + (t[1][1] - y) ** 2)
        if ((best[1][0] - x) ** 2 + (best[1][1] - y) ** 2) ** 0.5 <= 0.25:
            f["properties"]["name"] = best[0]; n += 1
    fc["names_filled"] = True
    json.dump(fc, open(OUT, "w"), separators=(",", ":"))
    print(f"filled {n} of {len(missing)} missing lake names from the 10m file")
