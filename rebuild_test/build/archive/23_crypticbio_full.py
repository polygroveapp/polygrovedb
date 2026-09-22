# %% [markdown]
# # PolygroveDB — full CrypticBio ingest: confusions + photos + common names (step 23)
#
# nb11 used a 40-part SAMPLE and pulled only the confusion mapping. CrypticBio's
# full schema also has `vernacularName[]` (common names). This reads ALL 627 parts,
# column-pruned + batched, and builds two tables resolved to species_id:
# - `species_confusions`  (rebuilt at full scale — the Q6 look-alikes)
# - `species_common_names`(display names)
# (CrypticBio also has photo urls; we deliberately do NOT persist them — sourced
#  cards use Wikipedia, custom cards use the user's own iNaturalist observation.)

# %%
import duckdb, requests, time
con = duckdb.connect("../polygrove.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs;")
# HuggingFace rate-limits (429) rapid parquet reads → throttle + auto-retry
con.sql("SET threads=3;")
con.sql("SET http_retries=8;")
con.sql("SET http_retry_wait_ms=3000;")
con.sql("SET http_retry_backoff=2;")
con.sql("SET http_timeout=120000;")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

S = requests.Session(); S.headers.update({"User-Agent": "PolygroveDB/0.1"})
def list_parts():
    for attempt in range(8):
        r = S.get("https://huggingface.co/api/datasets/gmanolache/CrypticBio/parquet", timeout=30)
        try:
            return r.json()['default']['train']
        except (KeyError, ValueError):
            wait = 10*(attempt+1)
            print(f"  listing call rate-limited (HTTP {r.status_code}) — waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("could not list CrypticBio parts after retries")

# prefer the LOCAL dump (data/crypticbio/) — fully offline; fall back to streaming
import glob
local = sorted(glob.glob("../data/crypticbio/*.parquet"))
parts = local if local else list_parts()
print(f"CrypticBio source: {'LOCAL dump' if local else 'HuggingFace stream'} — {len(parts)} parts", flush=True)

# staging: one row per (batch, species) — merged at the end
con.sql("CREATE OR REPLACE TABLE cb_stage (sci VARCHAR, photos VARCHAR[], common VARCHAR[], grp VARCHAR[])")

BATCH = 25
t0 = time.time()
nb = (len(parts)+BATCH-1)//BATCH
for i in range(0, len(parts), BATCH):
    chunk = parts[i:i+BATCH]
    urls = "[" + ",".join(f"'{u}'" for u in chunk) + "]"
    q = f"""INSERT INTO cb_stage
    SELECT scientificName AS sci, (array_agg(url))[1:5] AS photos,
           any_value(vernacularName) AS common, any_value(crypticGroup) AS grp
    FROM read_parquet({urls}) WHERE scientificName IS NOT NULL GROUP BY scientificName;"""
    for attempt in range(5):                       # python-level retry on top of DuckDB retries
        try:
            con.sql(q); break
        except Exception as e:
            if attempt == 4: raise
            wait = 15*(attempt+1)
            print(f"    batch {i//BATCH+1} attempt {attempt+1} failed ({str(e)[:50]}) — waiting {wait}s", flush=True)
            time.sleep(wait)
    print(f"  batch {i//BATCH+1}/{nb}  parts {i}-{i+len(chunk)-1}  ({time.time()-t0:.0f}s elapsed)", flush=True)
    time.sleep(4)                                   # be polite between batches

# %% [markdown]
# ## Merge batches → one row per species, then resolve to species_id

# %%
con.sql("""
CREATE OR REPLACE TABLE cb_species AS
SELECT sci,
       (flatten(array_agg(photos)))[1:5]                         AS photos,
       any_value(common) FILTER (WHERE len(common) > 0)          AS common,
       list_distinct(flatten(array_agg(grp)))                    AS grp
FROM cb_stage GROUP BY sci;
""")
print("distinct CrypticBio species:", con.sql("SELECT count(*) FROM cb_species").fetchone()[0])

# confusions (rebuild full): explode grp → directed pairs, resolve both ends
con.sql("""
CREATE OR REPLACE TABLE species_confusions AS
SELECT DISTINCT n1.species_id AS species_id, n2.species_id AS confused_with_species_id,
       round(1.0/greatest(len(c.grp),1), 4) AS confusion_strength, 'crypticbio' AS source
FROM cb_species c, UNNEST(c.grp) AS t(partner)
JOIN name2sid n1 ON n1.norm_name = norm(c.sci)
JOIN name2sid n2 ON n2.norm_name = norm(t.partner)
WHERE n1.species_id <> n2.species_id;
""")

# NOTE: CrypticBio also has photo urls, but we do NOT persist them — sourced
# cards use Wikipedia lead images; custom (user) cards use the user's own
# iNaturalist observation. The pre-pulled photo bank had no role, so it's dropped.

# common names: one per species (first non-null)
con.sql("""
CREATE OR REPLACE TABLE species_common_names AS
SELECT DISTINCT ON (n.species_id) n.species_id, c.common[1] AS common_name, 'crypticbio' AS source
FROM cb_species c JOIN name2sid n ON n.norm_name = norm(c.sci)
WHERE len(c.common) > 0
ORDER BY n.species_id;
""")

# %% [markdown]
# ## Score it

# %%
for tbl, label in [("species_confusions","confusion pairs"),("species_common_names","common names")]:
    con.sql(f"SELECT count(*) AS rows, count(DISTINCT species_id) AS species FROM {tbl}").show()
print("species with >=2 look-alikes (Q6 hard-mode eligible):",
      con.sql("SELECT count(*) FROM (SELECT species_id FROM species_confusions GROUP BY 1 HAVING count(*)>=2)").fetchone()[0])
con.sql("DROP TABLE cb_stage;")
con.close()
