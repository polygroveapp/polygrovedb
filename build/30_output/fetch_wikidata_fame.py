# Global fame for deck species = Wikidata SITELINK COUNT (how many language editions of
# Wikipedia have an article). Language-neutral, CC0. Replaces the English-only cited-
# sentence proxy for ranking (user rule: "a worse version of the global one").
# Items matched by GBIF taxon id (P846 = our species_id), then by taxon name (P225).
# Cached dump-first to data/wikidata_sitelinks.json.
import duckdb, json, time, requests, os
OUT="../../data/wikidata_sitelinks.json"
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")
# BOOTSTRAP (clean rebuild): `catalog` doesn't exist until generate_catalog runs, which
# itself reads this script's cache. On a fresh DB, run offline from the versioned cache
# (complete for the shipped deck); new deck members are fetched on the NEXT run.
try:
    deck=con.sql("SELECT species_id, canonicalName FROM catalog ORDER BY 1").fetchall()
except duckdb.CatalogException:
    deck=[]
    print("no catalog yet (clean rebuild) — using cached sitelinks only", flush=True)
con.close()
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (open species database; contact via github)"})
URL="https://query.wikidata.org/sparql"
def sparql(q):
    for attempt in range(5):
        r=S.get(URL, params={"query":q,"format":"json"}, timeout=120)
        if r.status_code==200: return r.json()["results"]["bindings"]
        time.sleep(5*(attempt+1))
    raise SystemExit(f"SPARQL failed: {r.status_code} {r.text[:200]}")
res=json.load(open(OUT)) if os.path.exists(OUT) else {}
todo=[(sid,n) for sid,n in deck if str(sid) not in res]
print(f"{len(deck):,} deck species, {len(todo):,} to fetch", flush=True)
# pass 1: by GBIF id
for i in range(0,len(todo),250):
    batch=todo[i:i+250]
    vals=" ".join(f'"{sid}"' for sid,_ in batch)
    q=f'SELECT ?gbif ?n WHERE {{ VALUES ?gbif {{ {vals} }} ?item wdt:P846 ?gbif ; wikibase:sitelinks ?n . }}'
    for b in sparql(q): res[b["gbif"]["value"]]=int(b["n"]["value"])
    print(f"  P846 batch {i//250+1}: {len(res):,} matched", flush=True); time.sleep(1.5)
# pass 2: by taxon name for the rest
rest=[(sid,n) for sid,n in todo if str(sid) not in res]
name2sid={n:sid for sid,n in rest}
for i in range(0,len(rest),250):
    batch=rest[i:i+250]
    vals=" ".join('"'+n.replace('"','')+'"' for _,n in batch)
    q=f'SELECT ?name ?n WHERE {{ VALUES ?name {{ {vals} }} ?item wdt:P225 ?name ; wikibase:sitelinks ?n . }}'
    for b in sparql(q):
        sid=name2sid.get(b["name"]["value"])
        if sid is not None: res[str(sid)]=max(res.get(str(sid),0), int(b["n"]["value"]))
    print(f"  P225 batch {i//250+1}: {len(res):,} matched", flush=True); time.sleep(1.5)
json.dump(res, open(OUT,"w"))
print(f"DONE: {len(res):,}/{len(deck):,} deck species have a sitelink count -> {OUT}")
