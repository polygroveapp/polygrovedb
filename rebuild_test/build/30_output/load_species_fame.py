# %% [markdown]
# # PolygroveDB — materialize species_fame from the cached fame artifacts
#
# The rebuild test caught this table being built ad-hoc and never scripted (drift).
# Sources, both versioned in data/ (dump-first, offline):
#   wiki_fame.json          — [species_id, canonicalName, wiki_title, bytes, refs, cited, notes[]]
#                             (refreshed by wiki_fame_fieldnotes.py, the manual 25GB-dump job)
#   wikidata_sitelinks.json — {species_id: sitelink count} (refreshed by fetch_wikidata_fame.py)

# %%
import duckdb, json, time
t0=time.time()
fame=json.load(open('../../data/wiki_fame.json'))
sl=json.load(open('../../data/wikidata_sitelinks.json')) if __import__('os').path.exists('../../data/wikidata_sitelinks.json') else {}
con=duckdb.connect('../../polygrove.duckdb')
con.sql("""CREATE OR REPLACE TABLE species_fame (species_id BIGINT, wiki_title VARCHAR,
  wiki_bytes INTEGER, wiki_refs INTEGER, cited_sentences INTEGER, sitelinks INTEGER)""")
con.executemany("INSERT INTO species_fame VALUES (?,?,?,?,?,?)",
  [(r[0], r[2], r[3], r[4], r[5], sl.get(str(r[0]))) for r in fame])
n=con.sql("SELECT count(*), count(sitelinks) FROM species_fame").fetchone()
print(f"species_fame: {n[0]:,} rows, {n[1]:,} with sitelinks  ({time.time()-t0:.0f}s)")
con.close()
