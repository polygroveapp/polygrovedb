# %% [markdown]
# # PolygroveDB — CC-licensed fish traits (the FishBase replacement)
#
# FishBase is CC-BY-NC (dropped in the 2026-08-07 license audit), which left the
# ~43k backbone fish with zero feeding/size signals. These three sources are the
# license-clean substitute, each verified at download (2026-09-09, data/fish_cc/):
#
# - **Beukhof et al. 2019** (PANGAEA 900866) — license field in the dataset's
#   metadata_jsonld: **CC-BY 4.0**. Marine fish of N Atlantic + NE Pacific
#   shelves; per-LME rows -> aggregate per taxon. tl (trophic level), length.max
#   (cm), habitat, feeding.mode.
# - **FishTraits 14.3** (Frimpong & Angermeier; ScienceBase 5a7c6e8ce4b00f54eb2318c0)
#   — rights field: **CC0-1.0 public domain**. 809 US freshwater species; binary
#   diet flags + MAXTL (cm, -999 = missing).
# - **Parravicini et al. 2020** (github valerianoparravicini/Trophic_Fish_2020,
#   repo **MIT**, paper PLoS Biology **CC-BY 4.0**) — 30 standardized expert
#   classifications for 6,315 reef fish; we take the majority guild
#   (H=herb, O=omni, P/I/PK=carnivore) with a deterministic tiebreak.
# - **FISHMORPH** (Brosse et al. 2021; figshare 14891412, license field via the
#   figshare API: **CC BY 4.0**) — 10,230 freshwater ray-finned fish; we use
#   MBl (maximum body length, cm). Semicolon-delimited.
#
# Output: `fish_traits_cc(species_id, niche, length_cm, habitat, src)` — one row
# per species, field-wise best source (FishTraits > Beukhof > Parravicini; diet
# flags beat shelf trophic level beat expert consensus). Species are gated to
# actual fish: shark/ray/jawless classes, or the backbone's class-less chordates
# with an order (= bony fish; see generate_catalog's 'Fish' synthetic class).

# %%
import duckdb, pandas as pd
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# %% Beukhof — per-LME rows -> one row per species-rank taxon
b = pd.ExcelFile("../../data/fish_cc/beukhof2019_traits.xlsx").parse("Trait values")
b = b[b["taxonomic.rank"].eq("S")]   # S/G/F = species/genus/family rows; species only
gb = b.groupby("taxon", sort=True).agg(
    tl=("tl", "median"), length=("length.max", "max"),
    feeding=("feeding.mode", lambda s: s.dropna().sort_values().mode().iat[0] if s.dropna().size else None),
).reset_index()
# guild: measured trophic level FIRST (standard bins: <=2.19 herb, <2.8 omni, else carn) —
# feeding.mode only as fallback, and 'generalist' means varied PREY, not omnivory
# (cod is generalist at tl 4.4; mapping mode first called it an Omnivore)
gb["niche"] = gb.apply(lambda r:
    ("Herbivore" if r["tl"] <= 2.19 else "Omnivore" if r["tl"] < 2.8 else "Carnivore") if pd.notna(r["tl"]) else
    {"herbivorous": "Herbivore", "generalist": "Omnivore",
     "benthivorous": "Carnivore", "planktivorous": "Carnivore", "piscivorous": "Carnivore"}.get(r["feeding"]), axis=1)
print(f"Beukhof: {len(gb)} species-rank taxa")

# %% FishTraits — diet flags -> guild; MAXTL cm (-999 sentinel)
f = pd.ExcelFile("../../data/fish_cc/fishtraits_14.3.xls").parse("all_traits_1")
f["name"] = f["GENUS"].str.strip() + " " + f["SPECIES"].str.strip()
herb = f[["ALGPHYTO", "MACVASCU", "DETRITUS"]].fillna(0).sum(axis=1) > 0
carn = f[["INVLVFSH", "FSHCRCRB", "BLOOD", "EGGS"]].fillna(0).sum(axis=1) > 0
f["niche"] = None
f.loc[herb & ~carn, "niche"] = "Herbivore"
f.loc[carn & ~herb, "niche"] = "Carnivore"
f.loc[herb & carn, "niche"] = "Omnivore"
f["length"] = f["MAXTL"].where(f["MAXTL"] > 0)
ft = f[["name", "niche", "length"]].dropna(subset=["niche", "length"], how="all")
print(f"FishTraits: {len(ft)} species ({ft['niche'].notna().sum()} with diet, {ft['length'].notna().sum()} with length)")

