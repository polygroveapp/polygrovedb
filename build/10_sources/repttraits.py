# %% [markdown]
# # PolygroveDB — ReptTraits for reptiles (step 21)
#
# The last vertebrate class. **ReptTraits** (Oskyrko, Mi, Meiri & Du 2024,
# *Scientific Data*, CC BY, figshare 24572683, 12,060 species — crocs, turtles,
# tuatara, lizards, amphisbaenians, snakes) completes the vertebrates:
# - **Size** — Maximum body mass (g): 10,469 reptiles
# - **Niche** — Diet (Carnivorous/Omnivorous/Herbivorous): 4,533
# - **Lifestyle** — Microhabitat (Terrestrial/Arboreal/Aquatic/Fossorial…): 10,693
# - **Habitat** — Habitat type (Forest/Desert/Grassland/Savanna…): 9,493 — real
#   habitat granularity, the same axis AVONET gives birds
#
# (IUCN status & population-trend columns are deliberately NOT ingested — the
# game excludes conservation status by design.)

# %%
import duckdb, pandas as pd
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

raw = pd.read_excel("../../data/repttraits.xlsx", sheet_name="Data")
rt = pd.DataFrame({
    "sciname":      raw["Species"].astype(str).str.strip(),
    "ord":          raw["Order"],
    "diet":         raw["Diet "].astype(str).str.strip(),
    "microhabitat": raw["Microhabitat"].astype(str).str.strip(),
    "habitat_type": raw["Habitat type"].astype(str).str.strip(),
    "active_time":  raw["Active time"].astype(str).str.strip(),
    "mass_g":       pd.to_numeric(raw["Maximum body mass (g)"], errors="coerce"),
    "max_tl_mm":    pd.to_numeric(raw['Maximum total length ("TL", mm)'], errors="coerce"),
}).replace({"nan": None})
con.register("rt_raw", rt)

# resolve + derive niche/lifestyle/habitat in the vert_niche vocabulary
con.sql("""
CREATE OR REPLACE TABLE reptile_traits AS
SELECT DISTINCT ON (n2.species_id)
  n2.species_id, r.sciname, r.ord,
  CASE r.diet WHEN 'Carnivorous' THEN 'Carnivore'
              WHEN 'Omnivorous'  THEN 'Omnivore'
              WHEN 'Herbivorous' THEN 'Herbivore' END          AS niche,
  -- collapse the multi-valued microhabitat to one lifestyle. Terrestrial wins
  -- over Arboreal on land-combos (ReptTraits lists every microhabitat a species
  -- uses, and codes some aquatic reptiles — e.g. crocs — with land tokens only).
  CASE
    WHEN lower(r.microhabitat) LIKE '%aquatic%'
      OR lower(r.microhabitat) LIKE '%marine%'      THEN 'Aquatic'
    WHEN lower(r.microhabitat) LIKE '%terrestrial%'
      OR lower(r.microhabitat) LIKE '%fossorial%'
      OR lower(r.microhabitat) LIKE '%saxicolous%'  THEN 'Terrestrial'
    WHEN lower(r.microhabitat) LIKE '%arboreal%'    THEN 'Insessorial'
  END                                                          AS lifestyle,
  r.microhabitat,                                       -- raw, nothing lost
  split_part(r.habitat_type, '/', 1)                           AS habitat,
  r.active_time, r.mass_g, r.max_tl_mm
FROM rt_raw r
JOIN name2sid n2 ON n2.norm_name = norm(r.sciname)
WHERE r.sciname IS NOT NULL
ORDER BY n2.species_id, r.mass_g DESC NULLS LAST;
""")

n_total = len(rt)
n_res   = con.sql("SELECT count(*) FROM reptile_traits").fetchone()[0]
print(f"ReptTraits rows: {n_total:,}  -> resolved to backbone: {n_res:,}")

# %% [markdown]
# ## Wire reptiles into the unified niche pool

# %%
con.sql("""
DELETE FROM vert_niche WHERE grp='reptile';
INSERT INTO vert_niche (species_id, niche, lifestyle, grp)
SELECT species_id, niche, lifestyle, 'reptile'
FROM reptile_traits WHERE niche IS NOT NULL OR lifestyle IS NOT NULL;
""")
con.sql("SELECT grp, count(*) FROM vert_niche GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## Score it

# %%
con.sql("""
SELECT count(*) AS reptiles, count(niche) AS with_niche, count(lifestyle) AS with_lifestyle,
       count(NULLIF(habitat,'None')) AS with_habitat, count(mass_g) AS with_mass
FROM reptile_traits
""").show()
print("=== habitat distribution (real granularity) ===")
con.sql("SELECT habitat, count(*) FROM reptile_traits WHERE habitat NOT IN ('None') GROUP BY 1 ORDER BY 2 DESC LIMIT 10").show()
print("=== sample: familiar reptiles ===")
con.sql("""
SELECT s.canonicalName AS species, t.niche, t.lifestyle, t.habitat, t.mass_g
FROM reptile_traits t JOIN species s ON s.species_id=t.species_id
WHERE s.canonicalName IN ('Crocodylus niloticus','Chelonia mydas','Python regius',
  'Iguana iguana','Naja naja','Varanus komodoensis','Sphenodon punctatus')
ORDER BY t.mass_g DESC NULLS LAST
""").show()

# %%
con.close()
