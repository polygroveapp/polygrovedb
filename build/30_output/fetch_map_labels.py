# %% [markdown]
# # PolygroveDB — map context labels: major cities + national parks
# Cities: Natural Earth populated places (PUBLIC DOMAIN). Parks: Wikidata instances
# of national park incl. subclasses — each country's own equivalent — (CC0).
# Both are app-layer display context. Outputs explorer/data/cities.json / parks.json.

# %%
import json, requests, time
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (map labels; CC0/PD sources)"})
ne=S.get("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson", timeout=120).json()
cities=[]
for f in ne["features"]:
    p=f["properties"]
    pop=p.get("pop_max") or 0
    if pop>=750000 or (p.get("featurecla","").startswith("Admin-0 capital") and pop>=100000):
        cities.append({"type":"Feature","geometry":f["geometry"],
            "properties":{"name":p.get("name"),"pop":pop,"cap":1 if p.get("featurecla","").startswith("Admin-0 capital") else 0}})
cities.sort(key=lambda f:-f["properties"]["pop"])
json.dump({"type":"FeatureCollection","features":cities}, open("../../explorer/data/cities.json","w"), separators=(',',':'))
print(f"cities: {len(cities)} (Natural Earth, public domain)", flush=True)

# sitelinks = cross-language fame, the priority key for label collision-culling
# (parks' answer to cities' population)
q="""SELECT ?p ?pLabel ?coord ?links WHERE {
  ?p wdt:P31/wdt:P279* wd:Q46169 . ?p wdt:P625 ?coord . ?p wikibase:sitelinks ?links .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
r=S.get("https://query.wikidata.org/sparql", params={"query":q,"format":"json"}, timeout=300)
rows=r.json()["results"]["bindings"]
SUFF=[' national park complex',' national park reserve',' national parks reserve',' national preserve',' national recreation area',' national historical park',' national park and preserve',' national park & preserve',' national parks',' national park',
      ' national nature reserve',' nature reserve',' national reserve',' national monument',
      ' provincial park',' state park',' nationalpark',' national marine park',' marine national park']
PREF=['parque nacional natural ','parque nacional ','parque natural ','parc national de la ','parc national des ',
      "parc national de l'",'parc national du ','parc national de ','parc national ','nationalpark ',
      'national park ','taman nasional ','vu\u1eddn qu\u1ed1c gia ']
def strip_name(n):
    """map labels say Yellowstone, not Yellowstone National Park — the dashed ring
    already says park (user, 2026-09-08)"""
    s=n; low=s.lower()
    for p in PREF:
        if low.startswith(p) and len(s)>len(p)+2: s=s[len(p):]; break
    low=s.lower()
    for x in SUFF:
        if low.endswith(x) and len(s)>len(x)+2: s=s[:len(s)-len(x)]; break
    return s.strip() or n
seen=set(); parks=[]
for b in rows:
    name=b["pLabel"]["value"]
    if name.startswith("Q") and name[1:].isdigit(): continue     # unlabeled items
    c=b["coord"]["value"]                                        # Point(lon lat)
    try: lon,lat=map(float, c[c.index("(")+1:c.index(")")].split())
    except Exception: continue
    k=(name, round(lon,1), round(lat,1))
    if k in seen: continue
    seen.add(k)
    parks.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lon,lat]},
                  "properties":{"name":strip_name(name),"fame":int(b.get("links",{}).get("value",0))}})
json.dump({"type":"FeatureCollection","features":parks}, open("../../explorer/data/parks.json","w"), separators=(',',':'))
print(f"parks: {len(parks)} (Wikidata, CC0)", flush=True)
# parks added by hand (state parks and the like, which this national-park query never returns)
exec(open('add_extra_parks.py').read())
