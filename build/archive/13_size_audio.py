# %% [markdown]
# # PolygroveDB — size + audio candidates (step 13)
#
# The last two untested questions.
# - **Size** ("which is bigger/heavier?") — EOL body-mass/length traits. Numeric,
#   so the answer is always well-defined and comparisons always discriminate;
#   the question is coverage. EOL splits it across specific predicates.
# - **Audio** ("which call is this?") — Commons audio files. Sampled by class via
#   the Commons API (can't scan all species), estimating coverage where it matters
#   (birds/amphibians) vs. where it doesn't (plants/fungi).

# %%
import duckdb, subprocess, io, csv, re, time, requests
con = duckdb.connect("../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
DATA="../data"; csv.field_size_limit(1<<24)

# %% [markdown]
# ## Size — find body-size predicates in terms.csv, then extract from traits.csv

# %%
# body-size predicate URIs (name has body mass/length, exclude egg/testes/ratio)
size_preds=set()
p=subprocess.Popen(f"unzip -p {DATA}/eol_traits_all.zip trait_bank/terms.csv",shell=True,stdout=subprocess.PIPE)
r=csv.reader(io.TextIOWrapper(p.stdout,encoding="utf-8",errors="replace")); h=next(r)
ui,ni=h.index('uri'),h.index('name')
for row in r:
    if len(row)>ni:
        n=row[ni].lower()
        if (('body mass' in n or 'body length' in n or 'total length' in n or 'head-body' in n)
            and not any(x in n for x in ('egg','testes','ratio','clutch','relative'))):
            size_preds.add(row[ui])
print(f"body-size predicates: {len(size_preds)}")

# stream traits.csv, keep numeric body-size rows
rows=[]
p=subprocess.Popen(f"unzip -p {DATA}/eol_traits_all.zip trait_bank/traits.csv",shell=True,stdout=subprocess.PIPE)
r=csv.reader(io.TextIOWrapper(p.stdout,encoding="utf-8",errors="replace")); h=next(r)
pi=h.index('predicate'); si=h.index('scientific_name'); mi=h.index('normal_measurement'); mi2=h.index('measurement')
for row in r:
    if len(row)>max(pi,si,mi,mi2) and row[pi] in size_preds:
        val=row[mi] or row[mi2]
        if val:
            rows.append({"scientific_name":row[si],"predicate":row[pi].rsplit('/',1)[-1],"value":val})
import pandas as pd
sdf=pd.DataFrame(rows)
con.sql("CREATE OR REPLACE TABLE eol_size AS SELECT * FROM sdf")
con.sql("""CREATE OR REPLACE TABLE species_size AS
  SELECT DISTINCT n.species_id, e.predicate, e.value
  FROM eol_size e JOIN name2sid n ON n.norm_name = norm(e.scientific_name);""")
con.sql("SELECT count(DISTINCT species_id) AS species_with_size, count(*) AS measurements FROM species_size").show()
con.sql("SELECT predicate, count(DISTINCT species_id) AS sp FROM species_size GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## Audio — sample species per class, check Commons for audio files

# %%
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (drew@polygrove.io)"})
def has_audio(name):
    try:
        r=S.get("https://commons.wikimedia.org/w/api.php",params={"action":"query","format":"json",
            "generator":"search","gsrsearch":f'{name} filetype:audio',"gsrnamespace":6,"gsrlimit":3,
            "prop":"imageinfo","iiprop":"mime"},timeout=15)
        pages=(r.json().get("query",{}) or {}).get("pages",{})
        return any((p.get("imageinfo",[{}])[0].get("mime","")).startswith(("audio","application/ogg")) for p in pages.values())
    except Exception: return None

print("audio coverage by class (sample of 12 species each):")
for cls in ["Aves","Amphibia","Mammalia","Insecta","Magnoliopsida"]:
    sample=[r[0] for r in con.execute(
        "SELECT canonicalName FROM species WHERE class=? ORDER BY random() LIMIT 12",[cls]).fetchall()]
    hits=0; n=0
    for sp in sample:
        a=has_audio(sp); time.sleep(0.3)
        if a is not None: n+=1; hits+=int(a)
    print(f"  {cls:<15} {hits}/{n} have audio on Commons")

# %%
con.close()
