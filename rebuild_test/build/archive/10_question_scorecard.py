# %% [markdown]
# # PolygroveDB — question viability scorecard (step 10)
#
# For each candidate quiz question, look past the coverage count at whether the
# data makes a *good question*: is the answer **varied and meaningful**, or
# dominated by one useless value (like habitat's "marine benthic biome")?
#
# Key metric: **top-value concentration** — what % of covered species share the
# single most-common answer. High concentration = a coin-flip, not a question.

# %%
import duckdb
con = duckdb.connect("../polygrove.duckdb")

def profile(name, sql_values):
    """sql_values must SELECT (species_id, value). Returns coverage, distinct, top%."""
    con.sql(f"CREATE OR REPLACE TEMP TABLE _v AS {sql_values}")
    cov = con.sql("SELECT count(DISTINCT species_id) FROM _v").fetchone()[0]
    nd  = con.sql("SELECT count(DISTINCT value) FROM _v").fetchone()[0]
    top = con.sql("SELECT value, count(DISTINCT species_id) c FROM _v GROUP BY 1 ORDER BY 2 DESC LIMIT 1").fetchone()
    topshare = round(100*top[1]/cov,0) if cov else 0
    print(f"\n{'─'*70}\n{name}")
    print(f"  coverage: {cov:,} species | distinct answers: {nd} | top answer '{str(top[0])[:32]}' = {topshare:.0f}%")
    con.sql("SELECT value AS answer, count(DISTINCT species_id) AS species FROM _v GROUP BY 1 ORDER BY 2 DESC LIMIT 6").show()
    return cov, nd, topshare

# %% [markdown]
# ## L0 Taxonomy  — GBIF class

# %%
profile("L0 TAXONOMY (class)",
        "SELECT species_id, class AS value FROM species WHERE class IS NOT NULL")

# %% [markdown]
# ## L1 Trophic role  — and the animal-only split (plants/fungi are trivial floors)

# %%
profile("L1 TROPHIC (all)",
        "SELECT species_id, role AS value FROM species_trophic_roles")
profile("L1 TROPHIC (animals only — the real question)",
        """SELECT r.species_id, r.role AS value FROM species_trophic_roles r
           JOIN species s ON s.species_id=r.species_id AND s.kingdom='Animalia'""")

# %% [markdown]
# ## L2 Habitat  — EOL (the one we just found is weak)

# %%
profile("L2 HABITAT (EOL labels)",
        "SELECT sh.species_id, hc.label AS value FROM species_habitats sh JOIN habitat_crosswalk hc ON hc.code=sh.habitat_raw")

# %% [markdown]
# ## L4 Biome  — from occurrence × ecoregion (sample)

# %%
profile("L4 BIOME (occurrence sample)",
        """SELECT DISTINCT se.species_id, e.BIOME AS value
           FROM species_ecoregions se JOIN ecoregions e ON e.ECO_ID=se.ecoregion_id WHERE e.BIOME IS NOT NULL""")

# %% [markdown]
# ## Food web  — GloBI interactions (the discarded candidate)

# %%
profile("FOOD WEB (interaction type)",
        """SELECT gn.accepted_id AS species_id, i.interactionTypeName AS value
           FROM interactions i JOIN gbif_names gn ON gn.norm_name = lower(i.sourceTaxonName)""")

# %% [markdown]
# ## Read-out: what the data supports (and what it doesn't)
# - L3 ORIGIN: not built — establishmentMeans known-sparse (weak, like habitat).
# - L5 CONFUSION: needs CrypticBio (not extracted).
# - SEASONALITY / SIZE / AUDIO: data exists in the dumps (GBIF dates, EOL body
#   mass, Commons audio) but not yet extracted — candidates to test next.
# Good question = high coverage AND low top-answer concentration AND meaningful values.

# %%
con.close()
