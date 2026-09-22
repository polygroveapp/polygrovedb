# %% [markdown]
# # PolygroveDB — RESOLVE ecoregions re-join (step 26, license cleanup)
#
# WWF ecoregions were CC-BY-NC. Swapped the `ecoregions` table to **RESOLVE
# Ecoregions 2017 (CC-BY 4.0)**. This rebuilds `species_ecoregions` against it,
# and (a) filters GBIF occurrences to **CC0/CC-BY licenses only** (dropping
# CC-BY-NC records), (b) uses **GARD reptile range polygons (CC0)** for reptiles
# instead of biased occurrence points. Everything here is CC-BY/CC0.

# %%
import duckdb, time
con = duckdb.connect("../../polygrove.duckdb")
con.sql("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("DROP INDEX IF EXISTS eco_rtree;")
con.sql("CREATE INDEX eco_rtree ON ecoregions USING RTREE (geom);")
t0=time.time()

# 1. occurrences × RESOLVE — license-filtered to CC0 / CC-BY only.
# DUMP-FIRST: the S3 scan's aggregate is cached as a versioned parquet; while the cache
# exists this step is fully offline (byte-determinism across rebuilds). Delete the
# parquet (and bump SNAPSHOT) to refresh from a newer GBIF snapshot.
SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
CACHE = "../../data/resolve_occ_pairs_2026-08-01.parquet"
import os
if os.path.exists(CACHE):
    con.sql(f"""CREATE OR REPLACE TABLE species_ecoregions AS
      SELECT species_id, ecoregion_id, occurrence_count FROM read_parquet('{CACHE}')""")
    print(f"species_ecoregions from cache {CACHE}  ({time.time()-t0:.0f}s)", flush=True)
else:
    parts = [r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*') ORDER BY 1 LIMIT 40").fetchall()]
    parts_sql = "[" + ",".join(f"'{p}'" for p in parts) + "]"
    con.sql(f"""
    CREATE OR REPLACE TEMP TABLE occ AS
    SELECT species, decimallatitude AS lat, decimallongitude AS lon
    FROM read_parquet({parts_sql})
    WHERE species IS NOT NULL AND decimallatitude IS NOT NULL AND decimallongitude IS NOT NULL
      AND lower(taxonrank) = 'species' AND lower(occurrencestatus) = 'present'
      AND license IN ('CC0_1_0','CC_BY_4_0');
    """)
    print(f"license-clean occurrence points: {con.sql('SELECT count(*) FROM occ').fetchone()[0]:,}  ({time.time()-t0:.0f}s)", flush=True)
    con.sql("""
    CREATE OR REPLACE TABLE species_ecoregions AS
    SELECT gn.accepted_id AS species_id, e.ECO_ID AS ecoregion_id, count(*) AS occurrence_count
    FROM occ o
    JOIN ecoregions e ON ST_Contains(e.geom, ST_Point(o.lon, o.lat))
    JOIN gbif_names gn ON gn.norm_name = norm(o.species)
    GROUP BY 1,2 HAVING count(*) >= 5;
    """)
    con.sql(f"COPY (SELECT * FROM species_ecoregions ORDER BY species_id, ecoregion_id) TO '{CACHE}' (FORMAT parquet)")
    print(f"cached to {CACHE}", flush=True)
print(f"species_ecoregions (occurrences, CC0/CC-BY): "
      f"{con.sql('SELECT count(DISTINCT species_id) FROM species_ecoregions').fetchone()[0]:,} species  ({time.time()-t0:.0f}s)", flush=True)

# %% [markdown]
# ## GARD reptile ranges (CC0) × RESOLVE — replace reptiles' occurrence biome with range biome

# %%
# ST_MakeValid on BOTH sides: GARD (and hi-res RESOLVE) polygons contain invalid
# rings that throw TopologyException mid-join otherwise (caught by the clean-rebuild test)
con.sql("""CREATE OR REPLACE TEMP TABLE gard_eco AS
WITH g AS (SELECT binomial, ST_MakeValid(geom) AS geom FROM ST_Read('../../data/gard/Gard_1_7_ranges.shp')),
     e AS (SELECT ECO_ID, ST_MakeValid(geom) AS geom FROM ecoregions)
SELECT g.binomial, e.ECO_ID, ST_Area_Spheroid(ST_Intersection(g.geom, e.geom)) AS overlap
FROM g JOIN e ON ST_Intersects(g.geom, e.geom);""")
print(f"GARD range×ecoregion overlaps: {con.sql('SELECT count(*) FROM gard_eco').fetchone()[0]:,}  ({time.time()-t0:.0f}s)", flush=True)

# reptiles: drop occurrence-derived rows, insert range-derived (weight = overlap area, m^2 → km^2)
con.sql("""DELETE FROM species_ecoregions WHERE species_id IN
  (SELECT species_id FROM species WHERE class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia'));""")
con.sql("""
INSERT INTO species_ecoregions (species_id, ecoregion_id, occurrence_count)
SELECT n.species_id, ge.ECO_ID, greatest((sum(ge.overlap)/1e6)::bigint, 1)
FROM gard_eco ge JOIN name2sid n ON n.norm_name = norm(ge.binomial)
WHERE ge.overlap > 0 AND NOT isnan(ge.overlap)   -- MakeValid can yield degenerate pieces with NaN area
GROUP BY n.species_id, ge.ECO_ID;   -- one row per (species, ecoregion); sum multi-polygon overlap
""")
print("reptiles now from GARD ranges. final species_ecoregions:", flush=True)
con.sql("""SELECT count(DISTINCT species_id) species, count(*) pairs FROM species_ecoregions""").show()
con.close()
print(f"done ({time.time()-t0:.0f}s)", flush=True)
