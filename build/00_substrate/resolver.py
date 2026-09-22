# %% [markdown]
# # PolygroveDB — name resolution v2 (step 3)
#
# v1 matched EOL/GloBI names to the backbone by *exact* canonical name and
# collapsed coverage (trophic 152k→11k). Two fixes here:
#
# 1. **Synonyms** — v1 only used *accepted* names. GBIF's backbone also has
#    synonyms pointing at an accepted taxon. We build a resolver over *all*
#    names → accepted `species_id`.
# 2. **Normalization** — EOL names carry authorship / subspecies / parens
#    (`"Puma concolor (Linnaeus, 1771)"`). A `norm()` macro strips those and
#    keeps genus+species, applied to *both* sides so they match.
#
# Output: a reusable `gbif_names` resolver, a `species` hub table (the real
# `species_id`), and resolved coverage v1-vs-v2 so we can see the lift.

# %%
import duckdb, subprocess, os
DATA = "../../data"; SCRATCH = "../_scratch"; os.makedirs(SCRATCH, exist_ok=True)
con = duckdb.connect("../../polygrove.duckdb")

# normalize a scientific name → "genus species", lowercased:
#   drop parenthetical authorship, drop rank markers, keep first two tokens.
con.sql(r"""
CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(
    list_filter(
      string_split(regexp_replace(coalesce(s,''), '\([^)]*\)', '', 'g'), ' '),
      x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.')
    )[1:2], ' '));
""")
print("norm demo:", con.sql("SELECT norm('Puma concolor (Linnaeus, 1771)'), norm('Amanita muscaria var. alba')").fetchone())

# %% [markdown]
# ## Build the `species` hub + the `gbif_names` resolver
# `species` = accepted species (reuse `taxon`). `gbif_names` = every
# species-level name (accepted **and** synonym) → its accepted `species_id`.

# %%
con.sql("""
CREATE OR REPLACE TABLE species AS
SELECT taxonID AS species_id, canonicalName, kingdom, phylum, class, "order", family, genus
FROM taxon;
""")

# re-read Taxon.tsv to get SYNONYMS (taxon table dropped them)
sh = lambda c: subprocess.run(c, shell=True, check=True)
sh(f"unzip -o -p {DATA}/backbone.zip Taxon.tsv > {SCRATCH}/Taxon.tsv")
con.sql(f"""
CREATE OR REPLACE TABLE gbif_names AS
SELECT DISTINCT norm(canonicalName) AS norm_name,
       CASE WHEN lower(taxonomicStatus) = 'accepted' THEN taxonID
            ELSE TRY_CAST(acceptedNameUsageID AS BIGINT) END AS accepted_id
FROM read_csv('{SCRATCH}/Taxon.tsv', delim='\t', header=true, quote='', ignore_errors=true)
WHERE lower(taxonRank) IN ('species','subspecies','variety','form')
  AND canonicalName IS NOT NULL AND canonicalName <> '';
""")
os.remove(f"{SCRATCH}/Taxon.tsv")
# keep only names that resolve to a real accepted species
con.sql("""
CREATE OR REPLACE TABLE gbif_names AS
SELECT g.norm_name, g.accepted_id
FROM gbif_names g JOIN species s ON s.species_id = g.accepted_id
WHERE g.norm_name <> '';
""")
con.sql("SELECT count(*) name_variants, count(DISTINCT accepted_id) species_reachable FROM gbif_names").show()

# the one-name-one-species resolver the whole pipeline joins through.
# (Historical note: this lived in a since-archived notebook — the clean-rebuild
# test caught that nothing in the chain created it. It belongs here, with gbif_names.)
# When a normalized name is claimed by SEVERAL accepted species (141k names: synonymy
# tangles, homonyms), prefer the accepted species whose OWN canonical name is that name
# (self-match), then fall back to the lowest id. The old min(accepted_id) rule sent
# 44,352 names' data to the wrong species (black widow -> a different Latrodectus).
con.sql("""CREATE OR REPLACE TABLE name2sid AS
  SELECT norm_name, arg_min(accepted_id, [self_match, accepted_id]) AS species_id FROM (
    SELECT g.norm_name, g.accepted_id,
           CASE WHEN norm(s.canonicalName)=g.norm_name THEN 0 ELSE 1 END AS self_match
    FROM gbif_names g JOIN species s ON s.species_id=g.accepted_id)
  GROUP BY 1;""")
