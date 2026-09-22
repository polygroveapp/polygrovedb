# %% [markdown]
# # PolygroveDB — normalized tables (step 4)
#
# Builds target-schema tables joined by `species_id` (via the `gbif_names`
# resolver from step 3), not by name string:
#
# - **`species_trophic_roles`** — taxonomy floors (Plantae→producer, Fungi→
#   decomposer) + EOL values crosswalked to the 5 buckets for animals.
# - **`species_habitats`** — EOL habitat values (raw labels; ENVO→29-label
#   crosswalk is a later refinement).
# - **`facts`** — the field notes, resolved to `species_id`, with a
#   `provenance` flag (`sourced` | `curated`).
#
# First-pass crosswalks are keyword/regex based — good enough to see the shape;
# a curated lookup table refines them later.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")
# resolver macro (idempotent — persisted from step 3, recreated to be safe)
con.sql(r"""
CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(
    string_split(regexp_replace(coalesce(s,''), '\([^)]*\)', '', 'g'), ' '),
    x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2], ' '));
""")

# %% [markdown]
# ## species_trophic_roles — floors + EOL crosswalk
# Multi-valued & sourced (a species can carry a taxonomy-floor role and an EOL
# role). Plants/algae = producer, fungi = decomposer (by taxonomy); animals map
# from EOL trophic values.

# %%
ALGAE = "('Phaeophyceae','Chlorophyta','Rhodophyta','Bacillariophyceae','Chrysophyceae','Xanthophyceae','Ulvophyceae','Florideophyceae')"
con.sql(f"""
CREATE OR REPLACE TABLE species_trophic_roles AS
-- taxonomy floors
SELECT species_id, 'producer'  AS role, 'taxonomy' AS source
  FROM species WHERE kingdom='Plantae' OR class IN {ALGAE}
UNION ALL
SELECT species_id, 'decomposer', 'taxonomy' FROM species WHERE kingdom='Fungi'
UNION ALL
-- animals from EOL trophic values (keyword crosswalk to 5 buckets)
SELECT DISTINCT g.accepted_id, role, 'eol'
FROM (
  SELECT scientific_name,
    CASE
      WHEN regexp_matches(lv,'omnivor') THEN 'omnivore'
      WHEN regexp_matches(lv,'carnivor|predat|piscivor|insectivor|vertivor|mammalivor|molluscivor|sanguinivor|hematophag') THEN 'carnivore'
      WHEN regexp_matches(lv,'herbivor|brows|graz|foliv|frugivor|granivor|nectarivor|palynivor|floriv') THEN 'herbivore'
      WHEN regexp_matches(lv,'decompos|saprotroph|saprophag|detritivor|coprophag') THEN 'decomposer'
      WHEN regexp_matches(lv,'autotroph|photosynth|producer') THEN 'producer'
    END AS role
  FROM (SELECT scientific_name, lower(coalesce(nullif(name_en,''), value_uri)) lv
        FROM eol_traits WHERE lower(predicate) LIKE '%troph%')
) e
JOIN gbif_names g ON g.norm_name = norm(e.scientific_name)
JOIN species s ON s.species_id = g.accepted_id AND s.kingdom='Animalia'
WHERE role IS NOT NULL;
""")
con.sql("""
SELECT source, role, count(DISTINCT species_id) species
FROM species_trophic_roles GROUP BY 1,2 ORDER BY 1, 3 DESC
""").show()
print("species with any trophic role:",
      con.sql("SELECT count(DISTINCT species_id) FROM species_trophic_roles").fetchone()[0])

# %% [markdown]
# ## species_habitats — EOL values (raw labels for now)
# EOL habitat values are ENVO URIs / English labels; kept raw. The crosswalk to
# your 29 canonical habitat labels is a later curated step.

# %%
con.sql("""
CREATE OR REPLACE TABLE species_habitats AS
SELECT DISTINCT g.accepted_id AS species_id,
       coalesce(nullif(name_en,''), regexp_replace(value_uri,'^.*/','')) AS habitat_raw,
       'eol' AS source
FROM eol_traits e
JOIN gbif_names g ON g.norm_name = norm(e.scientific_name)
WHERE lower(e.predicate) LIKE '%habitat%'
  AND coalesce(nullif(name_en,''), value_uri) IS NOT NULL;
""")
con.sql("""
SELECT count(DISTINCT species_id) species_with_habitat,
       count(*) habitat_rows,
       count(DISTINCT habitat_raw) distinct_labels
FROM species_habitats
""").show()
con.sql("SELECT habitat_raw, count(DISTINCT species_id) n FROM species_habitats GROUP BY 1 ORDER BY 2 DESC LIMIT 10").show()

# %% [markdown]
# ## facts — field notes resolved to species_id, with provenance
# The Wikipedia field notes carry `provenance='sourced'`. Curated expert notes
# (added later) carry `provenance='curated'` — same table, the flag drives
# licensing + access + trust.

# %%
con.sql("""
CREATE OR REPLACE TABLE facts AS
SELECT g.accepted_id AS species_id,
       f.field_note  AS sentence,
       'sourced'     AS provenance,
       'wikipedia'   AS source_type
FROM field_notes f
JOIN gbif_names g ON g.norm_name = norm(f.species);
""")
con.sql("SELECT provenance, count(*) facts, count(DISTINCT species_id) species FROM facts GROUP BY 1").show()

# %% [markdown]
# ## Where the normalized substrate stands

# %%
con.sql("""
SELECT 'species (hub)'          AS tbl, count(*) n FROM species
UNION ALL SELECT 'species_trophic_roles', count(*) FROM species_trophic_roles
UNION ALL SELECT 'species_habitats',      count(*) FROM species_habitats
UNION ALL SELECT 'facts',                 count(*) FROM facts
ORDER BY 2 DESC
""").show()
# %% [markdown]
# ## Still to come
# - `species_ecoregions` — needs GBIF occurrences (query-in-place, notebook 05).
# - `photos` — needs Commons metadata.
# - `species_confusions` — needs CrypticBio mapping.
# - Curated crosswalks — EOL/Wikidata trophic terms → 5 buckets; ENVO → 29 habitat labels.
# - Scale `facts` — run field-note extraction over the full eligible-species list.

# %%
con.sql("SHOW TABLES").show()
con.close()
