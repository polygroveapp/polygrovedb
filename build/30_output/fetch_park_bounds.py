# %% [markdown]
# # PolygroveDB — park boundary polygons (open-licensed only)
# Two sources, both redistribution-safe:
#   - US National Park Service unit boundaries (PUBLIC DOMAIN, ArcGIS open data)
#   - Wikidata P3896 geoshapes on Commons (Data: namespace = CC0) — ~70 worldwide
# WDPA is license-restricted (no redistribution) and OSM is ODbL (stance decision
# pending) — everywhere else the dashed ring stands in.
# Output: explorer/data/park_bounds.geojson (simplified for the web).

# %%
import json, time, requests, duckdb
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (open park boundaries)"})
feats=[]

# --- NPS (public domain) ---
NPS="https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/NPS_Land_Resources_Division_Boundary_and_Tract_Data_Service/FeatureServer/2/query"
offset=0
while True:
    r=S.get(NPS, params={"where":"1=1","outFields":"UNIT_NAME,UNIT_TYPE","f":"geojson",
        "resultOffset":offset,"resultRecordCount":100,"geometryPrecision":4}, timeout=120)
    j=r.json(); fs=j.get("features",[])
    if not fs: break
    for f in fs:
        f["properties"]={"name":f["properties"].get("UNIT_NAME",""),"src":"NPS"}
        feats.append(f)
    offset+=len(fs)
    print(f"  NPS: {offset}", flush=True)
    if not j.get("properties",{}).get("exceededTransferLimit") and len(fs)<100: break
    time.sleep(0.3)
print(f"NPS boundaries: {len(feats)}", flush=True)

# --- Wikidata/Commons geoshapes (CC0) ---
q="""SELECT ?pLabel ?shape WHERE { ?p wdt:P31/wdt:P279* wd:Q46169 . ?p wdt:P3896 ?shape .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
rows=S.get("https://query.wikidata.org/sparql", params={"query":q,"format":"json"}, timeout=180).json()["results"]["bindings"]
got=0
for b in rows:
    name=b["pLabel"]["value"]; shape=b["shape"]["value"].split("/data/main/")[-1]
    try:
        r=S.get("https://commons.wikimedia.org/w/index.php", params={"title":shape,"action":"raw"}, timeout=60)
        d=r.json().get("data")
        if d and d.get("type") in ("Feature","FeatureCollection","Polygon","MultiPolygon"):
            if d.get("type")=="FeatureCollection":
                for f in d["features"]:
                    f["properties"]={"name":name,"src":"Commons CC0"}; feats.append(f)
            elif d.get("type")=="Feature":
                d["properties"]={"name":name,"src":"Commons CC0"}; feats.append(d)
            else:
                feats.append({"type":"Feature","geometry":d,"properties":{"name":name,"src":"Commons CC0"}})
            got+=1
    except Exception: pass
    time.sleep(0.4)
print(f"Commons geoshapes: {got}", flush=True)

fc={"type":"FeatureCollection","features":feats}
json.dump(fc, open("/tmp_bounds_raw.json","w")) if False else None
# simplify via DuckDB spatial to keep the payload sane
open("../../data/park_bounds_raw.geojson","w").write(json.dumps(fc))
con=duckdb.connect(); con.sql("INSTALL spatial; LOAD spatial;")
con.sql("""COPY (
  SELECT name, src, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.002)) AS gj
  FROM ST_Read('../../data/park_bounds_raw.geojson')
  WHERE geom IS NOT NULL) TO '/dev/stdout' (FORMAT csv)""") if False else None
rows2=con.sql("""SELECT name, src, ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_MakeValid(geom), 0.002)) 
  FROM ST_Read('../../data/park_bounds_raw.geojson') WHERE geom IS NOT NULL""").fetchall()
def _unwrap(g):
    # ST_MakeValid can emit GeometryCollections, which MapLibre line layers won't draw
    if g.get("type")=="GeometryCollection":
        polys=[]
        for sub in g["geometries"]:
            if sub["type"]=="Polygon": polys.append(sub["coordinates"])
            elif sub["type"]=="MultiPolygon": polys.extend(sub["coordinates"])
        return {"type":"MultiPolygon","coordinates":polys}
    return g
out={"type":"FeatureCollection","features":[
    {"type":"Feature","geometry":_unwrap(json.loads(g)),"properties":{"name":n,"src":s2}} for n,s2,g in rows2]}
json.dump(out, open("../../explorer/data/park_bounds.geojson","w"), separators=(',',':'))
import os
print(f"DONE: {len(out['features'])} boundary features, {os.path.getsize('../../explorer/data/park_bounds.geojson')/1e6:.1f} MB", flush=True)
