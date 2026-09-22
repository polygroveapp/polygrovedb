# %% [markdown]
# # PolygroveDB — plant lifeform groups from WCVP (step: derive)
#
# The game's Plant group splits into the user's final category set (2026-09-09):
# Tree · Tree/Shrub · Shrub · Subshrub · Perennial Herb · Annual Herb · Epiphyte,
# residual 'Plant'. Folding rules: combined values take the FIRST-listed form
# ("annual or perennial" → Annual Herb); biennials ride with annuals (short-lived
# monocarps); geophytes (bulbs/rhizomes/tubers) are Perennial Herbs; lianas,
# climbers, helophytes etc stay 'Plant'. SYNONYM-AWARE: a deck name that is a
# WCVP synonym (Mahonia repens → Berberis) follows accepted_plant_name_id to the
# accepted row's lifeform — direct accepted matches win over synonym routes.
# Output: `plant_lifeform(species_id, lifeform, raw)`.

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""CREATE OR REPLACE TEMP MACRO lifecat(lf) AS
  CASE WHEN lf IS NULL OR lf='' THEN NULL
       WHEN lf LIKE '%epiphyt%' THEN 'Epiphyte'
       WHEN lf LIKE '%tree%' AND lf LIKE '%shrub%' THEN 'Tree/Shrub'
       WHEN lf LIKE '%tree%' THEN 'Tree'
       WHEN lf LIKE '%subshrub%' THEN 'Subshrub'
       WHEN lf LIKE '%shrub%' THEN 'Shrub'
       WHEN lf LIKE '%geophyte%' THEN 'Geophyte'   -- own category (user, 2026-09-09): bulbs/tubers/rhizomes
       -- Perennial Herb = FULLY perennial only (user, 2026-09-09); ANY annual/
       -- biennial mention ('annual or perennial' etc) goes to Annual/Biennial
       WHEN lf LIKE '%annual%' OR lf LIKE '%biennial%' THEN 'Annual/Biennial Herb'
       WHEN lf LIKE '%perennial%' THEN 'Perennial Herb'
       ELSE 'Plant' END""")

# %%
con.sql("""
CREATE OR REPLACE TEMP TABLE wcvp AS
SELECT plant_name_id, accepted_plant_name_id, taxon_name, taxon_status,
       lower(lifeform_description) AS lf
FROM read_csv('../../data/wcvp_names.csv', delim='|', header=true, quote='"', ignore_errors=true)
WHERE taxon_rank='Species';
""")
con.sql("""
CREATE OR REPLACE TABLE plant_lifeform AS
WITH acc AS (          -- lifeform lives on ACCEPTED rows
  SELECT plant_name_id, taxon_name, lf FROM wcvp WHERE taxon_status='Accepted' AND lf<>''),
routes AS (
  -- pri 0: the name IS the accepted name · pri 1: the name is a synonym of it
  SELECT a.taxon_name AS match_name, a.lf, 0 AS pri FROM acc a
  UNION ALL
  SELECT w.taxon_name, a.lf, 1
  FROM wcvp w JOIN acc a ON a.plant_name_id=w.accepted_plant_name_id
  WHERE w.taxon_status<>'Accepted')
SELECT n.species_id,
  arg_min(lifecat(r.lf), lpad(r.pri::VARCHAR,2,'0')||'|'||r.lf) AS lifeform,
  arg_min(r.lf,          lpad(r.pri::VARCHAR,2,'0')||'|'||r.lf) AS raw
FROM routes r
JOIN name2sid n ON n.norm_name = norm(r.match_name)
JOIN species s ON s.species_id = n.species_id AND s.kingdom='Plantae'
GROUP BY n.species_id;
""")
con.sql("SELECT lifeform, count(*) n FROM plant_lifeform GROUP BY 1 ORDER BY 2 DESC").show(max_rows=15)
con.sql("""SELECT count(*) deck_plants, count(pl.species_id) with_lifeform
FROM catalog c JOIN species s USING(species_id)
LEFT JOIN plant_lifeform pl USING(species_id) WHERE s.kingdom='Plantae'""").show()
con.close()
print(f"done ({time.time()-t0:.0f}s)")
