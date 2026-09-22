# %% [markdown]
# # PolygroveDB — FishBase traits for fish (step 20)
#
# The biggest remaining vertebrate gap. **FishBase** (Froese & Pauly, the
# authoritative fish database; open snapshot v25.04 on Source Cooperative S3,
# `cboettig/fishbase`, 36,132 species) gives fish what AVONET gave birds:
# - **Size** — `species.Length` (max length cm): 32,982 fish
# - **Trophic** — `estimate.Troph` (trophic level 2.0–5.3): 36,129 fish, plus
#   `ecology.FeedingType` (clean feeding categories) for the ~12k with ecology
# - **Habitat** — `species.DemersPelag` (demersal / reef-associated / pelagic …)
# - **Water type** — Fresh/Salt flags (~50/50 split, a strong discriminator)
#
# Mapped into the same niche/lifestyle vocabulary as `vert_niche` so fish join
# the convergence + niche + size questions.

# %%
import duckdb
con = duckdb.connect("../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
FB = "../data/fishbase"

# join species + estimate (1:1 on SpecCode) + ecology (dedup to 1 row/SpecCode)
con.sql(f"""
CREATE OR REPLACE TABLE fishbase_join AS
WITH eco AS (
  SELECT SpecCode, FeedingType, FoodTroph
  FROM '{FB}/ecology.parquet'
  QUALIFY row_number() OVER (PARTITION BY SpecCode ORDER BY autoctr) = 1
)
SELECT sp.SpecCode,
  trim(sp.Genus || ' ' || sp.Species)  AS sciname,
  sp.Length      AS max_length_cm,
  sp.DemersPelag AS habitat,
  CASE WHEN sp.Fresh=1 AND sp.Saltwater=1 THEN 'freshwater+marine'
       WHEN sp.Fresh=1 THEN 'freshwater'
       WHEN sp.Saltwater=1 THEN 'marine' END AS water_type,
  est.Troph      AS troph,
  eco.FeedingType
FROM '{FB}/species.parquet' sp
LEFT JOIN '{FB}/estimate.parquet' est ON est.SpecCode = sp.SpecCode
LEFT JOIN eco                          ON eco.SpecCode = sp.SpecCode;
""")

# derive niche: FeedingType where present, else bucket the trophic level
con.sql("""
CREATE OR REPLACE TABLE fish_traits AS
SELECT DISTINCT ON (n2.species_id)
  n2.species_id, j.sciname,
  CASE
    WHEN j.FeedingType IN ('grazing on aquatic plants','browsing on substrate')      THEN 'Herbivore'
    WHEN j.FeedingType IN ('selective plankton feeding','filtering plankton')        THEN 'Planktivore'
    WHEN j.FeedingType = 'hunting macrofauna (predator)'                             THEN 'Aquatic predator'
    WHEN j.FeedingType = 'feeding on dead animals (scavenger)'                        THEN 'Scavenger'
    WHEN j.FeedingType IN ('variable','plants/detritus+animals (troph. 2.2-2.79)')   THEN 'Omnivore'
    WHEN j.troph < 2.2  THEN 'Herbivore'
    WHEN j.troph < 2.8  THEN 'Omnivore'
    WHEN j.troph >= 2.8 THEN 'Aquatic predator'
  END                    AS niche,
  j.habitat, j.water_type, round(j.troph,2) AS troph, j.max_length_cm
FROM fishbase_join j
JOIN name2sid n2 ON n2.norm_name = norm(j.sciname)
ORDER BY n2.species_id, j.troph DESC NULLS LAST;
""")

n_total = con.sql("SELECT count(*) FROM fishbase_join").fetchone()[0]
n_res   = con.sql("SELECT count(*) FROM fish_traits").fetchone()[0]
print(f"FishBase species: {n_total:,}  -> resolved to backbone: {n_res:,}")

# %% [markdown]
# ## Wire fish into the unified niche pool (all fish lifestyle = Aquatic)

# %%
con.sql("""
DELETE FROM vert_niche WHERE grp='fish';
INSERT INTO vert_niche (species_id, niche, lifestyle, grp)
SELECT species_id, niche, 'Aquatic', 'fish'
FROM fish_traits WHERE niche IS NOT NULL;
""")
con.sql("SELECT grp, count(*) FROM vert_niche GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## Score it

# %%
con.sql("""
SELECT count(*) AS fish, count(niche) AS with_niche,
       count(max_length_cm) AS with_size, count(troph) AS with_troph,
       count(water_type) AS with_watertype
FROM fish_traits
""").show()
print("=== niche distribution ===")
con.sql("SELECT niche, count(*) FROM fish_traits GROUP BY 1 ORDER BY 2 DESC").show()
print("=== sample: familiar fish ===")
con.sql("""
SELECT s.canonicalName AS species, f.niche, f.habitat, f.water_type, f.troph, f.max_length_cm AS len_cm
FROM fish_traits f JOIN species s ON s.species_id=f.species_id
WHERE s.canonicalName IN ('Carcharodon carcharias','Thunnus thynnus','Amphiprion ocellaris',
  'Salmo salar','Danio rerio','Mola mola','Hippocampus kuda')
ORDER BY f.max_length_cm DESC
""").show()

# %%
con.close()
