# %% [markdown]
# # PolygroveDB — plant & fungi size from the EOL dump we already have (step 25)
#
# The all-6 catalog was 58% birds because plants/fungi had no Size — every size
# source was an animal DB. But EOL's trait dump (`data/trait_bank/traits.csv`,
# 6.2 GB, already local) carries **plant height** (TO_0000207 + vegetative
# height + FLOPO stem height) and **fungal fruiting-body/caudex height**. No new
# download, no gated TRY — just extract from the dump on disk.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

HEIGHT = (
 'http://purl.obolibrary.org/obo/TO_0000207',                                     # plant height
 'http://top-thesaurus.org/annotationInfo?viz=1&&trait=Plant_height_vegetative',  # vegetative height
 'http://purl.obolibrary.org/obo/FLOPO_0022260',                                  # stem height
 'http://eol.org/schema/terms/fruitingBodyHeight',                                # fungi
 'http://eol.org/schema/terms/caudexHeight',
)
inlist = ",".join(f"'{u}'" for u in HEIGHT)

# stream the 6.2 GB traits.csv, keep only height rows for the 5 predicates
con.sql(f"""
CREATE OR REPLACE TABLE eol_height_raw AS
SELECT scientific_name, predicate, normal_measurement, normal_units
FROM read_csv('../../data/trait_bank/traits.csv', header=true, quote='"',
              ignore_errors=true, all_varchar=true)
WHERE predicate IN ({inlist}) AND scientific_name IS NOT NULL
  AND TRY_CAST(normal_measurement AS DOUBLE) IS NOT NULL;
""")
print("raw EOL height records:", con.sql("SELECT count(*) FROM eol_height_raw").fetchone()[0])

# resolve to backbone species_id, one (max) height per species
con.sql("""
CREATE OR REPLACE TABLE plant_fungi_size AS
SELECT n.species_id,
       max(TRY_CAST(r.normal_measurement AS DOUBLE)) AS height,
       any_value(r.normal_units)                     AS units
FROM eol_height_raw r
JOIN name2sid n ON n.norm_name = norm(r.scientific_name)
GROUP BY n.species_id;
""")
n = con.sql("SELECT count(*) FROM plant_fungi_size").fetchone()[0]
print(f"resolved to backbone species with a height: {n:,}")

# %% [markdown]
# ## Coverage by kingdom — did we fill the plant/fungi size gap?

# %%
con.sql("""
SELECT s.kingdom, count(*) AS species_with_height
FROM plant_fungi_size z JOIN species s ON s.species_id=z.species_id
GROUP BY 1 ORDER BY 2 DESC
""").show()
print("=== sample ===")
con.sql("""
SELECT s.canonicalName AS species, round(z.height,2) AS height, z.units
FROM plant_fungi_size z JOIN species s ON s.species_id=z.species_id
WHERE s.canonicalName IN ('Sequoia sempervirens','Quercus robur','Helianthus annuus','Amanita muscaria')
""").show()

# %%
con.close()
