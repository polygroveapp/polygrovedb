# %% [markdown]
# # PolygroveDB — coverage audit (step 7)
#
# The "how good is the substrate" cross-tab. Covers the **structured layers we
# actually built** — trophic, habitat, ecoregion mapping, facts. NOTE: field
# notes (`facts`) are only the 6 demo species and `photos` isn't built, so the
# English-content / card-eligibility part is intentionally *not* measured here;
# this is the structured-substrate quality (the equitable part).
#
# Also note `species_ecoregions` is from a 40-part occurrence sample, so the
# per-ecoregion view is a sample, not the full snapshot.

# %%
import duckdb
con = duckdb.connect("../../polygrove.duckdb")

# one row per species with boolean coverage flags (semi-joins, fast)
con.sql("""
CREATE OR REPLACE TABLE audit AS
SELECT s.species_id, s.kingdom, s.class,
  s.species_id IN (SELECT species_id FROM species_trophic_roles) AS has_trophic,
  s.species_id IN (SELECT species_id FROM species_habitats)      AS has_habitat,
  s.species_id IN (SELECT species_id FROM species_ecoregions)    AS has_ecoregion,
  s.species_id IN (SELECT species_id FROM facts)                 AS has_fact
FROM species s;
""")

# %% [markdown]
# ## Substrate-wide coverage (all 2.6M backbone species)

# %%
con.sql("""
SELECT count(*) AS species,
  round(100.0*avg(has_trophic::int),1)   AS pct_trophic,
  round(100.0*avg(has_habitat::int),1)   AS pct_habitat,
  round(100.0*avg(has_ecoregion::int),1) AS pct_ecoregion_sample,
  round(100.0*avg((has_trophic AND has_habitat)::int),1) AS pct_trophic_and_habitat
FROM audit
""").show()

# %% [markdown]
# ## Retention by taxonomic class — the bias view
# Where the structured substrate is strong vs. thin. (`pct_struct` = has trophic
# AND habitat — the two structured facts a card needs.)

# %%
con.sql("""
SELECT class,
  count(*) AS species,
  round(100.0*avg(has_trophic::int),1)   AS pct_trophic,
  round(100.0*avg(has_habitat::int),1)   AS pct_habitat,
  round(100.0*avg((has_trophic AND has_habitat)::int),1) AS pct_struct
FROM audit WHERE class IS NOT NULL
GROUP BY 1 HAVING count(*) > 10000
ORDER BY species DESC LIMIT 18
""").show()

# %% [markdown]
# ## Per-ecoregion view (from the occurrence sample)
# Species richness per ecoregion, and how trait-complete that pool is — the
# "is this place playable" read. Sample-based, so absolute counts scale up.

# %%
con.sql("""
WITH per_eco AS (
  SELECT se.ecoregion_id,
         count(DISTINCT se.species_id) AS species,
         count(DISTINCT CASE WHEN a.has_trophic AND a.has_habitat THEN se.species_id END) AS struct_complete
  FROM species_ecoregions se JOIN audit a ON a.species_id = se.species_id
  GROUP BY 1
)
SELECT ec.ECO_NAME, ec.REALM, p.species,
       round(100.0*p.struct_complete/p.species,1) AS pct_struct_complete
FROM per_eco p JOIN (SELECT DISTINCT ECO_ID, ECO_NAME, REALM FROM ecoregions) ec ON ec.ECO_ID = p.ecoregion_id
ORDER BY p.species DESC LIMIT 12
""").show()

# %% [markdown]
# ## Realm-level summary (bias by biogeographic realm)

# %%
con.sql("""
SELECT ec.REALM,
       count(DISTINCT se.ecoregion_id) AS ecoregions,
       count(DISTINCT se.species_id)   AS species
FROM species_ecoregions se
JOIN (SELECT DISTINCT ECO_ID, REALM FROM ecoregions) ec ON ec.ECO_ID = se.ecoregion_id
GROUP BY 1 ORDER BY species DESC
""").show()

# %% [markdown]
# ## Read-out
# - Structured coverage (trophic/habitat) is what's measured; field-note + photo
#   (English-content) coverage is the known gap, pending scale-up.
# - Realm skew = the observer bias (Nearctic/Palearctic dominate the sample).
# - Full occurrence run raises the per-ecoregion counts and fills tropical realms.

# %%
con.close()
