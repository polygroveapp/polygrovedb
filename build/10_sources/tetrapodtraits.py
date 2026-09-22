# %% [markdown]
# # PolygroveDB — TetrapodTraits (step 28, CC-BY, unlocks birds + amphibians)
#
# TetrapodTraits v2 (Moura et al., CC-BY 4.0) covers all 33,281 tetrapods with
# body size, diet, habitat, and — crucially — **range-based biome + realm +
# centroid**. Birds and amphibians were stuck because BirdLife/IUCN ranges are
# non-commercial; this is the CC-BY source that fills them. We use MEASURED values
# (Imputed=0) and derive: size, diet→guild, habitat, and biome via the range
# centroid → RESOLVE ecoregion.

# %%
import duckdb, time
con = duckdb.connect("../../polygrove.duckdb"); con.sql("INSTALL spatial; LOAD spatial;")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
CSV = "../../data/tetrapodtraits/TetrapodTraits.csv"
t0=time.time()

con.sql(f"""
CREATE OR REPLACE TABLE tetrapod_traits AS
WITH t AS (SELECT * FROM read_csv('{CSV}', header=true, ignore_errors=true, sample_size=-1))
SELECT n.species_id, t."Scientific.Name" AS sci, t.Class AS class,
  -- SIZE (measured only): amphibians in mm (length), others in g (mass)
  CASE WHEN t.Class='Amphibia' AND TRY_CAST(t.ImputedLength AS INT)=0 THEN round(TRY_CAST(t.BodyLength_mm AS DOUBLE),1)::varchar||' mm'
       WHEN t.Class<>'Amphibia' AND TRY_CAST(t.ImputedMass AS INT)=0 THEN round(TRY_CAST(t.BodyMass_g AS DOUBLE),1)::varchar||' g'
  END AS size_val,
  -- FEEDING guild from diet proportions (measured only)
  CASE WHEN TRY_CAST(t.SourceDiet AS VARCHAR) IS NULL THEN NULL
    WHEN (coalesce(TRY_CAST(t.DietFruit AS DOUBLE),0)+coalesce(TRY_CAST(t.DietNect AS DOUBLE),0)
         +coalesce(TRY_CAST(t.DietSeed AS DOUBLE),0)+coalesce(TRY_CAST(t.DietPlant AS DOUBLE),0)) >= 0.7 THEN 'Herbivore'
    WHEN (coalesce(TRY_CAST(t.DietInv AS DOUBLE),0)+coalesce(TRY_CAST(t.DietVend AS DOUBLE),0)
         +coalesce(TRY_CAST(t.DietVect AS DOUBLE),0)+coalesce(TRY_CAST(t.DietVfish AS DOUBLE),0)) >= 0.7 THEN 'Carnivore'
    ELSE 'Omnivore' END AS niche,
  -- HABITAT / lifestyle from vertical strata flags
  CASE WHEN TRY_CAST(t.Aqu AS INT)=1 THEN 'Aquatic' WHEN TRY_CAST(t.Arb AS INT)=1 THEN 'Arboreal'
       WHEN TRY_CAST(t.Aer AS INT)=1 THEN 'Aerial' WHEN TRY_CAST(t.Fos AS INT)=1 THEN 'Fossorial'
       WHEN TRY_CAST(t.Ter AS INT)=1 THEN 'Terrestrial' END AS habitat,
  TRY_CAST(t.Longitude AS DOUBLE) AS lon, TRY_CAST(t.Latitude AS DOUBLE) AS lat,
  TRY_CAST(t.ImputedMass AS INT) AS mass_imputed, TRY_CAST(t.SourceDiet AS VARCHAR) AS diet_source
FROM t JOIN name2sid n ON n.norm_name = norm(t."Scientific.Name");
""")
r=con.sql("""SELECT count(*) sp, count(size_val) with_size, count(niche) with_diet, count(habitat) with_hab,
  count(CASE WHEN lon IS NOT NULL THEN 1 END) with_centroid FROM tetrapod_traits""").fetchone()
print(f"resolved tetrapods: {r[0]:,}  size {r[1]:,}  diet {r[2]:,}  habitat {r[3]:,}  centroid {r[4]:,}  ({time.time()-t0:.0f}s)", flush=True)

# %% [markdown]
# ## Biome for BIRDS + AMPHIBIANS via range centroid → RESOLVE ecoregion (the unlock)

# %%
con.sql("""CREATE OR REPLACE TEMP TABLE tt_bio AS
SELECT tt.species_id, e.ECO_ID
FROM tetrapod_traits tt JOIN species s ON s.species_id=tt.species_id
JOIN ecoregions e ON ST_Contains(e.geom, ST_Point(tt.lon, tt.lat))
WHERE s.class IN ('Aves','Amphibia') AND tt.lon IS NOT NULL;""")
print(f"bird+amphibian centroids placed in an ecoregion: {con.sql('SELECT count(*) FROM tt_bio').fetchone()[0]:,}  ({time.time()-t0:.0f}s)", flush=True)
con.sql("""INSERT INTO species_ecoregions (species_id, ecoregion_id, occurrence_count)
  SELECT species_id, ECO_ID, 100 FROM tt_bio
  WHERE NOT EXISTS (SELECT 1 FROM species_ecoregions se WHERE se.species_id=tt_bio.species_id AND se.ecoregion_id=tt_bio.ECO_ID);""")
print("birds w/ biome:", con.sql("""SELECT count(DISTINCT se.species_id) FROM species_ecoregions se JOIN species s ON s.species_id=se.species_id WHERE s.class='Aves'""").fetchone()[0],
      " amphibians w/ biome:", con.sql("""SELECT count(DISTINCT se.species_id) FROM species_ecoregions se JOIN species s ON s.species_id=se.species_id WHERE s.class='Amphibia'""").fetchone()[0], flush=True)
con.close()
print(f"done ({time.time()-t0:.0f}s)", flush=True)
