# %% [markdown]
# # PolygroveDB — insect & arachnid traits (step 30): LepTraits + OPD + World Spider Traits
#
# The deck had 5 insects + 4 arachnids because SIZE was the gate (feeding is mostly
# coverable via GloBI-derived guilds; biome/food-web already exist for insects).
# Three order-level, license-clean sources fix it:
# - **LepTraits 1.0** (Shirey et al. 2022, CC-BY 4.0): ~12.4k butterflies, wingspan
#   + hostplant families (recorded hostplants = measured herbivory).
# - **Odonate Phenotypic Database** (Waller et al. 2019, CC0 via Dryad): ~1k
#   dragonflies/damselflies, body length. (Dryad is token-gated now; dump obtained
#   from the OPD's own shiny-app repo, github.com/jhnwllr/shiny-server.)
# - **World Spider Trait database** (Pekár et al. 2021, CC-BY 4.0): body length
#   ('bole') for thousands of spiders, dumped page-by-page from its public API.
# EOL's raw dump was checked for insect body length: near-empty (only carapace/femur
# fragments) — not used.

# %%
import duckdb, os
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# %% [markdown]
# ## 1. LepTraits — butterfly wingspan (mm) + hostplant-recorded herbivory

# %%
con.sql("""
CREATE OR REPLACE TABLE lep_traits AS
WITH c AS (SELECT * FROM read_csv('../../data/leptraits/LepTraits-main/consensus/consensus.csv',
                                  header=true, ignore_errors=true, sample_size=-1)),
per AS (
  SELECT n.species_id,
    (coalesce(TRY_CAST(c.WS_L AS DOUBLE), TRY_CAST(c.WS_U AS DOUBLE))
     + coalesce(TRY_CAST(c.WS_U AS DOUBLE), TRY_CAST(c.WS_L AS DOUBLE))) / 2 AS ws,
    TRY_CAST(c.NumberOfHostplantFamilies AS INT) AS hostfams
  FROM c JOIN name2sid n ON n.norm_name = norm(c.Species))
SELECT species_id, round(max(ws)*10,1) AS wingspan_mm,   -- LepTraits WS_* are in CM (monarch=9.4) -> mm
       max(hostfams) AS hostplant_fams
FROM per GROUP BY 1;
""")
print("LepTraits resolved:", con.sql("SELECT count(*), count(wingspan_mm) FROM lep_traits").fetchone())
# units sanity: monarch wingspan should be ~90-100 mm after the cm->mm conversion
print("monarch check (expect ~94):", con.sql("""SELECT l.wingspan_mm FROM lep_traits l JOIN name2sid n ON n.species_id=l.species_id
  WHERE n.norm_name=norm('Danaus plexippus') LIMIT 1""").fetchall())

# %% [markdown]
# ## 2. OPD — odonate body length (mm)

# %%
con.sql("""
CREATE OR REPLACE TABLE odonate_traits AS
WITH o AS (SELECT * FROM read_csv('../../data/opd/OPD_mergeDataReduced.csv',
                                  header=true, ignore_errors=true, sample_size=-1))
SELECT n.species_id, round(avg(TRY_CAST(o.body_lengths AS DECIMAL(18,6))),1) AS body_mm
FROM o JOIN name2sid n ON n.norm_name = norm(o.GenusSpecies)
WHERE TRY_CAST(o.body_lengths AS DOUBLE) > 0
GROUP BY 1;
""")
print("OPD resolved:", con.sql("SELECT count(*) FROM odonate_traits").fetchone())

# %% [markdown]
# ## 3. World Spider Traits — adult body length (mm) from the API dump

# %%
assert os.path.exists("../../data/spidertraits/wst_records.jsonl"), "run dl_wst.py first"
con.sql("""
CREATE OR REPLACE TABLE spider_traits AS
WITH w AS (SELECT * FROM read_json('../../data/spidertraits/wst_records.jsonl',
                                   format='newline_delimited', ignore_errors=true)),
bole AS (
  SELECT taxonomy.genus || ' ' || taxonomy.species AS sci,
         TRY_CAST(value AS DOUBLE) AS mm
  FROM w
  WHERE trait.abbrev = 'bole' AND lifeStage.name = 'Adult'
    AND TRY_CAST(value AS DOUBLE) BETWEEN 0.3 AND 150)
SELECT n.species_id, round(avg(CAST(mm AS DECIMAL(18,6))),1) AS body_mm
FROM bole b JOIN name2sid n ON n.norm_name = norm(b.sci)
GROUP BY 1;
""")
print("WST spiders resolved:", con.sql("SELECT count(*) FROM spider_traits").fetchone())

# %%
# iconic sanity
for sp in ['Danaus plexippus','Papilio machaon','Latrodectus mactans','Anax junius','Aeshna cyanea']:
    r=con.sql("""SELECT coalesce(l.wingspan_mm, o.body_mm, s.body_mm)
      FROM name2sid n
      LEFT JOIN lep_traits l ON l.species_id=n.species_id
      LEFT JOIN odonate_traits o ON o.species_id=n.species_id
      LEFT JOIN spider_traits s ON s.species_id=n.species_id
      WHERE n.norm_name=norm(?) LIMIT 1""",params=[sp]).fetchone()
    print(f"  {sp}: {r[0] if r else None} mm")
con.close()
