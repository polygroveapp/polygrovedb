# %% [markdown]
# # PolygroveDB — FULL GBIF occurrence run via grid aggregation (step: derive)
#
# The 40-part occurrence SAMPLE left most insects (black widow, swallowtail,
# ~4.9k butterflies with wingspans) without a biome, and skewed the
# commissioning order. This is the full run over all ~9,705 snapshot parts,
# license-filtered to CC0/CC-BY, WITHOUT downloading the TB-scale points:
#
#   1. stream-aggregate occurrences to a 0.1-degree grid: (species, cell, n)
#      — reads only 4 columns off S3, resumable per part-batch
#   2. map DISTINCT cells -> RESOLVE ecoregion ONCE (the PHYLACINE trick)
#   3. emit (species, ecoregion, occurrence_count) -> local parquet dump
#
# Output: ../../data/occurrence_ecoregions_full.parquet  (the reproducible,
# redistributable derived artifact). Integration into polygrove.duckdb's
# species_ecoregions is a separate quick step (kept out of this long job so
# nothing writes the live DB in the background).

# %%
import duckdb, time, math
t0=time.time()
con = duckdb.connect("../../data/occ_grid.duckdb")   # own scratch DB, resumable
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"

parts = sorted(r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*')").fetchall())
print(f"{len(parts)} parts in snapshot", flush=True)
con.sql("CREATE TABLE IF NOT EXISTS grid(species VARCHAR, cx INTEGER, cy INTEGER, n BIGINT);")
con.sql("CREATE TABLE IF NOT EXISTS parts_done(part VARCHAR PRIMARY KEY);")
done = {r[0] for r in con.sql("SELECT part FROM parts_done").fetchall()}
todo = [p for p in parts if p not in done]
print(f"{len(done)} done, {len(todo)} to go", flush=True)

BATCH = 25
for i in range(0, len(todo), BATCH):
    batch = todo[i:i+BATCH]
    blist = "[" + ",".join(f"'{p}'" for p in batch) + "]"
    for attempt in range(5):
        try:
            con.sql(f"""
              INSERT INTO grid
              SELECT species, floor(decimallongitude*10)::INT, floor(decimallatitude*10)::INT, count(*)
              FROM read_parquet({blist})
              WHERE species IS NOT NULL AND decimallatitude IS NOT NULL AND decimallongitude IS NOT NULL
                AND license IN ('CC0_1_0','CC_BY_4_0')
              GROUP BY 1,2,3;""")
            con.executemany("INSERT OR IGNORE INTO parts_done VALUES (?)", [(p,) for p in batch])
            break
        except Exception as e:
            print(f"retry {attempt+1} on batch at {i}: {str(e)[:120]}", flush=True)
            time.sleep(20*(attempt+1))
    else:
        raise SystemExit(f"FAILED batch at {i}")
    if (i//BATCH) % 20 == 0:
        gn = con.sql("SELECT count(*) FROM grid").fetchone()[0]
        print(f"parts {len(done)+i+len(batch)}/{len(parts)}  grid rows {gn:,}  ({(time.time()-t0)/60:.0f}m)", flush=True)

# %% [markdown]
# ## Compact, map cells -> ecoregions once, emit the parquet dump

# %%
con.sql("CREATE OR REPLACE TABLE grid2 AS SELECT species, cx, cy, sum(n) n FROM grid GROUP BY 1,2,3;")
print("compacted grid rows:", con.sql("SELECT count(*) FROM grid2").fetchone()[0], flush=True)

con.sql("INSTALL spatial; LOAD spatial;")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
# simplified polygons (hi-res RESOLVE ST_Contains is 100x slower; 0.01 deg tolerance
# is well under the 0.1 deg cell size)
con.sql("""CREATE OR REPLACE TABLE eco_simple AS
  SELECT ECO_ID, ST_SimplifyPreserveTopology(ST_MakeValid(geom), 0.01) AS geom FROM pg.ecoregions;""")
con.sql("""CREATE OR REPLACE TABLE cell2eco AS
  SELECT c.cx, c.cy, e.ECO_ID
  FROM (SELECT DISTINCT cx, cy FROM grid2) c
  JOIN eco_simple e ON ST_Contains(e.geom, ST_Point(c.cx/10.0+0.05, c.cy/10.0+0.05));""")
print(f"distinct cells mapped: {con.sql('SELECT count(*) FROM cell2eco').fetchone()[0]:,}  ({(time.time()-t0)/60:.0f}m)", flush=True)

con.sql("""COPY (
  SELECT g.species, ce.ECO_ID AS ecoregion_id, sum(g.n) AS occurrence_count
  FROM grid2 g JOIN cell2eco ce ON ce.cx=g.cx AND ce.cy=g.cy
  GROUP BY 1,2
) TO '../../data/occurrence_ecoregions_full.parquet' (FORMAT parquet);""")
r=con.sql("SELECT count(*), count(DISTINCT species) FROM read_parquet('../../data/occurrence_ecoregions_full.parquet')").fetchone()
print(f"DONE: {r[0]:,} (species,ecoregion) pairs, {r[1]:,} species -> data/occurrence_ecoregions_full.parquet  ({(time.time()-t0)/60:.0f}m total)", flush=True)
con.close()
