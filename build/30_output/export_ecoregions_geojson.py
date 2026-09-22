# %% [markdown]
# # PolygroveDB — the explorer's ecoregion basemap geojson
#
# Replaces an ad-hoc export that had two sins (user, 2026-09-09: "smooth out the
# borders and make sure there are not gaps"): aggressive per-polygon simplification
# tore shared borders apart into black sliver gaps, and left everything jagged.
# Recipe: MakeValid -> simplify (gentler) -> small BUFFER with round joins, which
# closes inter-polygon gaps AND rounds the corners in one move. A second, lighter
# simplify AFTER the buffer strips the arc vertices (first attempt: 44.7 MB). Overlaps replace
# gaps; on same-colored fills overlaps are invisible, gaps are black.

# %%
import duckdb, json, time
t0=time.time()
con=duckdb.connect(); con.sql("INSTALL spatial; LOAD spatial;")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
rows=con.sql("""
  SELECT ECO_ID, ECO_NAME,
         ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Buffer(ST_SimplifyPreserveTopology(ST_MakeValid(geom), 0.012), 0.02, 3), 0.009)) AS gj
  FROM pg.ecoregions WHERE geom IS NOT NULL ORDER BY ECO_ID""").fetchall()
def q(o):                       # quantize to ~100m so the buffer's arcs don't bloat the file
    if isinstance(o,list): return [q(x) for x in o]
    if isinstance(o,float): return round(o,3)
    return o
feats=[]
for eid,name,gj in rows:
    g=json.loads(gj); g['coordinates']=q(g['coordinates'])
    feats.append({"type":"Feature","geometry":g,"properties":{"eco":eid,"name":name}})
fc={"type":"FeatureCollection","features":feats}
out="../../explorer/data/ecoregions.geojson"
json.dump(fc, open(out,"w"), separators=(',',':'))
import os
print(f"{len(feats)} ecoregions, {os.path.getsize(out)/1e6:.1f} MB  ({time.time()-t0:.0f}s)")
