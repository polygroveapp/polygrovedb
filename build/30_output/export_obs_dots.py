# %% [markdown]
# # PolygroveDB — per-card observation dots for the range map
#
# NOW AT 0.01 deg (~1 km): the dedicated deck-species scan (deck_obs_points.parquet,
# top 1,500 cells/card) replaces the coarse 0.1-deg grid — visually these read as real
# observation points. Still cells, not raw GPS: GBIF's own sensitive-species
# generalization applies upstream, and 1 km is the display floor we choose on top.
# Sharded djb2(sci)%256 like the dossiers; coordinates are cell indices x100
# (explorer divides by 100). Falls back to the 0.1-deg grid for any deck card the
# fine scan missed (expert-range species with few open-license records).

# %%
import duckdb, json, os, time
from collections import defaultdict
t0=time.time()
con=duckdb.connect()
con.sql("ATTACH '../../data/occ_grid.duckdb' AS og (READ_ONLY); ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql(r"""CREATE OR REPLACE TEMP MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

rows=con.sql("""
WITH fine AS (
  SELECT s.canonicalName sci, p.cx, p.cy, p.n
  FROM read_parquet('../../data/deck_obs_points.parquet') p
  JOIN pg.name2sid nm ON nm.norm_name = p.k
  JOIN pg.catalog c ON c.species_id = nm.species_id
  JOIN pg.species s ON s.species_id = c.species_id),
coarse AS (
  SELECT sci, cx*10 cx, cy*10 cy, n FROM (
    SELECT s.canonicalName sci, g.cx, g.cy, sum(g.n) n,
           row_number() OVER (PARTITION BY s.canonicalName ORDER BY sum(g.n) DESC, g.cx, g.cy) rn
    FROM og.grid2 g
    JOIN pg.name2sid nm ON nm.norm_name = norm(g.species)
    JOIN pg.catalog c ON c.species_id = nm.species_id
    JOIN pg.species s ON s.species_id = c.species_id
    WHERE nm.species_id NOT IN (SELECT c2.species_id FROM read_parquet('../../data/deck_obs_points.parquet') p2
                                JOIN pg.name2sid n2 ON n2.norm_name=p2.k JOIN pg.catalog c2 ON c2.species_id=n2.species_id)
    GROUP BY 1,2,3)
  WHERE rn <= 1200)
SELECT * FROM fine UNION ALL SELECT * FROM coarse ORDER BY sci, n DESC, cx, cy""").fetchall()
print(f"{len(rows):,} cells for the deck  ({time.time()-t0:.0f}s)", flush=True)

def djb2(s):
    h=5381
    for ch in s: h=((h*33)+ord(ch))&0xffffffff
    return h%256
shards=defaultdict(dict)
for sci,cx,cy,n in rows:
    shards[djb2(sci)].setdefault(sci,[]).append([int(cx),int(cy),int(n)])
outdir="../../explorer/data/obs"; os.makedirs(outdir,exist_ok=True)
for k,d in shards.items():
    json.dump(d, open(f"{outdir}/{k}.json","w"), separators=(',',':'))
import subprocess
print(f"wrote {len(shards)} shards  ({time.time()-t0:.0f}s)")
