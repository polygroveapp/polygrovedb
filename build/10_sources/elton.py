# %% [markdown]
# # PolygroveDB — EltonTraits mammals + cross-taxon convergence (step 16)
#
# AVONET gave clean niche/domain for birds. EltonTraits (Wilman 2014) gives the
# raw ingredients for ~5,400 mammals: **diet percentages** (→ dominant niche),
# **ForStrat-Value** (G/Ar/A/M → domain), body mass, activity. We derive
# AVONET-comparable niche + lifestyle, unify birds+mammals into one `vert_niche`
# table, and run convergence across BOTH — so a nectar bat can match a hummingbird.

# %%
import duckdb, pandas as pd
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

m = pd.read_csv("../../data/elton_MamFuncDat.txt", sep="\t", encoding="latin-1")
DIET={'Diet-Inv':'Invertivore','Diet-Vend':'Vertivore','Diet-Vect':'Vertivore','Diet-Vfish':'Vertivore',
      'Diet-Vunk':'Vertivore','Diet-Scav':'Scavenger','Diet-Fruit':'Frugivore','Diet-Nect':'Nectarivore',
      'Diet-Seed':'Granivore','Diet-PlantO':'Herbivore'}
ANIMAL=['Diet-Inv','Diet-Vend','Diet-Vect','Diet-Vfish','Diet-Vunk','Diet-Scav']
PLANT=['Diet-Fruit','Diet-Nect','Diet-Seed','Diet-PlantO']
def niche(r):
    a=sum(r[c] for c in ANIMAL); p=sum(r[c] for c in PLANT)
    if a>=20 and p>=20: return 'Omnivore'
    vals={c:r[c] for c in DIET}
    return DIET[max(vals,key=vals.get)]
LIFE={'G':'Terrestrial','Ar':'Insessorial','A':'Aerial','M':'Aquatic','S':'Terrestrial'}
m['niche']=m.apply(niche,axis=1)
m['lifestyle']=m['ForStrat-Value'].map(LIFE)
m['sciname']=m['Scientific']; m['mass']=m['BodyMass-Value']
con.sql("CREATE OR REPLACE TABLE mammal_traits AS SELECT sciname, niche, lifestyle, mass FROM m")

# resolve to species_id + unify birds (AVONET) and mammals into one niche table
con.sql("""
CREATE OR REPLACE TABLE vert_niche AS
SELECT species_id, niche, lifestyle, 'bird' AS grp FROM bird_traits WHERE niche IS NOT NULL
UNION ALL
SELECT n.species_id, mm.niche, mm.lifestyle, 'mammal'
FROM mammal_traits mm JOIN name2sid n ON n.norm_name = norm(mm.sciname) WHERE mm.niche IS NOT NULL;
""")
con.sql("SELECT grp, count(DISTINCT species_id) AS species FROM vert_niche GROUP BY 1").show()

# %% [markdown]
# ## Convergence across birds + mammals (same niche+lifestyle+biome, diff realm)

# %%
con.sql("""
CREATE OR REPLACE TEMP TABLE vn AS
SELECT DISTINCT v.species_id, v.niche, v.lifestyle, v.grp, e.REALM AS realm
FROM vert_niche v JOIN species_ecoregions se ON se.species_id=v.species_id
JOIN ecoregions e ON e.ECO_ID=se.ecoregion_id WHERE e.REALM<>'' AND e.REALM IS NOT NULL;
""")
print("=== CROSS-TAXON convergences (a bird's counterpart is a mammal or vice-versa) ===")
con.sql("""
SELECT s1.canonicalName AS focal, f.grp AS focal_grp, f.niche, f.lifestyle,
       s2.canonicalName AS counterpart, c.grp AS cp_grp, c.realm AS cp_realm
FROM vn f JOIN vn c ON c.niche=f.niche AND c.lifestyle=f.lifestyle AND c.realm<>f.realm
     AND c.grp<>f.grp AND c.species_id<>f.species_id
JOIN species s1 ON s1.species_id=f.species_id JOIN species s2 ON s2.species_id=c.species_id
ORDER BY random() LIMIT 8
""").show()

# %%
con.close()
