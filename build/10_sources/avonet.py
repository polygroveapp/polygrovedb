# %% [markdown]
# # PolygroveDB — AVONET ingest + real convergence (step 15)
#
# EOL's guild was marine plankton junk. AVONET (Tobias et al. 2022, Ecology
# Letters, CC BY) has clean, peer-reviewed traits for all 11,009 birds:
# **Trophic.Niche** (invertivore, frugivore…), **Primary.Lifestyle** (aerial/
# terrestrial/aquatic — the land/air/sea domain), **Habitat** (forest/grassland),
# **Mass**. We ingest it, resolve to species_id, and re-run the convergence
# self-join on FINE niche + domain to see if the owl↔sea-lion nonsense is gone.

# %%
import duckdb, pandas as pd
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

df = pd.read_excel("../../data/avonet.xlsx", sheet_name="AVONET1_BirdLife")
df = df[["Species1","Trophic.Niche","Trophic.Level","Primary.Lifestyle","Habitat","Mass"]]
df.columns = ["sciname","niche","trophic_level","lifestyle","habitat","mass"]
con.sql("CREATE OR REPLACE TABLE avonet_raw AS SELECT * FROM df")

# resolve to backbone species_id
con.sql("""
CREATE OR REPLACE TABLE bird_traits AS
SELECT n.species_id, a.niche, a.trophic_level, a.lifestyle, a.habitat, a.mass
FROM avonet_raw a JOIN name2sid n ON n.norm_name = norm(a.sciname);
""")
con.sql("SELECT count(*) AS birds_resolved FROM bird_traits").show()

# %% [markdown]
# ## Convergence on FINE niche + domain + habitat (game-side)
# Focal bird → find a bird with the SAME (niche, lifestyle, habitat) in a
# DIFFERENT realm. This is real convergence, not "two carnivores".

# %%
con.sql("""
CREATE OR REPLACE TEMP TABLE bt AS
SELECT DISTINCT b.species_id, b.niche, b.lifestyle, b.habitat, e.REALM AS realm
FROM bird_traits b
JOIN species_ecoregions se ON se.species_id = b.species_id
JOIN ecoregions e ON e.ECO_ID = se.ecoregion_id
WHERE e.REALM IS NOT NULL AND e.REALM <> '' AND b.niche IS NOT NULL;
""")
base=con.sql("SELECT count(DISTINCT species_id) FROM bt").fetchone()[0]
cp=con.sql("""SELECT count(DISTINCT f.species_id) FROM bt f
  JOIN bt c ON c.niche=f.niche AND c.lifestyle=f.lifestyle AND c.habitat=f.habitat
             AND c.realm<>f.realm AND c.species_id<>f.species_id""").fetchone()[0]
print(f"birds with (niche+lifestyle+habitat+realm): {base:,}")
print(f"  ...with a convergent counterpart (same niche+lifestyle+habitat, diff realm): {cp:,} ({100*cp//base}%)")

print("\n=== the SAME question, now with real convergence ===")
con.sql("""
SELECT s1.canonicalName AS focal, f.niche, f.lifestyle, f.habitat,
       f.realm AS focal_realm, s2.canonicalName AS counterpart, c.realm AS counterpart_realm
FROM bt f JOIN bt c ON c.niche=f.niche AND c.lifestyle=f.lifestyle AND c.habitat=f.habitat
          AND c.realm<>f.realm AND c.species_id<>f.species_id
JOIN species s1 ON s1.species_id=f.species_id
JOIN species s2 ON s2.species_id=c.species_id
WHERE f.lifestyle IN ('Aerial','Terrestrial')
ORDER BY random() LIMIT 6
""").show()

# %%
con.sql("SHOW TABLES").show()
con.close()
