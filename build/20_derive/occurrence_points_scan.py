# %% [markdown]
# # PolygroveDB — near-real observation points for DECK species (final S3 pass)
#
# 0.01-degree cells (~1km) for the 8,743 deck species only, CC0/CC-BY records.
# NOTE FOR FUTURE SNAPSHOT REFRESHES: combine this with occurrence_grid_full.py and
# occurrence_month_scan.py into ONE pass — three separate 3h scans of the same parts
# was wasteful (user, 2026-08-24). Resumable per part-batch.

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../data/occ_points.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""CREATE OR REPLACE TABLE deck_names AS
  SELECT DISTINCT norm(s.canonicalName) k FROM pg.catalog c JOIN pg.species s USING(species_id)""")
SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
parts = sorted(r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*')").fetchall())
con.sql("CREATE TABLE IF NOT EXISTS pts(k VARCHAR, cx INTEGER, cy INTEGER, n BIGINT)")
con.sql("CREATE TABLE IF NOT EXISTS parts_done(part VARCHAR PRIMARY KEY)")
done={r[0] for r in con.sql("SELECT part FROM parts_done").fetchall()}
todo=[p for p in parts if p not in done]
print(f"{len(parts)} parts · {len(todo)} to go", flush=True)
BATCH=25
for i in range(0,len(todo),BATCH):
    batch=todo[i:i+BATCH]; blist="["+",".join(f"'{p}'" for p in batch)+"]"
    for attempt in range(5):
        try:
            con.sql(f"""INSERT INTO pts
              SELECT norm(o.species), floor(o.decimallongitude*100)::INT, floor(o.decimallatitude*100)::INT, count(*)
              FROM read_parquet({blist}) o
              WHERE o.species IS NOT NULL AND o.decimallatitude IS NOT NULL AND o.decimallongitude IS NOT NULL
                AND o.license IN ('CC0_1_0','CC_BY_4_0')
                -- SIGHTINGS ONLY (2026-09-27), same as the other three scans: this file
                -- draws the map's Xs, and it was the LAST place zoo/fossil/museum
                -- records survived — the Lion's Albuquerque cell was the ABQ BioPark
                AND o.basisofrecord IN ('HUMAN_OBSERVATION','MACHINE_OBSERVATION','OBSERVATION','OCCURRENCE')
                AND norm(o.species) IN (SELECT k FROM deck_names)
              GROUP BY 1,2,3""")
            con.executemany("INSERT OR IGNORE INTO parts_done VALUES (?)", [(p,) for p in batch])
            break
        except Exception as e:
            print(f"retry {attempt+1} at {i}: {str(e)[:100]}", flush=True); time.sleep(20*(attempt+1))
    else: raise SystemExit(f"FAILED at batch {i}")
    if (i//BATCH)%20==0:
        print(f"parts {len(done)+i+len(batch)}/{len(parts)}  rows {con.sql('SELECT count(*) FROM pts').fetchone()[0]:,}  ({(time.time()-t0)/60:.0f}m)", flush=True)
# STRATIFIED selection, not densest-first (fix 2026-08-25, corrected same day):
# taking a species' top 1,500 fine cells by count collapses the map to a few birding
# hotspots (the robin's densest 1,500 of 11.6M cells all sit in city parks). Instead:
# rank 0.1-deg BLOCKS by record total and keep each top block's densest 1km cell —
# geographic spread from the block ranking, precision from the cell.
# Three correctness notes, each learned the hard way:
#   - pts holds one row PER SCAN BATCH, so aggregate per-cell totals FIRST;
#   - DuckDB // truncates toward zero, so use floor() for block coords or cells
#     straddling the meridian/equator land in misaligned double-width blocks;
#   - no window over the raw table (866M rows = OOM): aggregate to blocks, then rank.
con.sql("CREATE MACRO IF NOT EXISTS fdiv(x) AS CAST(floor(x/10.0) AS INTEGER);")
con.sql("""COPY (
  WITH cells AS (SELECT k, cx, cy, sum(n)::BIGINT AS n FROM pts GROUP BY 1,2,3),
  blocks AS (
    SELECT k, fdiv(cx) AS bx, fdiv(cy) AS byy, sum(n) AS bn,
           arg_max(cx, [n, -cx, -cy]) AS cx, arg_max(cy, [n, -cx, -cy]) AS cy,
           max(n) AS cell_n
    FROM cells GROUP BY 1,2,3)
  SELECT k, cx, cy, cell_n AS n FROM (
    SELECT *, row_number() OVER (PARTITION BY k ORDER BY bn DESC, bx, byy) AS brn FROM blocks)
  WHERE brn<=1500 ORDER BY k, brn)
  TO '../../data/deck_obs_points.parquet' (FORMAT parquet)""")
r=con.sql("SELECT count(*), count(DISTINCT k) FROM read_parquet('../../data/deck_obs_points.parquet')").fetchone()
print(f"DONE: {r[0]:,} point-cells · {r[1]:,} deck species  ({(time.time()-t0)/60:.0f}m)", flush=True)
con.close()