# %% Parravicini — majority expert guild, deterministic tiebreak (count desc, guild asc)
p = pd.read_csv("../../data/fish_cc/parravicini2020_expert_guilds.csv")
G = {"H": "Herbivore", "O": "Omnivore", "P": "Carnivore", "I": "Carnivore", "PK": "Carnivore"}
votes = (p.set_index("Genus_and_species").iloc[:, 8:]
           .apply(lambda row: row.dropna().map(G).value_counts(), axis=1))
pv = votes.apply(lambda r: None if r.dropna().empty else sorted(r.dropna().items(), key=lambda kv: (-kv[1], kv[0]))[0][0], axis=1)
pv = pv.dropna().reset_index(); pv.columns = ["name", "niche"]
print(f"Parravicini: {len(pv)} reef species with a majority guild")

# %% FISHMORPH — MBl (max body length, cm) for freshwater ray-finned fish
m = pd.read_csv("../../data/fish_cc/fishmorph.csv", sep=";", encoding="latin-1")
fm = m[["Genus species", "MBl"]].rename(columns={"Genus species": "name", "MBl": "length"})
fm["length"] = pd.to_numeric(fm["length"], errors="coerce")
fm = fm.dropna(subset=["length"]).query("length > 0").groupby("name", as_index=False)["length"].max()
print(f"FISHMORPH: {len(fm)} species with max body length")

# %% resolve to species_id (fish-gated) and combine field-wise by priority
con.register("beukhof_df", gb[["taxon", "niche", "length"]].rename(columns={"taxon": "name"}))
con.register("fishtraits_df", ft)
con.register("parravicini_df", pv)
con.register("fishmorph_df", fm)
con.sql("""
CREATE OR REPLACE TEMP TABLE fishset AS
SELECT species_id FROM species
WHERE class IN ('Elasmobranchii','Holocephali','Myxini','Petromyzonti')
   OR (class IS NULL AND phylum='Chordata' AND "order" IS NOT NULL);
""")
con.sql("""
CREATE OR REPLACE TABLE fish_traits_cc AS
WITH rows AS (
  SELECT n.species_id, d.niche, d.length, 'Freshwater' AS habitat, 'FishTraits (CC0)' AS src, 1 AS pri
  FROM fishtraits_df d JOIN name2sid n ON n.norm_name = norm(d.name)
  UNION ALL
  SELECT n.species_id, d.niche, d.length, 'Marine', 'Beukhof 2019 (CC-BY)', 2
  FROM beukhof_df d JOIN name2sid n ON n.norm_name = norm(d.name)
  UNION ALL
  SELECT n.species_id, d.niche, NULL, 'Reef', 'Parravicini 2020 (CC-BY)', 3
  FROM parravicini_df d JOIN name2sid n ON n.norm_name = norm(d.name)
  UNION ALL
  SELECT n.species_id, NULL, d.length, 'Freshwater', 'FISHMORPH (CC-BY)', 4
  FROM fishmorph_df d JOIN name2sid n ON n.norm_name = norm(d.name)
)
SELECT r.species_id,
  arg_min(r.niche,  r.pri) FILTER (r.niche  IS NOT NULL) AS niche,
  arg_min(r.length, r.pri) FILTER (r.length IS NOT NULL) AS length_cm,
  arg_min(r.habitat,r.pri) AS habitat,
  arg_min(r.src,    r.pri) AS src
FROM rows r JOIN fishset f USING (species_id)
GROUP BY r.species_id;
""")
con.sql("""SELECT count(*) fish, count(niche) with_niche, count(length_cm) with_len FROM fish_traits_cc""").show()
con.sql("""SELECT s.canonicalName, f.niche, f.length_cm, f.habitat, f.src
FROM fish_traits_cc f JOIN species s USING(species_id)
WHERE s.canonicalName IN ('Salmo salar','Oncorhynchus mykiss','Gadus morhua') ORDER BY 1""").show()
con.close()
print("fish_traits_cc built")
