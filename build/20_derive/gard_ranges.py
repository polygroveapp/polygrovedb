# %% [markdown]
# # PolygroveDB — pure GARD reptile ranges → `reptile_ranges` (step: derive)
#
# The GARD×RESOLVE join from resolve_rejoin.py, kept as its OWN table (2026-09-26):
# species_ecoregions is cumulative (sample scan ∪ GARD ∪ PHYLACINE ∪ the full-scan
# top-up), so it can't serve as "the range". species_ecoregions_rebuild.py reads
# this table (and mammal_ranges) to rebuild membership from clean parts.

# %%
import duckdb, time
t0 = time.time()
con = duckdb.connect("../../polygrove.duckdb")
con.sql("INSTALL spatial; LOAD spatial;")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# ST_MakeValid on BOTH sides: GARD (and hi-res RESOLVE) polygons contain invalid
# rings that throw TopologyException mid-join otherwise
con.sql("""CREATE OR REPLACE TEMP TABLE gard_eco AS
WITH g AS (SELECT binomial, ST_MakeValid(geom) AS geom FROM ST_Read('../../data/gard/Gard_1_7_ranges.shp')),
     e AS (SELECT ECO_ID, ST_MakeValid(geom) AS geom FROM ecoregions)
SELECT g.binomial, e.ECO_ID, ST_Area_Spheroid(ST_Intersection(g.geom, e.geom)) AS overlap
FROM g JOIN e ON ST_Intersects(g.geom, e.geom);""")
print(f"GARD range×ecoregion overlaps: {con.sql('SELECT count(*) FROM gard_eco').fetchone()[0]:,}  ({time.time()-t0:.0f}s)", flush=True)

# weight = overlap area (m² → km²); one row per (species, ecoregion)
con.sql("""CREATE OR REPLACE TABLE reptile_ranges AS
SELECT n.species_id, ge.ECO_ID AS ecoregion_id, greatest((sum(ge.overlap)/1e6)::bigint, 1) AS km2
FROM gard_eco ge JOIN name2sid n ON n.norm_name = norm(ge.binomial)
JOIN species s ON s.species_id = n.species_id
  AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia')
WHERE ge.overlap > 0 AND NOT isnan(ge.overlap)
GROUP BY n.species_id, ge.ECO_ID;""")
print("reptile_ranges:", con.sql("SELECT count(*), count(DISTINCT species_id) FROM reptile_ranges").fetchone(), flush=True)
con.close()
print(f"done ({time.time()-t0:.0f}s)", flush=True)
