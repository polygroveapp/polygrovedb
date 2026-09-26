# %% [markdown]
# # PolygroveDB — observation cells × MONTH for deck species (S3 pass)
#
# Powers the map's month filter buttons (user, 2026-09-25): which 0.01° cells
# have records in which months. Same shape as occurrence_points_scan.py — and the
# same standing note applies: on the next snapshot refresh, fold this, the grid
# scan and the month scan into ONE pass (user, 2026-08-24).
# CC0/CC-BY only. Resumable per part-batch.

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../data/occ_points_month.duckdb")
# the first run was SIGKILLed (OOM) at 5,775/9,705 parts — cap the appetite
con.sql("SET memory_limit='6GB'; SET threads=4;")
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""CREATE OR REPLACE TABLE deck_names AS
  SELECT DISTINCT norm(s.canonicalName) k FROM pg.catalog c JOIN pg.species s USING(species_id)""")
SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
parts = sorted(r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*')").fetchall())
con.sql("CREATE TABLE IF NOT EXISTS ptsm(k VARCHAR, cx INTEGER, cy INTEGER, month INTEGER, n BIGINT)")
con.sql("CREATE TABLE IF NOT EXISTS parts_done(part VARCHAR PRIMARY KEY)")
done={r[0] for r in con.sql("SELECT part FROM parts_done").fetchall()}
todo=[p for p in parts if p not in done]
print(f"{len(parts)} parts · {len(todo)} to go", flush=True)
BATCH=25
for i in range(0,len(todo),BATCH):
    batch=todo[i:i+BATCH]; blist="["+",".join(f"'{p}'" for p in batch)+"]"
    for attempt in range(5):
        try:
            con.sql(f"""INSERT INTO ptsm
              SELECT norm(o.species), floor(o.decimallongitude*100)::INT, floor(o.decimallatitude*100)::INT,
                     o.month, count(*)
              FROM read_parquet({blist}) o
              WHERE o.species IS NOT NULL AND o.decimallatitude IS NOT NULL AND o.decimallongitude IS NOT NULL
                AND o.month IS NOT NULL
                AND o.license IN ('CC0_1_0','CC_BY_4_0')
                -- sightings only, same as occurrence_grid_full.py (2026-09-26): no
                -- fossils, museum specimens, samples or citations on the map
                AND o.basisofrecord IN ('HUMAN_OBSERVATION','MACHINE_OBSERVATION','OBSERVATION','OCCURRENCE')
                AND norm(o.species) IN (SELECT k FROM deck_names)
              GROUP BY 1,2,3,4""")
            con.executemany("INSERT OR IGNORE INTO parts_done VALUES (?)", [(p,) for p in batch])
            break
        except Exception as e:
            print(f"  batch {i//BATCH} attempt {attempt}: {e}", flush=True)
            time.sleep(20*(attempt+1))
    else:
        raise SystemExit(f"batch {i//BATCH} failed after retries")
    if (i//BATCH)%10==0:
        print(f"  {min(i+BATCH,len(todo))}/{len(todo)} parts · {(time.time()-t0)/60:.0f}m", flush=True)
# compact duplicate part-batch rows once at the end
con.sql("CREATE OR REPLACE TABLE ptsm AS SELECT k,cx,cy,month,sum(n) n FROM ptsm GROUP BY 1,2,3,4")
print(f"DONE: {con.sql('SELECT count(*) FROM ptsm').fetchone()[0]:,} rows  ({(time.time()-t0)/60:.0f}m)", flush=True)
