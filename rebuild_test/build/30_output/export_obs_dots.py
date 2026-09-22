# %% [markdown]
# # PolygroveDB — per-card observation dots for the range map
#
# The full-occurrence scan's intermediate grid (data/occ_grid.duckdb, 132.5M
# rows of 0.1-degree cells) doubles as a dot map: each cell = "this species was
# actually recorded here", count-weighted. Export the top ~1,200 cells per deck
# card, sharded by djb2(sci)%256 like the dossiers, for on-demand fetch.
# Cells, not raw GPS points — 0.1 deg (~11 km) renders as a dot at map scale
# and is friendlier to sensitive-species location precision anyway.

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
SELECT sci, cx, cy, n FROM (
  SELECT s.canonicalName sci, g.cx, g.cy, sum(g.n) n,
         row_number() OVER (PARTITION BY s.canonicalName ORDER BY sum(g.n) DESC) rn
  FROM og.grid2 g
  JOIN pg.name2sid nm ON nm.norm_name = norm(g.species)
  JOIN pg.catalog c ON c.species_id = nm.species_id
  JOIN pg.species s ON s.species_id = c.species_id
  GROUP BY 1,2,3)
WHERE rn <= 1200""").fetchall()
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
