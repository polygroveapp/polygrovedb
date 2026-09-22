# %% [markdown]
# # PolygroveDB — trait discovery (step 14)
#
# We only mined 3 of EOL's hundreds of trait types. This scans the *entire*
# traits dump, ranks every predicate by how many species carry it, and resolves
# readable names — surfacing question candidates we haven't considered. Same for
# GloBI's interaction types and GBIF's other occurrence columns.

# %%
import duckdb, subprocess, io, csv, os
con = duckdb.connect("../polygrove.duckdb")
DATA="../data"; SCRATCH="../_scratch"; os.makedirs(SCRATCH,exist_ok=True); csv.field_size_limit(1<<24)

# %% [markdown]
# ## The full EOL trait menu — every predicate by species coverage

# %%
# extract traits.csv once, aggregate predicate -> distinct species, drop
subprocess.run(f"unzip -o -p {DATA}/eol_traits_all.zip trait_bank/traits.csv > {SCRATCH}/traits.csv",shell=True,check=True)
con.sql(f"""
CREATE OR REPLACE TABLE trait_menu AS
SELECT predicate, count(DISTINCT scientific_name) AS species, count(*) AS records
FROM read_csv('{SCRATCH}/traits.csv', header=true, sample_size=200000, ignore_errors=true)
WHERE predicate IS NOT NULL
GROUP BY 1;
""")
os.remove(f"{SCRATCH}/traits.csv")

# readable names from terms.csv
subprocess.run(f"unzip -o -p {DATA}/eol_traits_all.zip trait_bank/terms.csv > {SCRATCH}/terms.csv",shell=True,check=True)
con.sql(f"""CREATE OR REPLACE TABLE eol_terms AS
  SELECT uri, name FROM read_csv('{SCRATCH}/terms.csv', header=true, ignore_errors=true) WHERE type='predicate' OR type IS NOT NULL;""")
os.remove(f"{SCRATCH}/terms.csv")

print("=== top EOL traits by species coverage (candidate questions) ===")
con.sql("""
SELECT coalesce(t.name, regexp_replace(m.predicate,'^.*/','')) AS trait,
       m.species
FROM trait_menu m LEFT JOIN eol_terms t ON t.uri = m.predicate
WHERE m.species > 3000
ORDER BY m.species DESC LIMIT 35
""").show(max_rows=35)

# %% [markdown]
# ## GloBI — every interaction type (each is a potential question)

# %%
con.sql("""
SELECT interactionTypeName AS interaction, count(DISTINCT sourceTaxonName) AS source_species
FROM read_csv('../data/globi_interactions.tsv.gz', delim='\t', header=true, sample_size=100000, ignore_errors=true)
GROUP BY 1 ORDER BY 2 DESC LIMIT 20
""").show(max_rows=20)

# %%
con.close()
