# %% [markdown]
# # PolygroveDB — iNaturalist fill-ins: photos and common names the deck lacks
#
# 1,924 cards had no photo (Wikipedia's lead image is the only source) and
# 2,769 had no common name (user, 2026-10-08: a blank "Acantholycosa pedestris"
# card). iNaturalist's taxa API gives, per species, a default photo with its
# licence and attribution, every taxon photo, and the preferred common name.
# Only photos under CC0, CC BY or CC BY-SA are taken: the app may be sold, so
# non-commercial licences are out (user, 2026-10-07, of the audio). Resumable:
# build/cache/inat_taxa.json holds every lookup, reruns only fetch new cards.
#
# Output: explorer/data/inat_photos.json  {card id: {url, page, by, lic}}
#         build/cache/inat_names.json      {species_id: common name}   (→ generate_catalog)

# %%
import json, os, sys, time, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CACHE = os.path.join(ROOT, "build", "cache", "inat_taxa.json")
OUT_P = os.path.join(ROOT, "explorer", "data", "inat_photos.json")
OUT_N = os.path.join(ROOT, "build", "cache", "inat_names.json")
UA = {"User-Agent": "PolygroveDB-build/0.1 (card-game DB; polygrovedb.pages.dev)", "Accept": "application/json"}
OK_LIC = {"cc0": "CC0", "cc-by": "CC BY", "cc-by-sa": "CC BY-SA"}
cards = json.load(open(os.path.join(ROOT, "explorer", "data", "catalog.json")))
photos = json.load(open(os.path.join(ROOT, "explorer", "data", "photos.json")))
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
need = [c for c in cards if not photos.get(c["id"]) or c["name"].lower() == c["sci"].lower()]
# …and every species a quiz option names that is not a card (generate_catalog.py writes the list):
# an answer option should have a picture and an English name too (user, 2026-10-08)
_qo = os.path.join(ROOT, "build", "cache", "quiz_options.json")
_card_sids = {c["species_id"] for c in cards}
extras = [{"sci": sci, "species_id": int(sid)} for sid, sci in (json.load(open(_qo)).items() if os.path.exists(_qo) else []) if int(sid) not in _card_sids]
need += extras
todo = [c for c in need if c["sci"] not in cache]
print(f"{len(need)} cards want a photo or a name · {len(todo)} to look up", flush=True)

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

t0 = time.time()
for i, c in enumerate(todo):
    q = urllib.parse.quote(c["sci"])
    j = get(f"https://api.inaturalist.org/v1/taxa?q={q}&rank=species&per_page=3") or {}
    hit = next((t for t in j.get("results", []) if t.get("name", "").lower() == c["sci"].lower()), None)
    rec = {"id": None}
    if hit:
        rec = {"id": hit["id"], "name": hit.get("preferred_common_name") or None, "photo": licensed(hit.get("default_photo"))}
        if rec["photo"] is None and hit.get("default_photo"):
            # the default photo is not licensed for us: look through the taxon's other photos
            full = get(f"https://api.inaturalist.org/v1/taxa/{hit['id']}") or {}
            for tp in (full.get("results") or [{}])[0].get("taxon_photos", []):
                rec["photo"] = licensed(tp.get("photo"))
                if rec["photo"]: break
    cache[c["sci"]] = rec
    if (i + 1) % 50 == 0:
        json.dump(cache, open(CACHE, "w")); print(f"  {i+1}/{len(todo)}  ({(time.time()-t0)/60:.1f}m)", flush=True)
    time.sleep(0.7)   # well under iNaturalist's 60/min guidance
json.dump(cache, open(CACHE, "w"))

inat_photos, names = {}, {}
for c in cards:
    rec = cache.get(c["sci"]) or {}
    if not photos.get(c["id"]) and rec.get("photo"): inat_photos[c["id"]] = rec["photo"]
    # every card iNaturalist has a name for, whether or not the catalog already shows it:
    # the catalog applies it only where no other English name exists, and a rerun must
    # not drop names a previous run applied (2026-11-10: the second run wrote only the
    # still-Latin cards, so 1,142 cards reverted to Latin and lost their photo links)
    if rec.get("name"): names[str(c["species_id"])] = rec["name"]
for e in extras:
    rec = cache.get(e["sci"]) or {}
    if rec.get("name"): names[str(e["species_id"])] = rec["name"]
json.dump(inat_photos, open(OUT_P, "w"), separators=(",", ":")); json.dump(names, open(OUT_N, "w"), indent=0)
print(f"photos found: {len(inat_photos)} of {sum(1 for c in cards if not photos.get(c['id']))} missing · names found: {len(names)} of {sum(1 for c in cards if c['name'].lower()==c['sci'].lower())} Latin-only  ({(time.time()-t0)/60:.1f}m)")
