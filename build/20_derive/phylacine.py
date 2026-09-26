# %% [markdown]
# # PolygroveDB — PHYLACINE mammal ranges (step 27, CC0)
#
# Mammals crashed in the license-clean deck (they'd relied on CC-BY-NC
# occurrences for biome). **PHYLACINE 1.2 (CC0)** gives expert range maps for
# 5,831 mammals — as presence/absence rasters on a fixed EPSG:6933 grid. The
# grid is shared by every species, so we map each cell → ecoregion ONCE, then
# each mammal is a cheap lookup. Unbiased, clean, and it fills the mammal hole.

# %%
import rasterio, rasterio.warp, numpy as np, pandas as pd, duckdb, glob, os, time
from collections import Counter
con = duckdb.connect("../../polygrove.duckdb"); con.sql("INSTALL spatial; LOAD spatial;")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
t0=time.time()
RASTERS = sorted(glob.glob("../../data/phylacine_extract/PHYLACINE_1.2-master/Data/Ranges/Current/*.tif"))
print(f"{len(RASTERS)} mammal range rasters", flush=True)

# grid cell → ecoregion, computed once (reproject EPSG:6933 → lon/lat, point-in-polygon)
with rasterio.open(RASTERS[0]) as r: T=r.transform; H,W=r.shape; crs=str(r.crs)
idx=np.arange(H*W); rows,cols=np.divmod(idx, W)
xs=T.c+(cols+0.5)*T.a; ys=T.f+(rows+0.5)*T.e
lon,lat=rasterio.warp.transform(crs,"EPSG:4326", xs.tolist(), ys.tolist())
con.register("cells_df", pd.DataFrame({"idx":idx,"lon":lon,"lat":lat}))
con.sql("""CREATE OR REPLACE TEMP TABLE pce AS
  SELECT c.idx, e.ECO_ID FROM cells_df c JOIN ecoregions e ON ST_Contains(e.geom, ST_Point(c.lon,c.lat));""")
cell2eco = dict(con.sql("SELECT idx, ECO_ID FROM pce").fetchall())
print(f"grid cells mapped to an ecoregion: {len(cell2eco):,}  ({time.time()-t0:.0f}s)", flush=True)

# %% [markdown]
# ## Read each raster → (species, ecoregion, cell-count), replace mammal biome

# %%
recs=[]
for i,f in enumerate(RASTERS):
    sci=os.path.basename(f)[:-4].replace("_"," ")
    with rasterio.open(f) as r: a=r.read(1).ravel()
    ec=Counter(cell2eco[j] for j in np.flatnonzero(a>0).tolist() if j in cell2eco)
    for eco,cnt in ec.items(): recs.append((sci,int(eco),int(cnt)))
    if (i+1)%1500==0: print(f"  {i+1}/{len(RASTERS)} rasters ({time.time()-t0:.0f}s)", flush=True)
print(f"processed → {len(recs):,} (species,ecoregion) rows  ({time.time()-t0:.0f}s)", flush=True)

con.register("me", pd.DataFrame(recs, columns=["sci","eco","cnt"]))
# the PURE range, kept apart (2026-09-26): species_ecoregions gets topped up with
# observations later (occurrence_integrate.py) — zoo sightings included — so the
# catalog's mammal range filter reads THIS table, never species_ecoregions.
con.sql("""CREATE OR REPLACE TABLE mammal_ranges AS
  SELECT n.species_id, m.eco AS ecoregion_id, m.cnt AS cells FROM me m
  JOIN name2sid n ON n.norm_name=norm(m.sci)
  JOIN species s ON s.species_id=n.species_id AND s.class='Mammalia';""")
print("mammal_ranges:", con.sql("SELECT count(*), count(DISTINCT species_id) FROM mammal_ranges").fetchone(), flush=True)
con.sql("DELETE FROM species_ecoregions WHERE species_id IN (SELECT species_id FROM species WHERE class='Mammalia');")
con.sql("""INSERT INTO species_ecoregions (species_id, ecoregion_id, occurrence_count)
  SELECT n.species_id, m.eco, m.cnt FROM me m JOIN name2sid n ON n.norm_name=norm(m.sci)
  JOIN species s ON s.species_id=n.species_id AND s.class='Mammalia';""")
r=con.sql("""SELECT count(DISTINCT se.species_id) FROM species_ecoregions se
  JOIN species s ON s.species_id=se.species_id WHERE s.class='Mammalia'""").fetchone()[0]
print(f"mammals with biome from PHYLACINE ranges: {r:,}", flush=True)
print("species_ecoregions total species:", con.sql("SELECT count(DISTINCT species_id) FROM species_ecoregions").fetchone()[0], flush=True)
con.close()
print(f"done ({time.time()-t0:.0f}s)", flush=True)
