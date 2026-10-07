# %% [markdown]
# # PolygroveDB — sound recordings per deck species (GBIF occurrence media API)
#
# For each deck card: up to 3 sound recordings, CC0/CC-BY only (NC excluded per the
# license standard), with recordist for attribution. iNaturalist + Cornell/ML datasets
# come through GBIF; xeno-canto's NC records are filtered out by the license gate.
# Output: data/species_audio.json (app layer — we LINK to hosted audio, never copy it).
# Cached: reruns only fetch species not already in the JSON.

# %%
import duckdb, json, os, time, requests
OUT="../../data/species_audio.json"
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
deck=con.sql("SELECT species_id, s.canonicalName FROM pg.catalog c JOIN pg.species s USING(species_id) ORDER BY species_id").fetchall()
con.close()
res=json.load(open(OUT)) if os.path.exists(OUT) else {}
todo=[(sid,n) for sid,n in deck if not res.get(str(sid))]   # retry quiet species too — server-side license filter may find what the unfiltered sample missed
print(f"{len(deck):,} deck species · {len(todo):,} to fetch", flush=True)
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (open species database)"})
OK_LIC=('http://creativecommons.org/publicdomain/zero/1.0/','http://creativecommons.org/licenses/by/4.0/',
        'https://creativecommons.org/publicdomain/zero/1.0/','https://creativecommons.org/licenses/by/4.0/')
t0=time.time(); found=0
from concurrent.futures import ThreadPoolExecutor
def fetch(job):
    sid,name=job
    waited=0
    attempt=0
    while attempt<4:
        try:
            r=S.get("https://api.gbif.org/v1/occurrence/search",
                    params={"taxonKey":sid,"mediaType":"Sound","limit":50,"license":["CC0_1_0","CC_BY_4_0"]}, timeout=30)
        except Exception:
            attempt+=1; time.sleep(2*attempt); continue
        if r.status_code==429:
            # over GBIF's limit (2026-10-06: a six-thread run got the address
            # throttled for a long while): wait it out, up to an hour per species,
            # without spending an attempt — the limit lifts, the pull resumes
            if waited>=3600: return sid,None
            w=max(60.0,float(r.headers.get("Retry-After") or 60)); time.sleep(w); waited+=w; continue
        if r.status_code in (500,502,503,504):
            attempt+=1; time.sleep(3*attempt); continue
        if r.status_code!=200: return sid,None
        j=r.json()
        # under load GBIF has answered 200 with count>0 and an empty page (the
        # American robin came back [] against 2,376 matching records): retry
        if not j.get("results") and j.get("count",0)>0:
            attempt+=1; time.sleep(2*attempt); continue
        clips=[]
        for occ in j.get("results",[]):
            for m in occ.get("media",[]):
                if m.get("type")!="Sound" or not m.get("identifier"): continue
                lic=(m.get("license") or occ.get("license") or '')
                if lic not in OK_LIC and occ.get("license") not in ('CC0_1_0','CC_BY_4_0'): continue
                clips.append({"url":m["identifier"],
                              "by":m.get("rightsHolder") or occ.get("rightsHolder") or occ.get("recordedBy") or "",
                              "lic":"CC0" if "zero" in lic or occ.get("license")=='CC0_1_0' else "CC-BY",
                              "ds":occ.get("datasetName","")[:40]})
                if len(clips)>=3: break
            if len(clips)>=3: break
        return sid,clips
    return sid,None   # missing key = retried on next run
# TWO PASSES (2026-10-06, after GBIF throttled the one-request-per-species
# pattern: "Too many API requests… request a download"):
#  1. batches of 40 species in ONE faceted request (limit=0, facet=speciesKey)
#     say which of them have any CC0/CC-BY sound at all — most have none and
#     are settled with ~350 requests instead of 14,000
#  2. one request each for the species that do, to fetch up to three clips
# Paced at one request per 1.5 s; a 429 rests for a minute.
def facet_batch(sids):
    """-> (total count, {speciesKey: count}) for the batch, or None on failure"""
    for attempt in range(6):
        try:
            r=S.get("https://api.gbif.org/v1/occurrence/search",
                    params={"taxonKey":sids,"mediaType":"Sound","license":["CC0_1_0","CC_BY_4_0"],"limit":0,"facet":"speciesKey","facetLimit":200}, timeout=60)
        except Exception:
            time.sleep(5); continue
        if r.status_code==429 or r.status_code>=500: time.sleep(60 if r.status_code==429 else 5); continue
        if r.status_code!=200: return None
        j=r.json(); fc=(j.get("facets") or [{}])[0].get("counts",[])
        return j.get("count",0), {int(f["name"]):f.get("count",0) for f in fc}
    return None
withsound=[]; t0=time.time(); batches=[todo[i:i+40] for i in range(0,len(todo),40)]
for bi,batch in enumerate(batches):
    got=facet_batch([sid for sid,_ in batch])
    if got is None: continue             # left out of res → retried next run
    total,hits=got
    ids={sid for sid,_ in batch}
    # occurrences are faceted by their ACCEPTED species key: a deck id that is
    # a synonym matches the search but never appears in the facet (the
    # helmeted guineafowl's 15 recordings were missed this way, 2026-10-06).
    # When the matched keys don't account for every record, the unmatched
    # species of the batch stay candidates for pass 2.
    accounted=sum(n for k,n in hits.items() if k in ids)
    for sid,_ in batch:
        if sid in hits or (total>accounted): withsound.append((sid,_))
        else: res[str(sid)]=[]
    if (bi+1)%25==0:
        json.dump(res,open(OUT,"w"))
        print(f"  pass 1: {bi+1}/{len(batches)} batches · {len(withsound):,} candidates so far · {(time.time()-t0)/60:.0f}m", flush=True)
json.dump(res,open(OUT,"w"))
print(f"pass 1 done: {len(withsound):,} of {len(todo):,} species have licensed sound ({(time.time()-t0)/60:.0f}m)", flush=True)
for i,(sid,clips) in enumerate(fetch(j) for j in withsound):
    if clips is None: continue
    res[str(sid)]=clips
    if clips: found+=1
    if (i+1)%100==0:
        json.dump(res,open(OUT,"w"))
        print(f"  pass 2: {i+1:,}/{len(withsound):,} · {found:,} with sound · {(time.time()-t0)/60:.0f}m", flush=True)
    time.sleep(1.5)
json.dump(res,open(OUT,"w"))
have=sum(1 for v in res.values() if v)
print(f"DONE: {have:,}/{len(deck):,} deck species have licensed audio", flush=True)
