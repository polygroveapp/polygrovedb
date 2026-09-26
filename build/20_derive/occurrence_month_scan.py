# %% [markdown]
# # PolygroveDB — WHEN people see it: species × ecoregion × month (full occurrence scan)
#
# Second pass over all ~9,705 GBIF snapshot parts, keeping the MONTH column and
# aggregating straight to (species, ecoregion, month) by joining each 0.1-degree cell
# to the cell→ecoregion map the first scan already computed. Powers:
#   - the seasonal strip on a card ("when is this seen?"), locally sliced
#   - the player's own sighting as a dot on that strip
#   - the effort denominator in TIME (all species per ecoregion per month), which is
#     what makes "when people look" separable from "when it's around" — the observer-
#     bias lesson.
# License-filtered CC0/CC-BY. Resumable per part-batch.

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../data/occ_month.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
con.sql("ATTACH '../../data/occ_grid.duckdb' AS g (READ_ONLY);")   # reuse cell→ecoregion
con.sql("CREATE TABLE IF NOT EXISTS cell2eco AS SELECT * FROM g.cell2eco;")
con.sql("CREATE INDEX IF NOT EXISTS c2e ON cell2eco(cx, cy);") if False else None
SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
parts = sorted(r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*')").fetchall())
con.sql("CREATE TABLE IF NOT EXISTS sem(species VARCHAR, ecoregion_id BIGINT, month INTEGER, n BIGINT);")
con.sql("CREATE TABLE IF NOT EXISTS parts_done(part VARCHAR PRIMARY KEY);")
done = {r[0] for r in con.sql("SELECT part FROM parts_done").fetchall()}
todo = [p for p in parts if p not in done]
print(f"{len(parts)} parts · {len(done)} done · {len(todo)} to go", flush=True)

BATCH = 25
for i in range(0, len(todo), BATCH):
    batch = todo[i:i+BATCH]
    blist = "[" + ",".join(f"'{p}'" for p in batch) + "]"
    for attempt in range(5):
        try:
            con.sql(f"""
              INSERT INTO sem
              SELECT o.species, c.ECO_ID, o.month, count(*)
              FROM (SELECT species, month,
                           floor(decimallongitude*10)::INT cx, floor(decimallatitude*10)::INT cy
                    FROM read_parquet({blist})
                    WHERE species IS NOT NULL AND month IS NOT NULL
                      AND decimallatitude IS NOT NULL AND decimallongitude IS NOT NULL
                      AND license IN ('CC0_1_0','CC_BY_4_0')
                      -- sightings only, same as occurrence_grid_full.py (2026-09-26)
                      AND basisofrecord IN ('HUMAN_OBSERVATION','MACHINE_OBSERVATION','OBSERVATION','OCCURRENCE')) o
              JOIN cell2eco c ON c.cx=o.cx AND c.cy=o.cy
              GROUP BY 1,2,3;""")
            con.executemany("INSERT OR IGNORE INTO parts_done VALUES (?)", [(p,) for p in batch])
            break
        except Exception as e:
            print(f"retry {attempt+1} at {i}: {str(e)[:110]}", flush=True); time.sleep(20*(attempt+1))
    else:
        raise SystemExit(f"FAILED at batch {i}")
    if (i//BATCH) % 20 == 0:
        n=con.sql("SELECT count(*) FROM sem").fetchone()[0]
        print(f"parts {len(done)+i+len(batch)}/{len(parts)}  rows {n:,}  ({(time.time()-t0)/60:.0f}m)", flush=True)

con.sql("CREATE OR REPLACE TABLE species_eco_month AS SELECT species, ecoregion_id, month, sum(n) n FROM sem GROUP BY 1,2,3;")
con.sql("""COPY species_eco_month TO '../../data/species_eco_month.parquet' (FORMAT parquet);""")
# the TIME effort denominator: all species, per ecoregion, per month
con.sql("""COPY (SELECT ecoregion_id, month, sum(n) eff FROM species_eco_month GROUP BY 1,2)
           TO '../../data/effort_eco_month.parquet' (FORMAT parquet);""")
r=con.sql("SELECT count(*), count(DISTINCT species) FROM species_eco_month").fetchone()
print(f"DONE: {r[0]:,} (species,ecoregion,month) rows · {r[1]:,} species  ({(time.time()-t0)/60:.0f}m)", flush=True)
con.close()
