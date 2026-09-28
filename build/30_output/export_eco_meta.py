# %% [markdown]
# # PolygroveDB — merged ecoregion metadata for the explorer
# name + Wikipedia lead sentence (dump-extracted) + habitat photo (Wikipedia lead image,
# CC/PD-licensed with credit). Rerun whenever fetch_ecoregion_photos or
# extract_ecoregion_leads refresh their caches.

# %%
import duckdb, json, os
con=duckdb.connect(); con.sql("INSTALL spatial; LOAD spatial;")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
names=dict(con.sql("SELECT ECO_ID, ECO_NAME FROM pg.ecoregions WHERE ECO_NAME IS NOT NULL").fetchall())
# authoritative bboxes from the FULL geometry — the explorer's simplified geojson
# nulls some polygons (New England-Acadian!), silently breaking fly-to
bboxes={r[0]:[round(r[1],2),round(r[2],2),round(r[3],2),round(r[4],2)] for r in con.sql(
  """SELECT ECO_ID, ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom)
     FROM pg.ecoregions WHERE geom IS NOT NULL""").fetchall()}
con.close()
leads=json.load(open('../../data/ecoregion_leads.json')) if os.path.exists('../../data/ecoregion_leads.json') else {}
photos=json.load(open('../../data/ecoregion_photos.json')) if os.path.exists('../../data/ecoregion_photos.json') else {}
out={}
for eid,name in names.items():
    k=str(eid); e={"name":name}
    if eid in bboxes: e["bbox"]=bboxes[eid]
    if k in leads: e["lead"]=leads[k]["lead"]; e["wiki"]=leads[k]["title"]   # article title → the phone links to Wikipedia (2026-09-28)
    p=photos.get(k)
    if p: e["photo"]={"thumb":p.get("thumb") or p.get("url"),"by":p.get("by",""),"lic":p.get("license","")}
    out[k]=e
json.dump(out, open('../../explorer/data/eco_meta.json','w'), separators=(',',':'))
n_l=sum(1 for e in out.values() if 'lead' in e); n_p=sum(1 for e in out.values() if 'photo' in e)
print(f"eco_meta.json: {len(out)} ecoregions · {n_l} with lead · {n_p} with photo")
