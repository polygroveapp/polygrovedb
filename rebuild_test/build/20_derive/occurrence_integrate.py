# %% [markdown]
# # PolygroveDB — integrate the FULL occurrence run into species_ecoregions
#
# occurrence_grid_full.py produced data/occurrence_ecoregions_full.parquet:
# 6.8M (species, ecoregion, count) pairs over 1.09M species — all 9,705 GBIF
# snapshot parts, license-filtered CC0/CC-BY, grid-aggregated (0.1 deg).
#
# Integration rule: expert ranges already in species_ecoregions (PHYLACINE
# mammals, GARD reptiles, TetrapodTraits centroids) are KEPT — occurrences ADD
# every (species, ecoregion) pair not already present, with real observation
# counts as weights. That fills birds/plants/insects into every ecoregion where
# people actually record them (the "local deck" fix) and catches introduced
# ranges the expert maps omit.

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

before = con.sql("SELECT count(*), count(DISTINCT species_id) FROM species_ecoregions").fetchone()
con.sql("""
INSERT INTO species_ecoregions (species_id, ecoregion_id, occurrence_count)
SELECT n.species_id, o.ecoregion_id, sum(o.occurrence_count)
FROM read_parquet('../../data/occurrence_ecoregions_full.parquet') o
JOIN name2sid n ON n.norm_name = norm(o.species)
ANTI JOIN species_ecoregions se
  ON se.species_id = n.species_id AND se.ecoregion_id = o.ecoregion_id
GROUP BY 1, 2;
""")
after = con.sql("SELECT count(*), count(DISTINCT species_id) FROM species_ecoregions").fetchone()
print(f"species_ecoregions: {before[0]:,} → {after[0]:,} pairs | {before[1]:,} → {after[1]:,} species  ({time.time()-t0:.0f}s)")
con.close()
