# %% [markdown]
# # PolygroveDB — plant heights from the open trait databases (2026-10-05)
#
# EOL's height predicates give only ~4,000 of 447,000 plant species a size, so
# 13,000+ plants sit one fact short of a card (the user's own sightings among
# them). Two open sources fill the gap:
#
# - **BIEN** (Botanical Information and Ecology Network, CC BY): ~10 million
#   "whole plant height" records plus "maximum whole plant height". Pulled with
#   `bien_height_pull.py` from BIEN's public PostgreSQL (the same public,
#   read-only access the BIEN R package uses) into `data/bien_height.csv`, one
#   row per species × unit × access with the record count, median and max.
# - **AusTraits** (CC BY 4.0, Zenodo): `plant_height` for ~23,000 Australian
#   taxa, mostly "maximum" values from floras. `data/austraits-7.0.0/traits.csv`.
#
# Output: `plant_height_open(species_id, src, height_cm)` — one height per
# species per source, resolved to the backbone with the standard name resolver.
# `generate_catalog.py` unions it with EOL; among same-priority sources the
# largest value wins, so a card reads the plant's full-grown height.
#
# What "height" means here: AusTraits and BIEN's "maximum whole plant height"
# are stated maxima; BIEN's "whole plant height" is individual measurements,
# where the median of a plot survey underestimates a tree. So for that trait
# the per-species MAX is used when backed by at least 3 records and the
# median otherwise (a lone bad entry can't make a 2 m shrub a 90 m tree), all
# capped at 130 m — taller than any known plant.

# %%
import duckdb, os
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

parts = []
if os.path.exists("../../data/bien_height.csv"):
    # units: BIEN stores height in metres; anything else is converted or dropped
    parts.append("""
    SELECT n.species_id, 'BIEN' AS src,
           max(CASE WHEN b.unit='m' THEN b.h*100 WHEN b.unit='cm' THEN b.h WHEN b.unit='mm' THEN b.h/10 END) AS height_cm
    FROM (SELECT sci, unit, access, CASE WHEN n >= 3 THEN h_max ELSE h_med END AS h
          FROM read_csv('../../data/bien_height.csv', header=true)) b
    JOIN name2sid n ON n.norm_name = norm(b.sci)
    WHERE b.h IS NOT NULL AND b.access = 'public'
    GROUP BY n.species_id HAVING height_cm > 0 AND height_cm <= 13000""")
if os.path.exists("../../data/austraits-7.0.0/traits.csv"):
    parts.append("""
    SELECT n.species_id, 'AusTraits' AS src, max(TRY_CAST(a.value AS DOUBLE)) * 100 AS height_cm
    FROM read_csv('../../data/austraits-7.0.0/traits.csv', all_varchar=true, quote='"', escape='"', sample_size=-1) a
    JOIN name2sid n ON n.norm_name = norm(a.taxon_name)
    WHERE a.trait_name = 'plant_height' AND a.unit = 'm' AND a.value_type IN ('maximum','mean')
      AND TRY_CAST(a.value AS DOUBLE) > 0
    GROUP BY n.species_id HAVING height_cm <= 13000""")
assert parts, "neither data/bien_height.csv nor data/austraits-7.0.0/traits.csv is present"

con.sql(f"CREATE OR REPLACE TABLE plant_height_open AS {' UNION ALL '.join(parts)};")
for src, n in con.sql("SELECT src, count(*) FROM plant_height_open GROUP BY 1 ORDER BY 1").fetchall():
    print(f"{src}: {n:,} species with a height")
new = con.sql("""SELECT count(DISTINCT p.species_id) FROM plant_height_open p
                 LEFT JOIN plant_fungi_size e USING (species_id) WHERE e.species_id IS NULL""").fetchone()[0]
print(f"species EOL had no height for: {new:,}")
