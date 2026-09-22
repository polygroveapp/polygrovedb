# %% [markdown]
# # PolygroveDB — common names from the GBIF backbone dump (substrate)
#
# Cards read "Puma concolor" twice; the demo reads "Mountain Lion". The backbone
# dump we already have carries VernacularName.tsv (98MB) — same CC-BY source,
# zero new downloads. One best English name per species: most-attested wins
# (count of records per name), shortest breaks ties (drops "Northern Raccoon"
# vs "Raccoon" style verbosity when counts tie).

# %%
import duckdb, time
t0=time.time()
con = duckdb.connect("../../polygrove.duckdb")
con.sql("""
CREATE OR REPLACE TABLE species_common_names AS
WITH v AS (
  SELECT taxonID, trim(vernacularName) AS vn, count(*) AS n
  FROM read_csv('../../data/backbone/VernacularName.tsv', delim='\t', header=true,
                quote='', ignore_errors=true, sample_size=-1)
  WHERE language='en' AND vernacularName IS NOT NULL AND length(vernacularName) BETWEEN 3 AND 40
  GROUP BY 1,2
)
-- rank: (1) name used for ONE species beats group names like "Cobweb Spiders" that GBIF
-- attaches to many; (2) plain-ASCII beats accented (language-mislabeled rows, e.g. "Pèlopèe");
-- (3) most attested; (4) shortest.
, spread AS (SELECT vn, count(DISTINCT taxonID) n_sp FROM v GROUP BY 1)
SELECT s.species_id,
       -- single STRING sort key so exact ties (capitalization variants like
       -- "Lance-tipped"/"Lance-Tipped") resolve identically on every run: the name
       -- itself is the final tiebreak (caught by the clean-rebuild byte-diff)
       arg_max(v.vn, printf('%d%d%010d%03d',
                      CASE WHEN sp.n_sp=1 THEN 1 ELSE 0 END,
                      CASE WHEN regexp_matches(v.vn, '^[A-Za-z0-9 .''-]+$') THEN 1 ELSE 0 END,
                      v.n, 999-length(v.vn)) || v.vn) AS common_name
FROM v JOIN species s ON s.species_id = v.taxonID JOIN spread sp ON sp.vn = v.vn
GROUP BY 1;
""")
print("species with an English common name:",
      con.sql("SELECT count(*) FROM species_common_names").fetchone()[0], f"({time.time()-t0:.0f}s)")

# %%
# iconic sanity — names players expect
for sp in ['Puma concolor','Panthera leo','Haliaeetus leucocephalus','Danaus plexippus',
           'Ailuropoda melanoleuca','Procyon lotor','Sequoia sempervirens']:
    r=con.sql("""SELECT cn.common_name FROM species_common_names cn
      JOIN species s ON s.species_id=cn.species_id WHERE s.canonicalName=? LIMIT 1""",params=[sp]).fetchone()
    print(f"  {sp:26} -> {r[0] if r else '(none)'}")
con.close()
