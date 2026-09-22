# %% [markdown]
# # PolygroveDB — categorical diet (source): what it eats, as measured proportions
#
# Species-level food-web edges (GloBI) are sparse for most vertebrates — 8,449 birds
# were blocked on Q4 alone. But what birds/mammals/reptiles/amphibians eat IS
# recorded scientifically — categorically: TetrapodTraits (diet proportions for
# 33k tetrapods) and EltonTraits (10 diet classes, % for birds + mammals). Measured
# data → a "known to eat → insects / seeds / fruit" answer with distractors. Used as
# Q4's FALLBACK when no species-level edge clears the evidence floor (user rule).

# %%
import duckdb, time
t0=time.time()
con=duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
LABEL={'inv':'insects and other invertebrates','vend':'mammals and birds','vect':'reptiles and amphibians',
       'vfish':'fish','vunk':'other vertebrates','scav':'carrion','fruit':'fruit','nect':'nectar','seed':'seeds','plant':'plants'}
con.sql("CREATE OR REPLACE TABLE diet_categories (species_id BIGINT, category VARCHAR, frac DOUBLE, source VARCHAR)")
def unpivot(src, csv_opts, sci_col, cols, scale, extra_where=""):
    expr=(lambda col: f"CASE WHEN TRY_CAST(t.\"{col}\" AS DOUBLE)>0 THEN NULL END") if scale is None else (lambda col: f"TRY_CAST(t.\"{col}\" AS DOUBLE)/{scale}")
    flag=(lambda col: f"TRY_CAST(t.\"{col}\" AS DOUBLE)") if scale is None else (lambda col: f"TRY_CAST(t.\"{col}\" AS DOUBLE)")
    union=" UNION ALL ".join(f"SELECT n.species_id, '{cat}' cat, {expr(col)} frac, {flag(col)} present "
                             f"FROM src t JOIN name2sid n ON n.norm_name=norm(t.\"{sci_col}\") {extra_where}"
                             for cat,col in cols)
    con.sql(f"""INSERT INTO diet_categories
      WITH src AS (SELECT * FROM read_csv({csv_opts}))
      SELECT species_id, cat, max(frac), '{src}' FROM ({union}) WHERE present > 0 GROUP BY 1,2;""")
# TetrapodTraits: proportions 0-1, measured diets only
unpivot('TetrapodTraits', "'../../data/tetrapodtraits/TetrapodTraits.csv', header=true, ignore_errors=true, sample_size=-1",
        'Scientific.Name',
        [('inv','DietInv'),('vend','DietVend'),('vect','DietVect'),('vfish','DietVfish'),
         ('fruit','DietFruit'),('nect','DietNect'),('seed','DietSeed'),('plant','DietPlant')],
        None, "WHERE TRY_CAST(t.SourceDiet AS VARCHAR) IS NOT NULL")   # 0/1 PRESENCE flags, not shares
# EltonTraits birds + mammals: percentages 0-100
for f in ('elton_BirdFuncDat.txt','elton_MamFuncDat.txt'):
    unpivot('EltonTraits', f"'../../data/{f}', delim='\\t', header=true, ignore_errors=true, all_varchar=true, sample_size=-1",
            'Scientific',
            [('inv','Diet-Inv'),('vend','Diet-Vend'),('vect','Diet-Vect'),('vfish','Diet-Vfish'),('vunk','Diet-Vunk'),
             ('scav','Diet-Scav'),('fruit','Diet-Fruit'),('nect','Diet-Nect'),('seed','Diet-Seed'),('plant','Diet-PlantO')],
            100.0)
con.executemany("UPDATE diet_categories SET category=? WHERE category=?", [(v,k) for k,v in LABEL.items()])
r=con.sql("SELECT count(DISTINCT species_id), count(*) FROM diet_categories").fetchone()
print(f"diet_categories: {r[0]:,} species, {r[1]:,} rows  ({time.time()-t0:.0f}s)")
for sp in ['Turdus migratorius','Haliaeetus leucocephalus','Bubo scandiacus','Vulpes vulpes']:
    print("  ",sp, con.sql("""SELECT category||' '||coalesce(round(frac*100)::int::varchar||'%','present') FROM diet_categories d JOIN species s USING(species_id)
      WHERE s.canonicalName=? ORDER BY frac DESC NULLS LAST, category LIMIT 3""",params=[sp]).fetchall())
con.close()
