# %% [markdown]
# # PolygroveDB — what you are likely to see HERE (the app's PolygroveDB tab, 2026-10-06)
#
# Two rankings of the deck for the tab's Pin / Tent filters:
# - data/eco_species/<eid>.json — every deck card recorded in that ecoregion,
#   [[slug, records], …] most-recorded first (pg.species_ecoregions)
# - data/near/<bx>_<by>.json — 5°×5° blocks of 1° cells; each cell lists the
#   deck cards recorded in it, [[slug, records], …] most-recorded first, top 400
#   (data/deck_obs_points.parquet, the obs-dots source, 0.01° points)
# Both are the same GBIF occurrence data the range maps and ✕ cells already show.

# %%
import duckdb, json, os, time
from collections import defaultdict
t0=time.time()
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql(r"""CREATE TEMP MACRO norm(s) AS lower(array_to_string(list_filter(string_split(
  regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
cards={c['species_id']:c['id'] for c in json.load(open('../../explorer/data/catalog.json'))}
con.sql("CREATE TEMP TABLE deck(species_id BIGINT, slug VARCHAR)")
con.executemany("INSERT INTO deck VALUES (?,?)", list(cards.items()))

# ── tent: by ecoregion
rows=con.sql("""SELECT se.ecoregion_id, d.slug, se.occurrence_count
  FROM pg.species_ecoregions se JOIN deck d USING(species_id)
  ORDER BY se.ecoregion_id, se.occurrence_count DESC""").fetchall()
by=defaultdict(list)
for eid,slug,n in rows: by[int(eid)].append([slug,int(n)])
os.makedirs('../../explorer/data/eco_species',exist_ok=True)
for eid,lst in by.items(): json.dump(lst,open(f'../../explorer/data/eco_species/{eid}.json','w'),separators=(',',':'))
print(f"eco_species: {len(by)} ecoregions, {len(rows):,} rows  ({time.time()-t0:.0f}s)",flush=True)

# ── pin: by 1° cell, in 5° blocks
rows=con.sql("""SELECT floor(p.cx/100.0)::INT cx1, floor(p.cy/100.0)::INT cy1, d.slug, sum(p.n) n
  FROM read_parquet('../../data/deck_obs_points.parquet') p
  JOIN pg.name2sid nm ON nm.norm_name=p.k
  JOIN deck d ON d.species_id=nm.species_id
  GROUP BY 1,2,3 ORDER BY 1,2,4 DESC""").fetchall()
blocks=defaultdict(lambda: defaultdict(list))
for cx,cy,slug,n in rows:
    cell=blocks[(cx//5,cy//5)][f"{cx}_{cy}"]
    if len(cell)<400: cell.append([slug,int(n)])
os.makedirs('../../explorer/data/near',exist_ok=True)
for (bx,by_),cells in blocks.items(): json.dump(cells,open(f'../../explorer/data/near/{bx}_{by_}.json','w'),separators=(',',':'))
print(f"near: {len(blocks)} blocks, {sum(len(c) for c in blocks.values()):,} cells, {len(rows):,} rows  ({time.time()-t0:.0f}s)",flush=True)
