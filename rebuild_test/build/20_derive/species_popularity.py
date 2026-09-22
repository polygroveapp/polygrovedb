# %% [markdown]
# # PolygroveDB — species popularity = total observation records (derive)
#
# From the full-occurrence grid (data/occ_grid.duckdb): sum of license-clean GBIF
# observations per species. "How often do people actually record this species" —
# drives Q3's comparison opponent (compare against species players KNOW), local-deck
# ordering, and the field-note commissioning order. Pure observation counts, not the
# mixed range-area weights in species_ecoregions.

# %%
import duckdb, time
t0=time.time()
con=duckdb.connect("../../polygrove.duckdb")
con.sql("ATTACH '../../data/occ_grid.duckdb' AS og (READ_ONLY);")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""
CREATE OR REPLACE TABLE species_popularity AS
SELECT n.species_id, sum(g.n)::BIGINT AS obs_count
FROM og.grid2 g JOIN name2sid n ON n.norm_name = norm(g.species)
GROUP BY 1;""")
r=con.sql("SELECT count(*), max(obs_count) FROM species_popularity").fetchone()
print(f"species_popularity: {r[0]:,} species, max {r[1]:,} observations  ({time.time()-t0:.0f}s)")
for row in con.sql("""SELECT coalesce(cn.common_name,s.canonicalName), p.obs_count FROM species_popularity p
  JOIN species s USING(species_id) LEFT JOIN species_common_names cn USING(species_id)
  ORDER BY obs_count DESC LIMIT 8""").fetchall(): print(f"  {row[1]:>10,}  {row[0]}")
con.close()
