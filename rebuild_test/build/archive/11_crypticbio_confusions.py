# %% [markdown]
# # PolygroveDB — CrypticBio confusion pairs (step 11)
#
# The confusion source I wrongly dismissed as "weak" without checking. CrypticBio
# (HuggingFace `gmanolache/CrypticBio`) has one row per observation with
# `scientificName` (focal) + `crypticGroup` (an ARRAY of look-alike species).
# We read a sample of parts, take distinct (focal → group), explode into directed
# pairs, resolve both ends to `species_id`, and score coverage.
#
# `confusion_strength = 1/group_size` (tighter groups = stronger confusion).
# Full build reads all 627 parts; a sample already tells us if the question is viable.

# %%
import duckdb, requests
con = duckdb.connect("../polygrove.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs;")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# reusable name → single species_id resolver
con.sql("""CREATE OR REPLACE TABLE name2sid AS
  SELECT norm_name, min(accepted_id) AS species_id FROM gbif_names GROUP BY 1;""")

S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1"})
parts=S.get("https://huggingface.co/api/datasets/gmanolache/CrypticBio/parquet",timeout=30).json()['default']['train']
sample = parts[:40]
sample_sql = "[" + ",".join(f"'{u}'" for u in sample) + "]"
print(f"reading {len(sample)}/{len(parts)} CrypticBio parts")

# %% [markdown]
# ## Distinct focal→group, explode to directed pairs, resolve to species_id

# %%
con.sql(f"""
CREATE OR REPLACE TEMP TABLE cb AS
SELECT DISTINCT scientificName AS focal, crypticGroup AS grp
FROM read_parquet({sample_sql})
WHERE scientificName IS NOT NULL AND len(crypticGroup) > 0;
""")
print("distinct focal species in sample:", con.sql("SELECT count(*) FROM cb").fetchone()[0])

con.sql("""
CREATE OR REPLACE TABLE species_confusions AS
SELECT DISTINCT
       n1.species_id             AS species_id,
       n2.species_id             AS confused_with_species_id,
       round(1.0/len(cb.grp), 4) AS confusion_strength,
       'crypticbio'              AS source
FROM cb, UNNEST(cb.grp) AS t(partner)
JOIN name2sid n1 ON n1.norm_name = norm(cb.focal)
JOIN name2sid n2 ON n2.norm_name = norm(t.partner)
WHERE n1.species_id <> n2.species_id;
""")

# %% [markdown]
# ## Score it — coverage and partners per species (the question viability)

# %%
con.sql("""
SELECT count(*) AS directed_pairs,
       count(DISTINCT species_id) AS species_with_confusions,
       round(avg(cnt),1) AS avg_partners
FROM (SELECT species_id, count(*) cnt FROM species_confusions GROUP BY 1)
""").show()

print("sample: species and who they're confused with (with names)")
con.sql("""
SELECT s1.canonicalName AS species, s2.canonicalName AS confused_with, c.confusion_strength AS strength
FROM species_confusions c
JOIN species s1 ON s1.species_id=c.species_id
JOIN species s2 ON s2.species_id=c.confused_with_species_id
ORDER BY random() LIMIT 8
""").show()

# %%
con.sql("SHOW TABLES").show()
con.close()
