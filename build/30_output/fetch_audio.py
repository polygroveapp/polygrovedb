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
for i,(sid,name) in enumerate(todo):
    try:
        r=S.get("https://api.gbif.org/v1/occurrence/search",
                params={"taxonKey":sid,"mediaType":"Sound","limit":50,"license":["CC0_1_0","CC_BY_4_0"]}, timeout=30)
        clips=[]
        if r.status_code==200:
            for occ in r.json().get("results",[]):
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
        res[str(sid)]=clips
        if clips: found+=1
    except Exception:
        pass          # missing key = retried on next run
    if (i+1)%250==0:
        json.dump(res,open(OUT,"w"))
        print(f"  {i+1:,}/{len(todo):,} · {found:,} with sound · {(time.time()-t0)/60:.0f}m", flush=True)
    time.sleep(0.12)  # ~8 req/s, polite
json.dump(res,open(OUT,"w"))
have=sum(1 for v in res.values() if v)
print(f"DONE: {have:,}/{len(deck):,} deck species have licensed audio", flush=True)
