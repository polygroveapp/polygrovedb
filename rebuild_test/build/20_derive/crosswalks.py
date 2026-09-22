# %% [markdown]
# # PolygroveDB — trait crosswalks (step 5)
#
# Trophic/habitat values come from mixed vocabularies — **Wikidata Q-IDs**,
# **OBO ontology terms** (ECOCORE, ENVO), and readable strings. This notebook:
#
# 1. Fetches the English **label** for every distinct value (Wikidata API +
#    EBI OLS for the ontology terms).
# 2. Auto-maps clear labels to the 5 trophic buckets; leaves ambiguous ones
#    NULL for human review (sorted by species impact).
# 3. Rebuilds animal trophic roles using the crosswalk — the payoff.
# 4. Does the same label-resolution for the 30 ENVO habitat codes.
#
# The crosswalk tables are meant to be **reviewed/curated** — this fills the
# obvious rows and surfaces the high-impact unmapped ones.

# %%
import duckdb, re, requests, time
import pandas as pd
# Wikimedia + EBI APIs require a descriptive User-Agent, else they return empty/403.
S = requests.Session()
S.headers.update({"User-Agent": "PolygroveDB/0.1 (drew@polygrove.io)", "Accept": "application/json"})
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# offline term→label cache (self-dump) — the API only fills terms not yet cached,
# so a re-run with the cache present is fully offline.
import os
CACHE = {}
if os.path.exists("../../data/crosswalk_labels.csv"):
    _c = pd.read_csv("../../data/crosswalk_labels.csv")
    CACHE = dict(zip(_c.term.astype(str), _c.label))
    print(f"loaded {len(CACHE)} cached crosswalk labels (offline)")

def wd_labels(qids):
    out={}
    for i in range(0,len(qids),50):
        try:
            r=S.get("https://www.wikidata.org/w/api.php",
                params={"action":"wbgetentities","ids":"|".join(qids[i:i+50]),
                        "props":"labels","languages":"en","format":"json"},timeout=25)
            for q,e in r.json().get("entities",{}).items():
                out[q]=(e.get("labels",{}).get("en",{}) or {}).get("value")
        except Exception as ex:
            print("  wd batch failed:", type(ex).__name__)
        time.sleep(0.3)
    return out

def ols_label(short_form):
    try:
        r=S.get("https://www.ebi.ac.uk/ols4/api/terms",
            params={"short_form":short_form},timeout=20)
        t=r.json().get("_embedded",{}).get("terms",[])
        return t[0]["label"] if t else None
    except Exception: return None

def to_bucket(label):
    if not label: return None
    l=label.lower()
    if re.search(r'omnivor',l): return 'omnivore'
    if re.search(r'carnivor|predat|piscivor|insectivor|invertivor|vertivor|mammalivor|molluscivor|zoophag|faunivor|sanguinivor|hematophag|prey.?feed',l): return 'carnivore'
    if re.search(r'herbivor|brows|graz|foliv|frugivor|granivor|nectarivor|palynivor|floriv|phytophag|algae.?eat',l): return 'herbivore'
    if re.search(r'decompos|saprotroph|saproph|saprob|detritivor|deposit.?feed|coprophag|scaveng|xylophag',l): return 'decomposer'
    if re.search(r'autotroph|photosynth|primary producer|producer|chemotroph',l): return 'producer'
    return None   # ambiguous → review

# %% [markdown]
# ## Resolve labels for every distinct trophic value

# %%
vals = con.sql("""
SELECT coalesce(nullif(name_en,''), regexp_replace(value_uri,'^.*/','')) AS val,
       count(DISTINCT scientific_name) AS sp
FROM eol_traits WHERE lower(predicate) LIKE '%troph%' AND coalesce(nullif(name_en,''),value_uri) IS NOT NULL
GROUP BY 1
""").df()
qids = [v for v in vals.val if re.fullmatch(r'Q[0-9]+', str(v)) and str(v) not in CACHE]
wd = wd_labels(qids)
def resolve(v):
    v=str(v)
    if v in CACHE: return CACHE[v]
    if re.fullmatch(r'Q[0-9]+', v): return wd.get(v)
    if re.fullmatch(r'[A-Z]+_[0-9]+', v): return ols_label(v)
    return v
vals["label"]  = vals.val.map(resolve)
vals["bucket"] = vals.label.map(to_bucket)
con.sql("CREATE OR REPLACE TABLE trophic_crosswalk AS SELECT * FROM vals")

