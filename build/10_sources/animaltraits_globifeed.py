# %% [markdown]
# # PolygroveDB — AnimalTraits invert size + GloBI-derived feeding (step 29, CC-BY)
#
# Two clean fills for invertebrates (the sanity check flagged honeybee/monarch as
# missing size, and insects have no feeding source):
# - **AnimalTraits** (Herberstein et al. 2022, CC-BY, animaltraits.org): body mass
#   for 366 invertebrates (insects/arachnids/molluscs) → SIZE. Restricted to
#   non-Chordata so mass-in-grams never mixes into the vertebrate size units.
# - **GloBI-derived feeding**: a species' guild inferred from what it eats — food
#   mostly fungi → Decomposer, mostly plants → Herbivore, mostly animals → Carnivore, mix → Omnivore. Pure
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
# EVERY FOOD NAME COUNTS (2026-10-07): a record's target is often a genus,
# family or order ("Agaricales", "Insecta"), and those used to be dropped
# because only species-rank names resolved. Now a target that is not one of
# our species is matched against the higher taxa our species table knows
# (genus … phylum, kingdom) — unambiguous names only — for its kingdom. The
# banana slug's 19 mushroom records are what this was for.
con.sql("""
CREATE OR REPLACE TEMP TABLE hk AS
SELECT lower(nm) nm, any_value(kingdom) kingdom FROM (
  SELECT genus nm, kingdom FROM species WHERE genus IS NOT NULL UNION ALL SELECT family, kingdom FROM species WHERE family IS NOT NULL
  UNION ALL SELECT "order", kingdom FROM species WHERE "order" IS NOT NULL UNION ALL SELECT class, kingdom FROM species WHERE class IS NOT NULL
  UNION ALL SELECT phylum, kingdom FROM species WHERE phylum IS NOT NULL UNION ALL SELECT kingdom, kingdom FROM species)
GROUP BY 1 HAVING count(DISTINCT kingdom)=1;
CREATE OR REPLACE TEMP TABLE tnames AS SELECT DISTINCT targetTaxonName tn FROM interactions WHERE interactionTypeName IN ('eats','preysOn');
CREATE OR REPLACE TEMP TABLE tmap AS
SELECT t.tn, any_value(nt.species_id) sid, any_value(tp.kingdom) kingdom FROM tnames t
JOIN name2sid nt ON nt.norm_name = norm(t.tn) JOIN species tp ON tp.species_id = nt.species_id GROUP BY 1;
INSERT INTO tmap SELECT t.tn, NULL, hk.kingdom FROM tnames t JOIN hk ON hk.nm = lower(trim(t.tn)) WHERE t.tn NOT IN (SELECT tn FROM tmap);
""")
con.sql("""
CREATE OR REPLACE TABLE globi_feeding AS
WITH prey AS (
  SELECT ns.species_id AS sid, m.kingdom AS pk, count(*) AS n
  FROM interactions i
  JOIN name2sid ns ON ns.norm_name = norm(i.sourceTaxonName)
  JOIN tmap m ON m.tn = i.targetTaxonName
  WHERE i.interactionTypeName IN ('eats','preysOn') AND (m.sid IS NULL OR ns.species_id <> m.sid)
  GROUP BY 1,2
), agg AS (
  SELECT sid, coalesce(sum(n) FILTER (WHERE pk='Plantae'),0) AS plant,
              coalesce(sum(n) FILTER (WHERE pk='Animalia'),0) AS animal,
              coalesce(sum(n) FILTER (WHERE pk='Fungi'),0) AS fungi      -- lichens are Fungi too
  FROM prey GROUP BY 1
)
-- DECOMPOSERS (user, 2026-10-07: the California banana slug came out Carnivore —
-- its 19 mushroom and 3 lichen records were not counted at all, leaving 5 records
-- of it on a dead mouse and a dead woodpecker). A species whose recorded food is
-- mostly fungi is a decomposer in the game's five-role sense; the plant/animal
-- split is judged only on what is left.
SELECT sid AS species_id,
  CASE WHEN fungi >= 0.5*(plant+animal+fungi) THEN 'Decomposer'
       WHEN plant >= 0.8*(plant+animal) THEN 'Herbivore'
       WHEN animal >= 0.8*(plant+animal) THEN 'Carnivore'
       ELSE 'Omnivore' END AS niche
FROM agg
WHERE plant+animal+fungi > 0;
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
