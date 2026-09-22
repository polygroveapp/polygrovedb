# %% [markdown]
# # PolygroveDB — facts disambiguation (step 9)
#
# `facts` fanned out (6 real species → 13 `species_id`s) because the name→species
# resolver is one-to-many (homonyms / ambiguous synonyms). A field note should
# attach to exactly one species. Fix: resolve each field-note name to a **single
# accepted species** by exact (normalized) canonical match, with a deterministic
# pick for the rare true cross-kingdom homonym.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

print("BEFORE:", con.sql("SELECT count(*) AS facts_rows, count(DISTINCT species_id) AS sp FROM facts").fetchone())

# %% [markdown]
# ## Rebuild: one accepted species per field-note name

# %%
con.sql("""
CREATE OR REPLACE TABLE facts AS
WITH picked AS (           -- accepted species matching the note's name; one per (name, note)
  SELECT f.field_note, f.species AS qname, min(s.species_id) AS species_id
  FROM field_notes f
  JOIN species s ON norm(s.canonicalName) = norm(f.species)
  GROUP BY f.field_note, f.species
)
SELECT species_id,
       field_note AS sentence,
       'sourced'  AS provenance,
       'wikipedia' AS source_type
FROM picked
WHERE species_id IS NOT NULL;
""")
print("AFTER: ", con.sql("SELECT count(*) AS facts_rows, count(DISTINCT species_id) AS sp FROM facts").fetchone())

# %% [markdown]
# ## Per-species facts (should be exactly our 6 species, no fan-out)

# %%
con.sql("""
SELECT sp.canonicalName AS species, sp.kingdom, count(*) AS facts
FROM facts f JOIN species sp ON sp.species_id = f.species_id
GROUP BY 1,2 ORDER BY 3 DESC
""").show()

# %%
con.close()