mapped_sp = con.sql("SELECT sum(sp) FROM trophic_crosswalk WHERE bucket IS NOT NULL").fetchone()[0]
total_sp  = con.sql("SELECT sum(sp) FROM trophic_crosswalk").fetchone()[0]
print(f"auto-mapped values: {con.sql('SELECT count(*) FROM trophic_crosswalk WHERE bucket IS NOT NULL').fetchone()[0]}/{len(vals)}"
      f"   covering ~{mapped_sp:,} of ~{total_sp:,} species-value hits")
print("\n=== auto-mapped (sample) ===")
con.sql("SELECT val, label, bucket, sp FROM trophic_crosswalk WHERE bucket IS NOT NULL ORDER BY sp DESC LIMIT 12").show()
print("=== TOP UNMAPPED — needs human review (by species impact) ===")
con.sql("SELECT val, label, sp FROM trophic_crosswalk WHERE bucket IS NULL ORDER BY sp DESC LIMIT 12").show()

# %% [markdown]
# ## Rebuild animal trophic roles using the crosswalk (the payoff)

# %%
con.sql("""
CREATE OR REPLACE TABLE species_trophic_roles AS
SELECT species_id,'producer' AS role,'taxonomy' AS source FROM species WHERE kingdom='Plantae'
  OR class IN ('Phaeophyceae','Chlorophyta','Rhodophyta','Bacillariophyceae','Chrysophyceae','Xanthophyceae','Ulvophyceae','Florideophyceae')
UNION ALL
SELECT species_id,'decomposer','taxonomy' FROM species WHERE kingdom='Fungi'
UNION ALL
SELECT DISTINCT g.accepted_id, x.bucket, 'eol'
FROM (SELECT scientific_name, coalesce(nullif(name_en,''), regexp_replace(value_uri,'^.*/','')) val
      FROM eol_traits WHERE lower(predicate) LIKE '%troph%') e
JOIN trophic_crosswalk x ON x.val = e.val AND x.bucket IS NOT NULL
JOIN gbif_names g ON g.norm_name = norm(e.scientific_name)
JOIN species s ON s.species_id = g.accepted_id AND s.kingdom='Animalia';
""")
con.sql("SELECT source, count(DISTINCT species_id) sp FROM species_trophic_roles GROUP BY 1").show()
print("ANIMAL species with a trophic role now:",
  con.sql("""SELECT count(DISTINCT r.species_id) FROM species_trophic_roles r
             JOIN species s ON s.species_id=r.species_id AND s.kingdom='Animalia'""").fetchone()[0],
  "(was 1,584 before the crosswalk)")

# %% [markdown]
# ## Habitat: resolve the 30 ENVO codes to labels

# %%
hvals = con.sql("SELECT habitat_raw AS code, count(DISTINCT species_id) sp FROM species_habitats GROUP BY 1 ORDER BY 2 DESC").df()
def hres(v):
    v=str(v)
    if v in CACHE: return CACHE[v]
    if re.fullmatch(r'Q[0-9]+', v): return wd.get(v) or wd_labels([v]).get(v)
    if re.fullmatch(r'[A-Z]+_[0-9]+', v): return ols_label(v)
    return v
hvals["label"]=hvals.code.map(hres)
con.sql("CREATE OR REPLACE TABLE habitat_crosswalk AS SELECT * FROM hvals")

# refresh the offline cache with any newly-resolved terms
con.sql("""COPY (
  SELECT DISTINCT val AS term, label FROM trophic_crosswalk WHERE label IS NOT NULL AND (regexp_matches(val,'^Q[0-9]+$') OR regexp_matches(val,'^[A-Z]+_[0-9]+$'))
  UNION SELECT DISTINCT code, label FROM habitat_crosswalk WHERE label IS NOT NULL AND (regexp_matches(code,'^Q[0-9]+$') OR regexp_matches(code,'^[A-Z]+_[0-9]+$'))
) TO '../../data/crosswalk_labels.csv' (HEADER, DELIMITER ',');""")
print("refreshed offline cache: data/crosswalk_labels.csv")
print("=== habitat codes → labels (map these to your 29 allowlist labels) ===")
con.sql("SELECT code, label, sp FROM habitat_crosswalk ORDER BY sp DESC LIMIT 15").show()

# %%
con.sql("SHOW TABLES").show()
con.close()
