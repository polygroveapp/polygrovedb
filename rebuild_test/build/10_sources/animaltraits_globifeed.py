# %% [markdown]
# # PolygroveDB — AnimalTraits invert size + GloBI-derived feeding (step 29, CC-BY)
#
# Two clean fills for invertebrates (the sanity check flagged honeybee/monarch as
# missing size, and insects have no feeding source):
# - **AnimalTraits** (Herberstein et al. 2022, CC-BY, animaltraits.org): body mass
#   for 366 invertebrates (insects/arachnids/molluscs) → SIZE. Restricted to
#   non-Chordata so mass-in-grams never mixes into the vertebrate size units.
# - **GloBI-derived feeding**: a species' guild inferred from what it eats — prey
#   mostly plants → Herbivore, mostly animals → Carnivore, mix → Omnivore. Pure
#   GloBI (CC-BY) + GBIF taxonomy (CC-BY). Fills feeding for insects etc.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# 1. AnimalTraits — invertebrate body mass (kg → g), one per species
con.sql("""
CREATE OR REPLACE TABLE animaltraits_size AS
WITH a AS (SELECT * FROM read_csv('../../data/animaltraits/observations.csv', header=true, ignore_errors=true, sample_size=-1))
SELECT DISTINCT ON (n.species_id) n.species_id,
       round(TRY_CAST(a."body mass" AS DOUBLE)*1000, 3) AS mass_g
FROM a JOIN name2sid n ON n.norm_name = norm(a.species)
WHERE a.phylum <> 'Chordata' AND lower(a."body mass - units")='kg' AND a."body mass" IS NOT NULL
ORDER BY n.species_id, mass_g DESC;
""")
print("AnimalTraits invert sizes:", con.sql("SELECT count(*) FROM animaltraits_size").fetchone()[0])

# 2. GloBI-derived feeding from prey kingdoms
con.sql("""
CREATE OR REPLACE TABLE globi_feeding AS
WITH prey AS (
  SELECT ns.species_id AS sid, tp.kingdom AS pk, count(*) AS n
  FROM interactions i
  JOIN name2sid ns ON ns.norm_name = norm(i.sourceTaxonName)
  JOIN name2sid nt ON nt.norm_name = norm(i.targetTaxonName)
  JOIN species tp ON tp.species_id = nt.species_id
  WHERE i.interactionTypeName IN ('eats','preysOn') AND ns.species_id <> nt.species_id
  GROUP BY 1,2
), agg AS (
  SELECT sid, sum(n) FILTER (WHERE pk='Plantae') AS plant,
              sum(n) FILTER (WHERE pk='Animalia') AS animal
  FROM prey GROUP BY 1
)
SELECT sid AS species_id,
  CASE WHEN coalesce(plant,0) >= 0.8*(coalesce(plant,0)+coalesce(animal,0)) THEN 'Herbivore'
       WHEN coalesce(animal,0) >= 0.8*(coalesce(plant,0)+coalesce(animal,0)) THEN 'Carnivore'
       ELSE 'Omnivore' END AS niche
FROM agg
WHERE coalesce(plant,0)+coalesce(animal,0) > 0;
""")
r=con.sql("SELECT niche, count(*) FROM globi_feeding WHERE niche IS NOT NULL GROUP BY 1").fetchall()
print("GloBI-derived feeding:", dict(r))
# sanity: iconic insects
con.sql(r"""CREATE OR REPLACE MACRO nm(s) AS norm(s);""")
for sp in ['Apis mellifera','Danaus plexippus']:
    sid=con.sql("SELECT species_id FROM name2sid WHERE norm_name=norm(?) LIMIT 1",params=[sp]).fetchone()
    if sid:
        sz=con.sql(f"SELECT mass_g FROM animaltraits_size WHERE species_id={sid[0]}").fetchone()
        fd=con.sql(f"SELECT niche FROM globi_feeding WHERE species_id={sid[0]}").fetchone()
        print(f"  {sp}: size={sz[0] if sz else None}g  feeding={fd[0] if fd else None}")
con.close()
