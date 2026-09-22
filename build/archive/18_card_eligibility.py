# %% [markdown]
# # PolygroveDB — how many cards can we make? (step 18)
#
# A card needs a field note + photo + enough quiz questions. This counts, per
# species, how many of the *data-backed* questions it can support, and reports
# the eligible pool — plus the honest gate (field notes + photos aren't scaled).

# %%
import duckdb
con = duckdb.connect("../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# size = EOL body-size OR AVONET/Elton/FishBase/AmphiBIO/ReptTraits mass|length
con.sql("""
CREATE OR REPLACE TEMP TABLE has_size AS
SELECT species_id FROM species_size
UNION SELECT species_id FROM bird_traits WHERE mass IS NOT NULL
UNION SELECT n.species_id FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) WHERE m.mass IS NOT NULL
UNION SELECT species_id FROM fish_traits      WHERE max_length_cm IS NOT NULL
UNION SELECT species_id FROM amphibian_traits WHERE body_size_mm IS NOT NULL OR mass IS NOT NULL
UNION SELECT species_id FROM reptile_traits   WHERE mass_g IS NOT NULL OR max_tl_mm IS NOT NULL;
""")
# habitat granularity = AVONET birds + ReptTraits reptiles + AmphiBIO amphibians
con.sql("""
CREATE OR REPLACE TEMP TABLE has_habitat AS
SELECT species_id FROM bird_traits WHERE habitat IS NOT NULL
UNION SELECT species_id FROM reptile_traits   WHERE habitat IS NOT NULL AND habitat <> 'None'
UNION SELECT species_id FROM amphibian_traits WHERE habitat IS NOT NULL;
""")

con.sql("""
CREATE OR REPLACE TABLE card_elig AS
SELECT s.species_id, s.kingdom, s.class,
  (sc.has_interaction)                                          AS q_foodweb,
  (s.species_id IN (SELECT species_id FROM species_confusions)) AS q_confusion,
  (s.species_id IN (SELECT species_id FROM species_native_origin)) AS q_origin,
  (s.species_id IN (SELECT species_id FROM vert_niche))         AS q_niche,
  (s.species_id IN (SELECT species_id FROM has_size))           AS q_size,
  (s.species_id IN (SELECT species_id FROM has_habitat))       AS q_habitat,
  (s.species_id IN (SELECT species_id FROM species_ecoregions)) AS q_biome,
  (s.species_id IN (SELECT species_id FROM facts))              AS q_fieldnote
FROM species s
LEFT JOIN species_coverage sc ON sc.species_id = s.species_id;
""")
con.sql("""
ALTER TABLE card_elig ADD COLUMN n_questions INTEGER;
UPDATE card_elig SET n_questions =
  q_foodweb::int+q_confusion::int+q_origin::int+q_niche::int+q_size::int+q_habitat::int+q_biome::int;
""")

# %% [markdown]
# ## The pool — species by how many data-backed questions they support
# (Taxonomy is always available, so this counts the *other* questions on top.)

# %%
con.sql("""
SELECT n_questions AS content_questions, count(*) AS species
FROM card_elig GROUP BY 1 ORDER BY 1 DESC
""").show()
for k in [1,2,3,4]:
    n=con.sql(f"SELECT count(*) FROM card_elig WHERE n_questions >= {k}").fetchone()[0]
    print(f"  species supporting >= {k} content questions (+ taxonomy): {n:,}")

# %% [markdown]
# ## Per-question availability + the honest shippable gate

# %%
con.sql("""
SELECT
  sum(q_foodweb::int) foodweb, sum(q_confusion::int) confusion, sum(q_origin::int) origin,
  sum(q_niche::int) niche, sum(q_size::int) size, sum(q_habitat::int) habitat, sum(q_biome::int) biome_sample,
  sum(q_fieldnote::int) fieldnote
FROM card_elig
""").show()
print("SHIPPABLE gate: a card also needs a FIELD NOTE + PHOTO.")
print("  field notes extracted so far:", con.sql("SELECT count(DISTINCT species_id) FROM facts").fetchone()[0], "(demo only — extraction not scaled)")
print("  photos: 0 (Commons not ingested)")

# %% [markdown]
# ## Pool by kingdom (>=3 content questions)

# %%
con.sql("""
SELECT kingdom, count(*) AS eligible_species
FROM card_elig WHERE n_questions >= 3 GROUP BY 1 ORDER BY 2 DESC
""").show()

# %%
con.close()
