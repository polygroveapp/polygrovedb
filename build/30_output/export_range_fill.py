# %% [markdown]
# # PolygroveDB — the range FILL layer: every ecoregion a species was recorded in
#
# The map used to fill a binary top-60 list, so a naturalized foothold holding 0.5% of
# a plant's records lit up as brightly as its Japanese core, while genuinely-recorded
# Philippine islands showed dots over empty land (they fell past rank 60, or under the
# >=5-records floor). Fix (user, 2026-08-25): "do it entirely by how non-transparent the
# green is by how many dots there are — but put every sighting."
#
# So: NO cutoffs here. Every ecoregion with >=1 record, weighted by its share, and the
# explorer renders opacity from the weight. This is the DISPLAY layer only —
# species_ecoregions keeps its >=5 floor for quiz answers, biome and eligibility, where
# a single stray record shouldn't assert anything. Display shows all; assertion stays strict.

# %%
import duckdb, json, os, time
from collections import defaultdict
t0=time.time()
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql(r"""CREATE TEMP MACRO norm(s) AS lower(array_to_string(list_filter(string_split(
  regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
# species_ecoregions (occurrences >=5 + GARD/PHYLACINE expert ranges) UNION the sub-5
# occurrence tail it excludes — union keeps expert ranges for reptiles/mammals whose
# cards aren't occurrence-driven at all.
rows=con.sql("""
WITH scope AS (
  -- deck cards PLUS the explorer's pool.json species (>=4 of 5 facts): the
  -- Full-database pages get a range map too (user, 2026-09-10, via basil)
  SELECT species_id FROM pg.catalog
  UNION
  SELECT species_id FROM pg.card_pool
  WHERE has_feeding+has_size+has_foodweb+has_slot5+has_biome >= 4),
base AS (
  SELECT s.canonicalName sci, se.ecoregion_id eco, se.occurrence_count n
  FROM pg.species_ecoregions se JOIN scope c USING(species_id)
  JOIN pg.species s ON s.species_id=se.species_id),
tail AS (
  SELECT s.canonicalName sci, o.ecoregion_id eco, o.occurrence_count n
  FROM read_parquet('../../data/occurrence_ecoregions_full.parquet') o
  JOIN pg.name2sid nm ON nm.norm_name=norm(o.species)
  JOIN scope c ON c.species_id=nm.species_id
  JOIN pg.species s ON s.species_id=c.species_id),
all_rows AS (SELECT sci, eco, max(n) n FROM (SELECT * FROM base UNION ALL SELECT * FROM tail) GROUP BY 1,2)
-- OUTLIER RULE (user, 2026-09-08): the FILL asserts "part of its range", so a stray
-- handful of records doesn't earn it — 7 zoo/museum cougar records were painting
-- Europe, Greenland AND Antarctica (one 'Rock and Ice' polygon covers both poles).
-- An ecoregion fills only with >=5 records or >=0.5% of the species' total (5 matches
-- the assertion layer's historic floor; share keeps rare-but-real regions of sparse species); the DOTS
-- still show every sighting, so nothing is hidden — a lone record is a faint gold
-- point you can wonder about, not a painted continent.
SELECT sci, eco, n, n*1000.0/sum(n) OVER (PARTITION BY sci) AS permille
FROM all_rows
QUALIFY n>=5 OR n >= 0.005*sum(n) OVER (PARTITION BY sci)
ORDER BY sci, n DESC, eco""").fetchall()
print(f"{len(rows):,} (species, ecoregion) fill rows  ({time.time()-t0:.0f}s)", flush=True)
def djb2(s):
    h=5381
    for ch in s: h=((h*33)+ord(ch))&0xffffffff
    return h%256
shards=defaultdict(dict)
for sci,eco,n,pm in rows:
    shards[djb2(sci)].setdefault(sci,[]).append([int(eco), max(1,round(pm))])
outdir="../../explorer/data/range"; os.makedirs(outdir,exist_ok=True)
for sh,data in shards.items():
    json.dump(data, open(f"{outdir}/{sh}.json","w"), separators=(',',':'))
per=[len(v) for d in shards.values() for v in d.values()]
print(f"wrote {len(shards)} shards · {sum(per):,} pairs · median {sorted(per)[len(per)//2]} ecoregions/card, max {max(per)}  ({time.time()-t0:.0f}s)")
con.close()
