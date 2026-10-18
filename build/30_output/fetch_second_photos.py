# %% [markdown]
# # PolygroveDB — a second photo per species for the quiz's last question
#
# Q6 "Is this your card?" showed the very photo on the card, so it could be
# answered by remembering the picture (user, 2026-10-18: "for the last question
# don't put the original photo of the animal if we can, put a second photo of
# the species"). For every card that gets Q6 this takes another photo of the
# species from iNaturalist's taxon photos: openly licensed only (CC0, CC BY,
# CC BY-SA; the app may be sold), never the photo the card already shows.
# Resumable: names → iNaturalist ids share build/cache/inat_taxa.json with
# fetch_inat_taxa.py; the taxon photo lists go to build/cache/inat_taxon_photos.json.
#
# Output: explorer/data/second_photos.json  {card id: {url, page, by, lic}}

# %%
import json, os, re, time, urllib.error, urllib.parse, urllib.request
# the same request and licence helpers as fetch_inat_taxa.py
UA = {"User-Agent": "PolygroveDB-build/0.1 (card-game DB; polygrovedb.pages.dev)", "Accept": "application/json"}
OK_LIC = {"cc0": "CC0", "cc-by": "CC BY", "cc-by-sa": "CC BY-SA"}
def get(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(30 * (attempt + 1)); continue
            if e.code == 404: return None
            time.sleep(5)
        except Exception: time.sleep(5)
    return None

def licensed(p):
    lic = (p or {}).get("license_code")
    if lic not in OK_LIC: return None
    url = p.get("medium_url") or (p.get("url") or "").replace("/square.", "/medium.")
    if not url: return None
    return {"url": url, "page": f"https://www.inaturalist.org/photos/{p['id']}", "by": (p.get("attribution") or "").replace("(c) ", "").split(", some rights")[0].split(", uploaded")[0], "lic": OK_LIC[lic]}


HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TAXA = os.path.join(ROOT, "build", "cache", "inat_taxa.json")
TPH = os.path.join(ROOT, "build", "cache", "inat_taxon_photos.json")
OUT = os.path.join(ROOT, "explorer", "data", "second_photos.json")
cards = json.load(open(os.path.join(ROOT, "explorer", "data", "catalog.json")))
photos = json.load(open(os.path.join(ROOT, "explorer", "data", "photos.json")))
inat_p = json.load(open(os.path.join(ROOT, "explorer", "data", "inat_photos.json")))
taxa = json.load(open(TAXA)) if os.path.exists(TAXA) else {}
tph = json.load(open(TPH)) if os.path.exists(TPH) else {}
want = [c for c in cards if len(c.get("lookAlikes") or []) >= 2]
t0 = time.time()

# 1 · the iNaturalist id of each species (one search per name not yet looked up)
todo = [c for c in want if c["sci"] not in taxa]
print(f"{len(want)} cards get Q6 · {len(todo)} names to look up", flush=True)
for i, c in enumerate(todo):
    j = get(f"https://api.inaturalist.org/v1/taxa?q={urllib.parse.quote(c['sci'])}&rank=species&per_page=3") or {}
    hit = next((t for t in j.get("results", []) if t.get("name", "").lower() == c["sci"].lower()), None)
    taxa[c["sci"]] = {"id": hit["id"], "name": hit.get("preferred_common_name") or None, "photo": licensed(hit.get("default_photo"))} if hit else {"id": None}
    if (i + 1) % 100 == 0:
        json.dump(taxa, open(TAXA, "w")); print(f"  names {i+1}/{len(todo)}  ({(time.time()-t0)/60:.1f}m)", flush=True)
    time.sleep(0.7)   # well under iNaturalist's 60/min guidance
json.dump(taxa, open(TAXA, "w"))

# 2 · each taxon's photos, thirty taxa per call
ids = sorted({str(taxa[c["sci"]]["id"]) for c in want if (taxa.get(c["sci"]) or {}).get("id")} - set(tph))
print(f"{len(ids)} taxa to fetch photos for", flush=True)
for k in range(0, len(ids), 30):
    chunk = ids[k:k + 30]
    j = get(f"https://api.inaturalist.org/v1/taxa/{','.join(chunk)}") or {}
    got = {str(r["id"]): [p for p in (licensed(tp.get("photo")) for tp in r.get("taxon_photos", [])) if p][:6] for r in j.get("results", [])}
    for t in chunk: tph[t] = got.get(t, [])
    if (k // 30 + 1) % 20 == 0:
        json.dump(tph, open(TPH, "w")); print(f"  photos {k+30}/{len(ids)}  ({(time.time()-t0)/60:.1f}m)", flush=True)
    time.sleep(1.0)
json.dump(tph, open(TPH, "w"))

# 3 · pick: the first licensed photo that is not the one on the card. A Commons
# copy of an iNaturalist photo usually carries its photo number in the file
# name, so a number found in the card's Wikipedia URL rules that photo out too.
pid = lambda p: re.search(r"/photos/(\d+)", p["page"]).group(1)
out = {}
for c in want:
    tid = (taxa.get(c["sci"]) or {}).get("id")
    if not tid: continue
    shown = photos.get(c["id"]) or ""
    own = inat_p.get(c["id"])
    for p in tph.get(str(tid), []):
        n = pid(p)
        if own and pid(own) == n: continue
        if n in shown: continue
        out[c["id"]] = p; break
json.dump(out, open(OUT, "w"), separators=(",", ":"))
print(f"second photos: {len(out)} of {len(want)} Q6 cards  ({(time.time()-t0)/60:.1f}m)")
