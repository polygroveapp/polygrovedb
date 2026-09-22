# %% [markdown]
# # PolygroveDB — ecoregion areas (derive)
#
# Area per ecoregion, used as the DENSITY tiebreaker for a card's primary biome:
# when two ecoregions hold the same number of records, the SMALLER one implies a
# higher concentration — you're likelier to actually encounter the species there
# (user rule, 2026-08-20). Also the basis for future records-per-km² range work.
#
# ST_Area_Spheroid returns NaN on ~half of RESOLVE's polygons (degenerate rings),
# so area is computed per dumped part as planar degrees² scaled by that part's own
# centroid latitude — never NaN, and totals 146.5M km² vs Earth's ~149M land.

# %%
import duckdb, time
t0=time.time()
con=duckdb.connect("../../polygrove.duckdb")
con.sql("INSTALL spatial; LOAD spatial;")
con.sql("""
CREATE OR REPLACE TABLE ecoregion_area AS
WITH parts AS (SELECT ECO_ID, UNNEST(ST_Dump(ST_MakeValid(geom))).geom AS g FROM ecoregions)
SELECT ECO_ID, sum(ST_Area(g)*cos(radians(ST_Y(ST_Centroid(g))))*12365) AS km2
FROM parts GROUP BY 1;""")
r=con.sql("SELECT count(*), round(sum(km2))::bigint, round(min(km2))::bigint, round(max(km2))::bigint FROM ecoregion_area").fetchone()
print(f"ecoregion_area: {r[0]} ecoregions, total {r[1]:,} km² (Earth land ≈149M), range {r[2]:,}–{r[3]:,}  ({time.time()-t0:.0f}s)")
con.close()
