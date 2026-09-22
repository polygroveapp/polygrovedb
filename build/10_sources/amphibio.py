# %% [markdown]
# # PolygroveDB — AmphiBIO traits for amphibians (step 19)
#
# Amphibians had no scientific-grade trait source (birds→AVONET, mammals→Elton,
# plants→WCVP). **AmphiBIO** (Oliveira et al. 2017, *Scientific Data*, CC BY,
# figshare 4644424, 6,776 species) is the amphibian equivalent: binary diet
# flags (Leaves…Vert), habitat flags (Fossorial/Terrestrial/Aquatic/Arboreal),
# diel, body mass & size, seasonality. This maps them into the SAME niche/
# lifestyle vocabulary as `vert_niche` so amphibians join the convergence pool.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# raw AmphiBIO; NA -> null; flags are '1' when present
con.sql("""
CREATE OR REPLACE TABLE amphibio_raw AS
SELECT * FROM read_csv('../../data/AmphiBIO_v1.csv', header=true, nullstr='NA',
                       ignore_errors=true, sample_size=-1);
""")

# derive niche (diet) + lifestyle (habitat) in the vert_niche vocabulary
con.sql("""
CREATE OR REPLACE TABLE amphibian_traits AS
WITH d AS (
  SELECT "Species" AS sciname, "Order" AS ord, "Family" AS fam,
    (Leaves=1 OR Flowers=1 OR Seeds=1 OR Fruits=1) AS plant,
    (Arthro=1)                                     AS arthro,
    (Vert=1)                                       AS vert,
    Fos=1 AS fos, Ter=1 AS ter, Aqu=1 AS aqu, Arb=1 AS arb,
    TRY_CAST(Body_mass_g AS DOUBLE)  AS mass,
    TRY_CAST(Body_size_mm AS DOUBLE) AS body_size_mm
  FROM amphibio_raw WHERE "Species" IS NOT NULL
)
SELECT n2.species_id, d.sciname, d.ord, d.fam,
  CASE
    WHEN plant AND (arthro OR vert) THEN 'Omnivore'
    WHEN vert                       THEN 'Vertivore'
    WHEN arthro                     THEN 'Invertivore'
    WHEN plant                      THEN 'Herbivore'
  END AS niche,
  CASE
    WHEN aqu THEN 'Aquatic'
    WHEN arb THEN 'Insessorial'
    WHEN ter OR fos THEN 'Terrestrial'
  END AS lifestyle,
  CASE
    WHEN aqu THEN 'aquatic' WHEN arb THEN 'arboreal'
    WHEN fos THEN 'fossorial' WHEN ter THEN 'terrestrial'
  END AS habitat,
  d.mass, d.body_size_mm
FROM d JOIN name2sid n2 ON n2.norm_name = norm(d.sciname);
""")

n_total = con.sql("SELECT count(*) FROM amphibio_raw").fetchone()[0]
n_res   = con.sql("SELECT count(DISTINCT species_id) FROM amphibian_traits").fetchone()[0]
print(f"AmphiBIO rows: {n_total:,}  -> resolved to backbone species: {n_res:,}")

# %% [markdown]
# ## Wire amphibians into the unified niche pool (feeds convergence + niche question)

# %%
con.sql("""
DELETE FROM vert_niche WHERE grp='amphibian';
INSERT INTO vert_niche (species_id, niche, lifestyle, grp)
SELECT DISTINCT species_id, niche, lifestyle, 'amphibian'
FROM amphibian_traits WHERE niche IS NOT NULL OR lifestyle IS NOT NULL;
""")
con.sql("SELECT grp, count(*) FROM vert_niche GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## Score it — coverage of the questions AmphiBIO now backs

# %%
con.sql("""
SELECT
  count(*)                                    AS amphibians,
  count(niche)                                AS with_diet_niche,
  count(lifestyle)                            AS with_lifestyle,
  count(mass)                                 AS with_mass,
  count(body_size_mm)                         AS with_size
FROM amphibian_traits
""").show()
print("=== niche distribution ===")
con.sql("SELECT niche, count(*) FROM amphibian_traits GROUP BY 1 ORDER BY 2 DESC").show()
print("=== sample: familiar amphibians ===")
con.sql("""
SELECT s.canonicalName AS species, a.niche, a.lifestyle, a.habitat,
       round(a.mass,1) AS mass_g, a.body_size_mm
FROM amphibian_traits a JOIN species s ON s.species_id=a.species_id
WHERE s.canonicalName IN ('Rana temporaria','Bufo bufo','Ambystoma mexicanum',
  'Andrias japonicus','Dendrobates tinctorius','Salamandra salamandra')
ORDER BY 1
""").show()

# %%
con.close()
