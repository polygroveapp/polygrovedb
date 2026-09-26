# %% [markdown]
# # PolygroveDB — rebuild species_ecoregions from CLEAN parts (step: derive)
#
# species_ecoregions used to be cumulative: the sample scan (resolve_rejoin) ∪
# GARD reptiles ∪ PHYLACINE mammals ∪ occurrence_integrate's full-scan top-up. Once
# the scans changed to sightings-only (2026-09-26), the old fossil/specimen rows would
# never expire — so rebuild the table from parts that are each pure:
#   mammals  → mammal_ranges  (PHYLACINE 1.2 current, phylacine.py)
#   reptiles → reptile_ranges (GARD 1.7, gard_ranges.py)
#   everyone else → the sightings-only full scan (occurrence_ecoregions_full.parquet)
# Then occurrence_integrate.py tops mammals/reptiles up with their observations
# exactly as before (ANTI JOIN), so downstream (biome, look-alikes, food-web
# overlap) sees the same shape of table it always did.

# %%
import duckdb, time
t0 = time.time()
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
before = con.sql("SELECT count(*), count(DISTINCT species_id) FROM species_ecoregions").fetchone()

con.sql("""CREATE OR REPLACE TABLE species_ecoregions AS
  SELECT species_id, ecoregion_id, cells AS occurrence_count FROM mammal_ranges
  UNION ALL
  SELECT species_id, ecoregion_id, km2 FROM reptile_ranges
  UNION ALL
  SELECT n.species_id, o.ecoregion_id, sum(o.occurrence_count)
  FROM read_parquet('../../data/occurrence_ecoregions_full.parquet') o
  JOIN name2sid n ON n.norm_name = norm(o.species)
  JOIN species s ON s.species_id = n.species_id
  WHERE s.class NOT IN ('Mammalia','Squamata','Testudines','Crocodylia','Rhynchocephalia')
     OR (s.class = 'Mammalia' AND n.species_id NOT IN (SELECT species_id FROM mammal_ranges))
     OR (s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia')
         AND n.species_id NOT IN (SELECT species_id FROM reptile_ranges))
  GROUP BY 1, 2;""")
after = con.sql("SELECT count(*), count(DISTINCT species_id) FROM species_ecoregions").fetchone()
print(f"species_ecoregions rebuilt: {before[0]:,} → {after[0]:,} pairs | {before[1]:,} → {after[1]:,} species  ({time.time()-t0:.0f}s)", flush=True)
con.close()
