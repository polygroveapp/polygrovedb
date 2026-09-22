# %% [markdown]
# # PolygroveDB — WCVP native origin for plants (step 17)
#
# Origin was ❌ (establishmentMeans null in GBIF occurrences). WCVP (Kew's World
# Checklist of Vascular Plants, CC BY) has authoritative **native ranges** for
# plants: per (plant, botanical area) with an `introduced` flag. Native origin =
# the continents where `introduced=0`. This does for plants what AVONET did for
# birds — resurrects a ❌ question for a big slice of the substrate.

# %%
import duckdb, subprocess, os
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
DATA="../../data"; SCRATCH="../_scratch"; os.makedirs(SCRATCH,exist_ok=True)

# extract the two pipe-delimited CSVs
subprocess.run(f"unzip -o -p {DATA}/wcvp.zip wcvp_names.csv > {SCRATCH}/wcvp_names.csv",shell=True,check=True)
subprocess.run(f"unzip -o -p {DATA}/wcvp.zip wcvp_distribution.csv > {SCRATCH}/wcvp_dist.csv",shell=True,check=True)

# accepted species names
con.sql(f"""
CREATE OR REPLACE TABLE wcvp_names AS
SELECT plant_name_id, taxon_name, taxon_status, taxon_rank
FROM read_csv('{SCRATCH}/wcvp_names.csv', delim='|', header=true, quote='', ignore_errors=true)
WHERE taxon_status='Accepted' AND lower(taxon_rank)='species';
""")
# native distribution → continent
con.sql(f"""
CREATE OR REPLACE TABLE wcvp_dist AS
SELECT plant_name_id, continent
FROM read_csv('{SCRATCH}/wcvp_dist.csv', delim='|', header=true, quote='', ignore_errors=true)
WHERE introduced=0 AND extinct=0 AND location_doubtful=0 AND continent IS NOT NULL;
""")
os.remove(f"{SCRATCH}/wcvp_names.csv"); os.remove(f"{SCRATCH}/wcvp_dist.csv")

# join names+dist, resolve to backbone species_id → native origin (continent)
con.sql("""
CREATE OR REPLACE TABLE species_native_origin AS
SELECT DISTINCT n2.species_id, d.continent AS native_continent
FROM wcvp_dist d
JOIN wcvp_names w ON w.plant_name_id = d.plant_name_id
JOIN name2sid n2 ON n2.norm_name = norm(w.taxon_name);
""")
con.sql("""
SELECT count(DISTINCT species_id) AS plant_species_with_origin,
       count(*) AS species_continent_pairs
FROM species_native_origin
""").show()

# %% [markdown]
# ## Score it — is this a good Origin question?

# %%
con.sql("SELECT native_continent, count(DISTINCT species_id) AS species FROM species_native_origin GROUP BY 1 ORDER BY 2 DESC").show()
print("=== sample: plant → native origin ===")
con.sql("""
SELECT s.canonicalName AS plant, string_agg(o.native_continent, ', ') AS native_to
FROM species_native_origin o JOIN species s ON s.species_id=o.species_id
WHERE s.canonicalName IN ('Welwitschia mirabilis','Ginkgo biloba','Sequoia sempervirens','Adansonia digitata','Rafflesia arnoldii')
GROUP BY 1
""").show()

# %%
con.close()
