# %% [markdown]
# # PolygroveDB — substrate build (step 1)
#
# Builds the core substrate from the staged dumps using **DuckDB**. The
# `.duckdb` file this creates *is* PolygroveDB. Everything streams — no source
# is fully loaded into pandas, and nothing over a couple GB is kept extracted.
#
# **Prereqs:** `pip install duckdb` (DuckDB ≥1.5). The `spatial` extension is
# installed below for the WWF shapefile.
#
# **Layout assumed:** this notebook lives in `polygrovedb/build/`, dumps in
# `polygrovedb/data/`. Run cells top to bottom.

# %%
import duckdb, subprocess, os

DATA = "../../data"
SCRATCH = "../_scratch"; os.makedirs(SCRATCH, exist_ok=True)
con = duckdb.connect("../../polygrove.duckdb")      # <-- this file IS PolygroveDB
con.sql("INSTALL spatial; LOAD spatial;")
print("duckdb", duckdb.__version__)

def sh(cmd):                                       # tiny shell helper
    subprocess.run(cmd, shell=True, check=True)

# %% [markdown]
# ## 1. Taxonomy — the join key
# The GBIF backbone is what every other source resolves *to*. We extract
# `Taxon.tsv` (2.25 GB), load the columns we need at species rank, then delete
# the raw file — the DuckDB table is columnar + compressed, so the footprint
# stays small.

# %%
sh(f"unzip -o -p {DATA}/backbone.zip Taxon.tsv > {SCRATCH}/Taxon.tsv")
con.sql(f"""
CREATE OR REPLACE TABLE taxon AS
SELECT taxonID, canonicalName, scientificName, taxonRank, taxonomicStatus,
       kingdom, phylum, class, "order", family, genus
FROM read_csv('{SCRATCH}/Taxon.tsv', delim='\t', header=true,
              quote='', ignore_errors=true)
WHERE lower(taxonRank) = 'species'
  AND lower(taxonomicStatus) = 'accepted';
""")
os.remove(f"{SCRATCH}/Taxon.tsv")
con.sql("SELECT count(*) AS accepted_species, count(DISTINCT kingdom) AS kingdoms FROM taxon").show()

# %% [markdown]
# ## 2. Interactions — GloBI (read the gzip directly)
# Keep the **rich** interaction set, not just eats/eatenBy — the food web plus
# pollination, parasitism, seed dispersal (the data we were going to discard).

# %%
con.sql(f"""
CREATE OR REPLACE TABLE interactions AS
SELECT sourceTaxonName, sourceTaxonId, interactionTypeName,
       targetTaxonName, targetTaxonId, targetTaxonRank
FROM read_csv('{DATA}/globi_interactions.tsv.gz', delim='\t', header=true,
              sample_size=200000, ignore_errors=true)
WHERE interactionTypeName IN
      ('eats','eatenBy','preysOn','preyedUponBy','pollinates','pollinatedBy',
       'visitsFlowersOf','parasiteOf','hasHost','hostOf','dispersalVectorOf');
""")
con.sql("SELECT interactionTypeName, count(*) n FROM interactions GROUP BY 1 ORDER BY n DESC").show()

# %% [markdown]
# ## 3. Traits — EOL TraitBank (stream via unzip -p)
# `traits.csv` is 5.8 GB inside the zip; stream it out, keep trophic + habitat
# rows (extend the filter later to keep the richer trait set). Values are a mix
# of EOL terms / Wikidata Q-IDs / ENVO URIs — the crosswalk to your buckets is a
# later step; here we just capture them raw.

# %%
sh(f"unzip -o -p {DATA}/eol_traits_all.zip trait_bank/traits.csv > {SCRATCH}/eol_traits.csv")
con.sql(f"""
CREATE OR REPLACE TABLE eol_traits AS
SELECT page_id, scientific_name, predicate, value_uri, literal, name_en
FROM read_csv('{SCRATCH}/eol_traits.csv', header=true,
              sample_size=200000, ignore_errors=true)
WHERE lower(predicate) LIKE '%troph%' OR lower(predicate) LIKE '%habitat%';
""")
os.remove(f"{SCRATCH}/eol_traits.csv")
con.sql("""
SELECT CASE WHEN lower(predicate) LIKE '%troph%' THEN 'trophic' ELSE 'habitat' END kind,
       count(*) n_rows, count(DISTINCT scientific_name) taxa
FROM eol_traits GROUP BY 1
""").show()

# %% [markdown]
# ## 4. Ecoregions — RESOLVE Ecoregions 2017 (CC-BY 4.0)
# 847 ecoregions with geometry, for the occurrence-in-polygon step
# (species-per-ecoregion) later. (Originally WWF ecoregions, dropped in the
# 2026-08-07 license audit: CC-BY-NC. RESOLVE is the CC-BY replacement —
# the swap was first done in-session; this cell is now the producing code.)

# %%
con.sql(f"""
CREATE OR REPLACE TABLE ecoregions AS
SELECT ECO_NAME, ECO_ID::BIGINT AS ECO_ID, BIOME_NAME AS BIOME, REALM, geom
FROM ST_Read('{DATA}/resolve/Ecoregions2017.shp');
""")
con.sql("SELECT REALM, count(DISTINCT ECO_ID) ecoregions FROM ecoregions GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## 5. First coverage numbers — the start of the audit
# Substrate-wide: how many taxa carry each field. (Join quality improves once we
# resolve GloBI/EOL names onto `taxon` — this is the raw floor.)

# %%
con.sql("""
SELECT
  (SELECT count(*) FROM taxon)                                                   AS backbone_species,
  (SELECT count(DISTINCT scientific_name) FROM eol_traits
     WHERE lower(predicate) LIKE '%troph%')                                      AS eol_trophic_taxa,
  (SELECT count(DISTINCT scientific_name) FROM eol_traits
     WHERE lower(predicate) LIKE '%habitat%')                                    AS eol_habitat_taxa,
  (SELECT count(DISTINCT sourceTaxonName) FROM interactions)                     AS globi_source_taxa,
  (SELECT count(DISTINCT ECO_ID) FROM ecoregions)                               AS ecoregions
""").show()

# %% [markdown]
# ## Next steps (not in this notebook yet)
# - **GBIF occurrences** — query the S3 Parquet in place with DuckDB
#   (`httpfs`), spatial-join to `ecoregions` → species-per-ecoregion.
# - **Name resolution** — map GloBI/EOL `scientific_name` onto `taxon.canonicalName`
#   (+ synonyms) so coverage counts are on the resolved backbone, not raw strings.
# - **Trait crosswalk** — EOL terms / Wikidata Q-IDs → 5 trophic buckets; ENVO → 29 habitat labels.
# - **Wikipedia field notes** — deferred (disk); fetch only the species pages you need.
# - **CrypticBio** — extract just the cryptic-group→species mapping from HF, in place.
# - **The per-ecoregion / per-taxonomic-group coverage cross-tab** — the real audit.

# %%
con.sql("SHOW TABLES").show()
print("PolygroveDB written to ../../polygrove.duckdb")
con.close()