print("name2sid:", con.sql("SELECT count(*) FROM name2sid").fetchone()[0])

# %% [markdown]
# ## The lift: raw name-strings → v1 (exact) → v2 (normalized + synonyms)

# %%
metrics = {
  "trophic (EOL)":     "SELECT DISTINCT scientific_name n FROM eol_traits WHERE lower(predicate) LIKE '%troph%'",
  "habitat (EOL)":     "SELECT DISTINCT scientific_name n FROM eol_traits WHERE lower(predicate) LIKE '%habitat%'",
  "interaction (GloBI)":"SELECT DISTINCT sourceTaxonName n FROM interactions",
}
print(f"{'metric':<22}{'raw names':>12}{'v1 exact':>12}{'v2 resolved':>14}{'lift':>8}")
print("-"*68)
for label, q in metrics.items():
    raw = con.sql(f"SELECT count(*) FROM ({q}) t WHERE n IS NOT NULL").fetchone()[0]
    v1  = con.sql(f"""SELECT count(DISTINCT s.species_id) FROM ({q}) x
                      JOIN species s ON lower(x.n) = lower(s.canonicalName)""").fetchone()[0]
    v2  = con.sql(f"""SELECT count(DISTINCT g.accepted_id) FROM ({q}) x
                      JOIN gbif_names g ON g.norm_name = norm(x.n)""").fetchone()[0]
    lift = f"{v2/v1:.1f}x" if v1 else "—"
    print(f"{label:<22}{raw:>12,}{v1:>12,}{v2:>14,}{lift:>8}")

# %% [markdown]
# ## Rebuild `species_coverage` on the resolved links (v2)

# %%
con.sql("""
CREATE OR REPLACE TEMP TABLE r_troph AS
  SELECT DISTINCT g.accepted_id sid FROM (SELECT DISTINCT scientific_name n FROM eol_traits WHERE lower(predicate) LIKE '%troph%') x
  JOIN gbif_names g ON g.norm_name = norm(x.n);
CREATE OR REPLACE TEMP TABLE r_hab AS
  SELECT DISTINCT g.accepted_id sid FROM (SELECT DISTINCT scientific_name n FROM eol_traits WHERE lower(predicate) LIKE '%habitat%') x
  JOIN gbif_names g ON g.norm_name = norm(x.n);
CREATE OR REPLACE TEMP TABLE r_int AS
  SELECT DISTINCT g.accepted_id sid FROM (SELECT DISTINCT sourceTaxonName n FROM interactions) x
  JOIN gbif_names g ON g.norm_name = norm(x.n);
""")
con.sql("""
CREATE OR REPLACE TABLE species_coverage AS
SELECT s.species_id, s.canonicalName, s.kingdom, s.class,
       (t.sid IS NOT NULL) AS has_trophic,
       (h.sid IS NOT NULL) AS has_habitat,
       (i.sid IS NOT NULL) AS has_interaction
FROM species s
LEFT JOIN r_troph t ON t.sid = s.species_id
LEFT JOIN r_hab   h ON h.sid = s.species_id
LEFT JOIN r_int   i ON i.sid = s.species_id;
""")
con.sql("""
SELECT class, count(*) species,
       round(100.0*avg(has_trophic::int),1) pct_trophic,
       round(100.0*avg(has_interaction::int),1) pct_interaction
FROM species_coverage WHERE class IS NOT NULL
GROUP BY class HAVING count(*) > 5000 ORDER BY species DESC LIMIT 12
""").show()

# %%
con.sql("SHOW TABLES").show()
con.close()
