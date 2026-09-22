# %% [markdown]
# # PolygroveDB — occurrences → species_ecoregions (step 6)
#
# The "where does each species live" layer. We query the **GBIF occurrence
# Parquet snapshot on S3 in place** (no download), spatial-join the points to
# the WWF ecoregion polygons, and aggregate to (species, ecoregion).
#
# The full snapshot is ~9,705 Parquet parts (~200 GB). This notebook runs a
# **bounded sample** of parts so it completes live; the full build is the same
# query over `glob(.../*)` with no LIMIT — best run in-region (us-east-1) as a
# batch job. Column names in the GBIF Parquet are lowercase.

# %%
import duckdb
con = duckdb.connect("../polygrove.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-east-1';")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

SNAPSHOT = "s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
N_PARTS  = 40                     # sample size — raise toward 9705 for the full build

# %% [markdown]
# ## Pull a sample of georeferenced species occurrences

# %%
parts = [r[0] for r in con.sql(f"SELECT file FROM glob('{SNAPSHOT}/*') LIMIT {N_PARTS}").fetchall()]
parts_sql = "[" + ",".join(f"'{p}'" for p in parts) + "]"
con.sql(f"""
CREATE OR REPLACE TEMP TABLE occ AS
SELECT species, decimallatitude AS lat, decimallongitude AS lon
FROM read_parquet({parts_sql})
WHERE species IS NOT NULL
  AND decimallatitude IS NOT NULL AND decimallongitude IS NOT NULL
  AND lower(taxonrank) = 'species'
  AND lower(occurrencestatus) = 'present';
""")
print(f"sampled {N_PARTS} parts → occurrence points:",
      con.sql("SELECT count(*) FROM occ").fetchone()[0])

# %% [markdown]
# ## Spatial-join points → ecoregions (R-tree indexed), aggregate, resolve to species_id

# %%
con.sql("CREATE INDEX IF NOT EXISTS eco_rtree ON ecoregions USING RTREE (geom);")
con.sql("""
CREATE OR REPLACE TABLE species_ecoregions AS
SELECT gn.accepted_id AS species_id,
       e.ECO_ID       AS ecoregion_id,
       count(*)       AS occurrence_count
FROM occ o
JOIN ecoregions e ON ST_Contains(e.geom, ST_Point(o.lon, o.lat))
JOIN gbif_names gn ON gn.norm_name = norm(o.species)
GROUP BY 1, 2;
""")
con.sql("""
SELECT count(*) pairs,
       count(DISTINCT species_id) species,
       count(DISTINCT ecoregion_id) ecoregions_hit
FROM species_ecoregions
""").show()

# %% [markdown]
# ## Sanity check — species richness per ecoregion (sample), with names

# %%
con.sql("""
SELECT ec.ECO_NAME, ec.REALM, count(DISTINCT se.species_id) AS species
FROM species_ecoregions se
JOIN (SELECT DISTINCT ECO_ID, ECO_NAME, REALM FROM ecoregions) ec ON ec.ECO_ID = se.ecoregion_id
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10
""").show()

# %% [markdown]
# ## Scaling note
# This used a **sample** (`N_PARTS`). The production build removes the LIMIT and
# scans all ~9,705 parts — same query. Do it from an us-east-1 VM (no egress,
# fast S3 reads); the spatial join with the R-tree index scales linearly. Then
# apply the Phase-3 rule: drop (species, ecoregion) pairs with occurrence_count < 5.

# %%
con.sql("SHOW TABLES").show()
con.close()
