# Dump the World Spider Trait database (CC-BY 4.0) locally via its public API.
# Full dump (all traits, not just body length) so re-runs never need the network.
import json, time, urllib.request, os
BASE=("https://spidertraits.sci.muni.cz/backend/data/family/%2A/genus/%2A/species/%2A/"
      "original-name/%2A/trait-category/%2A/trait/%2A/method/%2A/location/%2A/country/%2A/"
      "dataset/%2A/authors/%2A/reference/%2A/row-link/%2A")
OUT="../../data/spidertraits/wst_records.jsonl"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
LIMIT=5000; off=0; n=0
with open(OUT,"w") as f:
    while True:
        url=f"{BASE}?offset={off}&limit={LIMIT}"
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=120) as r: d=json.load(r)
                break
            except Exception as e:
                print(f"retry {attempt+1} at offset {off}: {e}", flush=True); time.sleep(5*(attempt+1))
        else:
            raise SystemExit(f"FAILED at offset {off}")
        items=d.get("items",[])
        if not items: break
        for it in items: f.write(json.dumps(it)+"\n")
        n+=len(items); off+=LIMIT
        print(f"{n:,} records", flush=True)
        time.sleep(0.5)
print(f"DONE: {n:,} records -> {OUT}", flush=True)
