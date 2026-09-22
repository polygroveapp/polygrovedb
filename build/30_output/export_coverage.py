# %% [markdown]
# # PolygroveDB — coverage.json for the explorer's Coverage tab
#
# One row per card_pool class: described species, per-signal counts (feeding /
# size / biome) and finished deck cards. Replaces the ad-hoc Aug-21 dump with a
# DAG step so the tab tracks the DB — in particular the 'Fish' synthetic class
# (the backbone's class-less bony fish) now shows up as its own frontier row.

# %%
import duckdb, json
con = duckdb.connect("../../polygrove.duckdb")
rows = con.sql("""
WITH eff AS (
  -- plants report under their WCVP lifeform group (user, 2026-09-09); lifeform-less
  -- plants stay under their taxonomic class and roll up to 'Plant' in the explorer
  SELECT CASE WHEN s.kingdom='Plantae' AND pl.lifeform IS NOT NULL AND pl.lifeform<>'Plant'
              THEN pl.lifeform ELSE cp.class END AS class,
         cp.species_id, cp.has_feeding, cp.has_size, cp.has_biome
  FROM card_pool cp
  JOIN species s USING (species_id)
  LEFT JOIN plant_lifeform pl USING (species_id)
  WHERE cp.class IS NOT NULL)
SELECT class,
       count(*)          AS total,
       sum(has_feeding)  AS feeding,
       sum(has_size)     AS size,
       sum(has_biome)    AS biome,
       count(*) FILTER (species_id IN (SELECT species_id FROM catalog)) AS deck
FROM eff
GROUP BY 1
HAVING count(*) > 5000 OR sum(has_feeding) > 0
ORDER BY total DESC, class
""").fetchall()
out = [{"class": c, "total": t, "feeding": int(f), "size": int(s), "biome": int(b), "deck": int(d)}
       for c, t, f, s, b, d in rows]
json.dump(out, open("../../explorer/data/coverage.json", "w"), separators=(",", ":"))
fish = next((r for r in out if r["class"] == "Fish"), None)
print(f"coverage.json: {len(out)} classes; Fish row: {fish}")
con.close()
