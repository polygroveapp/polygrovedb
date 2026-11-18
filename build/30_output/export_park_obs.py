# %% [markdown]
# # PolygroveDB — observation counts for parks + ecoregions (user, 2026-09-22)
#
# "The same observation way count": parks sum the SAME 0.01°-cell deck
# observation points the golden map dots draw (deck_obs_points.parquet) —
# inside the park's real boundary bbox (470 NPS polygons) or a 0.15° radius
# around its point. Ecoregions sum occurrence_ecoregions_full (every record).
# Output: parks.json features gain properties.obs + properties.eco (containing
# ecoregion via point-in-polygon); eco_meta.json entries gain "obs".

# %%
import duckdb, json, time
from collections import defaultdict
t0=time.time()

# ---- cell sums (deck observation cells, same as the map dots) --------------
con=duckdb.connect()
cells={}
for cx,cy,n in con.sql("""SELECT cx, cy, sum(n) FROM read_parquet('../../data/deck_obs_points.parquet')
                          GROUP BY 1,2""").fetchall():
    cells[(cx,cy)]=int(n)
print(f"{len(cells):,} obs cells  ({time.time()-t0:.0f}s)", flush=True)

# ---- ecoregion totals (every occurrence record) ----------------------------
eco_obs={int(e):int(n) for e,n in con.sql("""SELECT ecoregion_id, sum(occurrence_count)
  FROM read_parquet('../../data/occurrence_ecoregions_full.parquet') GROUP BY 1""").fetchall()}
print(f"eco totals for {len(eco_obs):,} ecoregions  ({time.time()-t0:.0f}s)", flush=True)

# ---- park -> ecoregion (point in polygon over the explorer geojson) --------
eco=json.load(open('../../explorer/data/ecoregions.geojson'))
def in_ring(x,y,ring):
    inside=False; j=len(ring)-1
    for i in range(len(ring)):
        xi,yi=ring[i][0],ring[i][1]; xj,yj=ring[j][0],ring[j][1]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi: inside=not inside
        j=i
    return inside
efeats=[]
for f in eco['features']:
    g=f.get('geometry'); eid=f['properties'].get('eco')
    if not g or eid is None: continue
    polys=[g['coordinates']] if g['type']=='Polygon' else (g['coordinates'] if g['type']=='MultiPolygon' else [])
    for p in polys:
        xs=[c[0] for c in p[0]]; ys=[c[1] for c in p[0]]
        efeats.append((min(xs),min(ys),max(xs),max(ys),p[0],eid))
def eco_at(x,y):
    for w,s,e,n,ring,eid in efeats:
        if w<=x<=e and s<=y<=n and in_ring(x,y,ring): return eid
    return None

# ---- park bboxes (real boundaries where they exist) ------------------------
bounds=json.load(open('../../explorer/data/park_bounds.geojson'))
def norm(s): return (s or '').lower().replace('national park','').replace('national','').replace('park','').strip()
bmap=defaultdict(list)
for f in bounds['features']:
    g=f.get('geometry')
    if not g: continue
    coords=[]
    def walk(c):
        if isinstance(c[0],(int,float)): coords.append(c)
        else:
            for k in c: walk(k)
    walk(g['coordinates'])
    xs=[c[0] for c in coords]; ys=[c[1] for c in coords]
    bmap[norm(f['properties'].get('name'))].append((min(xs),min(ys),max(xs),max(ys)))

def cellsum(w,s,e,n):
    tot=0
    for cx in range(int(w*100)-1,int(e*100)+2):
        for cy in range(int(s*100)-1,int(n*100)+2):
            v=cells.get((cx,cy))
            if v: tot+=v
    return tot

parks=json.load(open('../../explorer/data/parks.json'))
R=0.15
done=0
for f in parks['features']:
    x,y=f['geometry']['coordinates']; nm=f['properties'].get('name','')
    boxes=bmap.get(norm(nm))
    box=None
    if boxes:  # pick the candidate box that actually contains the marker
        for b in boxes:
            if b[0]-0.2<=x<=b[2]+0.2 and b[1]-0.2<=y<=b[3]+0.2: box=b; break
    if box and (box[2]-box[0])*(box[3]-box[1])<64:   # sanity: huge multi-unit sprawl falls back to the radius
        f['properties']['obs']=cellsum(*box)
    else:
        r=f['properties'].get('r') or R   # a park added by hand names its own, smaller box (extra_parks.json)
        f['properties']['obs']=cellsum(x-r,y-r,x+r,y+r)
    f['properties']['eco']=eco_at(x,y)
    done+=1
    if done%500==0: print(f"  {done}/{len(parks['features'])}  ({time.time()-t0:.0f}s)", flush=True)
json.dump(parks, open('../../explorer/data/parks.json','w'), separators=(',',':'))

meta=json.load(open('../../explorer/data/eco_meta.json'))
for k in meta:
    try: meta[k]['obs']=eco_obs.get(int(k),0)
    except Exception: pass
json.dump(meta, open('../../explorer/data/eco_meta.json','w'), separators=(',',':'))
top=sorted(parks['features'],key=lambda f:-f['properties']['obs'])[:5]
print('top parks by obs:',[(f['properties']['name'],f['properties']['obs']) for f in top])
print(f"DONE ({time.time()-t0:.0f}s)")
