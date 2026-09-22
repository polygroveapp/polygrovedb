# %% [markdown]
# # PolygroveDB — mollusc body mass from the EOL dump (source)
#
# The whole phylum Mollusca had ONE size record (the tiger slug via AnimalTraits):
# 567 molluscs sat one fact short. The raw EOL trait dump carries `bodyMassWet`
# for ~11k molluscs (resource 30) — units unstated in the dump, validated as GRAMS
# against known weights (Cepaea nemoralis 1.6 g, Lissachatina fulica 58.5 g,
# queen conch 728 g). Phylum-gated so a name collision can't paste a snail's mass
# onto something else. Confidence: measured (EOL-aggregated).

# %%
import duckdb, time
t0=time.time()
con=duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""
CREATE OR REPLACE TABLE mollusc_mass AS
SELECT s.species_id, round(max(TRY_CAST(t.normal_measurement AS DOUBLE)),3) AS mass_g
FROM read_csv('../../data/trait_bank/traits.csv', header=true, quote='"', ignore_errors=true, all_varchar=true) t
JOIN name2sid n2 ON n2.norm_name=norm(t.scientific_name)
JOIN species s ON s.species_id=n2.species_id AND s.phylum='Mollusca'
WHERE t.predicate='http://eol.org/schema/terms/bodyMassWet'
  AND TRY_CAST(t.normal_measurement AS DOUBLE) > 0
GROUP BY 1;""")
print("mollusc_mass:", con.sql("SELECT count(*) FROM mollusc_mass").fetchone()[0], f"species  ({time.time()-t0:.0f}s)")
con.close()
