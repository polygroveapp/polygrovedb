# %% [markdown]
# # PolygroveDB — parks added by hand (user, 2026-11-18)
#
# parks.json is built from Wikidata's NATIONAL parks (fetch_map_labels.py), so a state
# park is not in it however well known it is locally: "why isn't Henry Cowell in the
# database" — Henry Cowell Redwoods is a California state park. The user: "we just need
# to add it manually if nothing else".
#
# extra_parks.json is that manual list. Each entry: name (written the way the map labels
# parks, without "State Park"), lng, lat, fame (Wikidata sitelinks, the label priority),
# r (the half-width in degrees of the box its sightings and species are counted in — a
# state park is far smaller than the 0.15° used for a national park that has no boundary
# file), kind, and source.
#
# This appends any entry not already in parks.json. Entries go at the END, so the park
# numbers that park_species.json is keyed by do not move. Run export_park_obs.py and
# export_park_species.py afterwards: they fill in obs, eco, state and the species list.
# fetch_map_labels.py runs this itself after rebuilding the national list.

# %%
import json
P='../../explorer/data/parks.json'
parks=json.load(open(P)); extra=json.load(open('extra_parks.json'))
have={(f['properties']['name'], round(f['geometry']['coordinates'][0],2), round(f['geometry']['coordinates'][1],2)) for f in parks['features']}
added=0
for e in extra:
    k=(e['name'], round(e['lng'],2), round(e['lat'],2))
    if k in have: continue
    props={"name":e['name'],"fame":int(e.get('fame',1))}
    for opt in ('r','kind'):
        if e.get(opt) is not None: props[opt]=e[opt]
    parks['features'].append({"type":"Feature","geometry":{"type":"Point","coordinates":[e['lng'],e['lat']]},"properties":props})
    have.add(k); added+=1
json.dump(parks, open(P,'w'), separators=(',',':'))
print(f"extra parks: {added} added, {len(extra)-added} already there; {len(parks['features'])} parks in all", flush=True)
