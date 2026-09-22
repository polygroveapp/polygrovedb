# %% [markdown]
# # PolygroveDB — photos.json: card id → Wikimedia CDN thumbnail URL
#
# The explorer's Ecoregions hex-cluster views show one tiny hex per deck
# species; the runtime per-species Wikipedia walk can't fill 2,600 hexes, so
# thumbs are resolved once at build time and baked into the SVG (user,
# 2026-09-09: "actually do that for all of them").
#
# Uses the MediaWiki ACTION API (`prop=pageimages`, 50 titles per request,
# ~208 requests for the whole deck) — the REST summary endpoint one-request-
# per-title approach got the IP 429'd across all of Wikimedia. On 429 this
# script backs off in minutes-long steps and resumes; lookups are cached in
# build/cache/wiki_thumbs.json so reruns only fetch new cards.

# %%
import json, os, time, urllib.request, urllib.parse

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
CACHE = os.path.join(ROOT, "build", "cache", "wiki_thumbs.json")
OUT = os.path.join(ROOT, "explorer", "data", "photos.json")
UA = {"User-Agent": "PolygroveDB-build/0.1 (offline card-game DB; local build script)"}
API = "https://en.wikipedia.org/w/api.php"
THUMB_W = 96  # hexes render at 15px, pan-zoom up to 9x

cards = json.load(open(os.path.join(ROOT, "explorer", "data", "catalog.json")))
con = duckdb.connect(os.path.join(ROOT, "polygrove.duckdb"), read_only=True)
fame = dict(con.sql("SELECT species_id, wiki_title FROM species_fame WHERE wiki_title IS NOT NULL").fetchall())
con.close()

cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
titles = {c["id"]: (fame.get(c["species_id"]) or c["sci"]) for c in cards}
todo = sorted({t for t in titles.values() if t not in cache})
print(f"{len(cards)} cards; {len(todo)} titles to fetch ({len(cache)} cached)", flush=True)


def api_batch(chunk):
    """One pageimages query for ≤50 titles → {requested title: thumb url or ''}."""
    data = urllib.parse.urlencode({
        "action": "query", "format": "json", "formatversion": "2",
        "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": str(THUMB_W),
        "redirects": "1", "maxlag": "5", "titles": "|".join(chunk),
    }).encode()
    backoff = 90
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(API, data=data, headers=UA), timeout=30) as r:
                d = json.load(r)
            if "error" in d and d["error"].get("code") == "maxlag":
                time.sleep(20); continue
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  429 — sleeping {backoff}s", flush=True)
                time.sleep(backoff); backoff = min(backoff * 2, 900)
            else:
                raise
        except Exception as e:
            print(f"  {type(e).__name__} — retrying in 30s", flush=True)
            time.sleep(30)
    q = d.get("query", {})
    fwd = {}  # requested → final title, through normalization then redirects
    for m in q.get("normalized", []) + q.get("redirects", []):
        fwd[m["from"]] = m["to"]
    thumb = {}
    for p in q.get("pages", []):
        t = (p.get("thumbnail") or {}).get("source", "")
        thumb[p.get("title")] = t
    out = {}
    for t in chunk:
        f = t
        for _ in range(3):
            f = fwd.get(f, f)
        out[t] = thumb.get(f, "")
    return out


for ci in range(0, len(todo), 50):
    chunk = todo[ci:ci + 50]
    cache.update(api_batch(chunk))
    if (ci // 50) % 20 == 0:
        json.dump(cache, open(CACHE, "w"))
        print(f"  {ci + len(chunk)}/{len(todo)}", flush=True)
    time.sleep(1.2)
json.dump(cache, open(CACHE, "w"))

out = {cid: cache[t] for cid, t in sorted(titles.items()) if cache.get(t)}
json.dump(out, open(OUT, "w"), separators=(",", ":"))
print(f"photos.json: {len(out)}/{len(cards)} cards with a thumb; {os.path.getsize(OUT)//1024} KB")
