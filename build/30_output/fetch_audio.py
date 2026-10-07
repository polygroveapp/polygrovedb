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
            w=float(r.headers.get("Retry-After") or 60); time.sleep(w); waited+=w; continue
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
# ONE request at a time, ~4/s: three in flight got the address rate-limited (2026-10-06)
def paced(jobs):
    for j in jobs:
        yield fetch(j); time.sleep(0.25)
with ThreadPoolExecutor(1) as ex:
    for i,(sid,clips) in enumerate(paced(todo)):
        if clips is None: continue
        res[str(sid)]=clips
        if clips: found+=1
        if (i+1)%250==0:
            json.dump(res,open(OUT,"w"))
            print(f"  {i+1:,}/{len(todo):,} · {found:,} with sound · {(time.time()-t0)/60:.0f}m", flush=True)
json.dump(res,open(OUT,"w"))
have=sum(1 for v in res.values() if v)
print(f"DONE: {have:,}/{len(deck):,} deck species have licensed audio", flush=True)
