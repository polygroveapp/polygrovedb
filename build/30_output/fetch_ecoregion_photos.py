# %% [markdown]
# # PolygroveDB — one photo per ecoregion (Merlin-style habitat imagery, PROTOTYPE)
#
# The insight (user, 2026-09-08): habitat photos belong to the ECOREGION, not the
# species — 847 images serve all 8,743 cards, because every card already knows its
# primary ecoregion. Source: each RESOLVE ecoregion's own English Wikipedia article
# (most have one, usually with a representative landscape as lead image).
# Per image we fetch the Commons license and keep only CC0 / CC-BY / CC-BY-SA /
# public domain, with author for the attribution line. App layer, like all
# Wikipedia-derived content. Output: data/ecoregion_photos.json {eco_id: {...}}.

# %%
import duckdb, json, os, time, requests
OUT="../../data/ecoregion_photos.json"
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
ecos=con.sql("SELECT ECO_ID, ECO_NAME FROM pg.ecoregions WHERE ECO_NAME IS NOT NULL ORDER BY ECO_ID").fetchall()
con.close()
res=json.load(open(OUT)) if os.path.exists(OUT) else {}
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (open species database; habitat imagery prototype)"})
def get_json(url, params, tries=5):
    """Wikipedia rate-limits bursts with an HTML error page — back off and retry
    rather than silently losing 827 of 847 lookups (the prototype's first run)."""
    for a in range(tries):
        r=S.get(url, params=params, timeout=30)
        if r.status_code==200 and 'json' in (r.headers.get('content-type') or ''):
            return r.json()
        time.sleep(3*(a+1))
    raise RuntimeError(f"{url} kept failing: {r.status_code} {(r.headers.get('content-type') or '')[:40]}")
API="https://en.wikipedia.org/w/api.php"
COMMONS="https://commons.wikimedia.org/w/api.php"
OK_LIC=('cc0','cc by','cc by-sa','cc-by','cc-by-sa','public domain','pd')
def lead_image(title):
    r=get_json(API, {"action":"query","format":"json","redirects":1,"titles":title,
        "prop":"pageimages","piprop":"name|original|thumbnail","pithumbsize":640})
    pages=r.get("query",{}).get("pages",{})
    for p in pages.values():
        if "missing" in p: return None
        if p.get("pageimage"):
            return {"file":p["pageimage"], "url":p.get("original",{}).get("source"),
                    "thumb":p.get("thumbnail",{}).get("source"), "article":p.get("title")}
    return None
def license_of(filename):
    r=get_json(COMMONS, {"action":"query","format":"json","titles":f"File:{filename}",
        "prop":"imageinfo","iiprop":"extmetadata","iiextmetadatafilter":"LicenseShortName|Artist"})
    for p in r.get("query",{}).get("pages",{}).values():
        ii=(p.get("imageinfo") or [{}])[0].get("extmetadata",{})
        lic=(ii.get("LicenseShortName",{}).get("value") or "").strip()
        artist=(ii.get("Artist",{}).get("value") or "")
        import re; artist=re.sub(r"<[^>]+>","",artist).strip()[:60]
        return lic, artist
    return "", ""
t0=time.time(); found=badlic=miss=errs=0
for i,(eid,name) in enumerate(ecos):
    if str(eid) in res: continue
    try:
        img=lead_image(name)
        if not img or not (img.get("url") or img.get("thumb")):
            res[str(eid)]=None; miss+=1
        else:
            lic,artist=license_of(img["file"])
            if any(k in lic.lower() for k in OK_LIC):
                res[str(eid)]={"url":img.get("url"),"thumb":img.get("thumb"),
                               "article":img.get("article"),"license":lic,"by":artist}
                found+=1
            else:
                res[str(eid)]=None; badlic+=1
    except Exception as e:
        errs+=1
        if errs<=3 or errs%50==0: print(f"  ERROR at {name[:36]}: {str(e)[:90]}", flush=True)
    if (i+1)%100==0:
        json.dump(res,open(OUT,"w"))
        print(f"  {i+1}/{len(ecos)} · usable {found} · no-article/no-image {miss} · unusable license {badlic} · {(time.time()-t0)/60:.1f}m", flush=True)
    time.sleep(0.3)
json.dump(res,open(OUT,"w"))
tot=sum(1 for v in res.values() if v)
print(f"DONE: {tot}/{len(ecos)} ecoregions have a licensed photo ({found} new, {miss} missing, {badlic} bad license, {errs} errors)", flush=True)
