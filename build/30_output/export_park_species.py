# %% [markdown]
# # PolygroveDB — park states + per-park deck species (user, 2026-09-22)
#
# 1) parks.json gains properties.state — the Natural Earth admin-1 unit (US
#    state / province) the park point falls in, else its admin-0 country.
# 2) explorer/data/park_species.json — {parkIdx: [[sci_lower, n], ...]}: the
#    deck species with observation cells (deck_obs_points, the SAME cells the
#    gold dots draw) inside each park's boundary bbox / point radius. Feeds
#    the Parks tab's park-scoped food web.

# %%
import duckdb, json, time, requests, os
from collections import defaultdict
t0=time.time()

NE='https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/'
def get_cached(fn,url):
    p=f'../../data/{fn}'
    if not os.path.exists(p):
        open(p,'w').write(requests.get(url,timeout=180).text)
    return json.load(open(p))
adm1=get_cached('ne_50m_admin_1.geojson',NE+'ne_50m_admin_1_states_provinces.geojson')
adm0=get_cached('ne_110m_admin_0.geojson',NE+'ne_110m_admin_0_countries.geojson')

def rings_of(g):
    if not g: return []
    return [g['coordinates']] if g['type']=='Polygon' else (g['coordinates'] if g['type']=='MultiPolygon' else [])
def in_ring(x,y,ring):
    inside=False; j=len(ring)-1
    for i in range(len(ring)):
        xi,yi=ring[i][0],ring[i][1]; xj,yj=ring[j][0],ring[j][1]
        if (yi>y)!=(yj>y) and x<(xj-xi)*(y-yi)/(yj-yi)+xi: inside=not inside
        j=i
    return inside
def index(fc,namef):
    out=[]
    for f in fc['features']:
        nm=f['properties'].get(namef) or f['properties'].get('name')
        for p in rings_of(f.get('geometry')):
            xs=[c[0] for c in p[0]]; ys=[c[1] for c in p[0]]
            out.append((min(xs),min(ys),max(xs),max(ys),p[0],nm))
    return out
I1=index(adm1,'name'); I0=index(adm0,'NAME' if any('NAME' in f['properties'] for f in adm0['features'][:1]) else 'name')
def lookup(idx,x,y):
    for w,s,e,n,ring,nm in idx:
        if w<=x<=e and s<=y<=n and in_ring(x,y,ring): return nm
    return None

# ---- park boxes (same rules as export_park_obs) ----------------------------
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
parks=json.load(open('../../explorer/data/parks.json'))
R=0.15
cell2park=defaultdict(list)
for i,f in enumerate(parks['features']):
    x,y=f['geometry']['coordinates']
    f['properties']['state']=lookup(I1,x,y) or lookup(I0,x,y) or ''
    boxes=bmap.get(norm(f['properties'].get('name','')))
    box=None
    if boxes:
        for b in boxes:
            if b[0]-0.2<=x<=b[2]+0.2 and b[1]-0.2<=y<=b[3]+0.2: box=b; break
    r=f['properties'].get('r') or R   # a park added by hand names its own, smaller box (extra_parks.json)
    if not(box and (box[2]-box[0])*(box[3]-box[1])<64): box=(x-r,y-r,x+r,y+r)
    for cx in range(int(box[0]*100)-1,int(box[2]*100)+2):
        for cy in range(int(box[1]*100)-1,int(box[3]*100)+2):
            cell2park[(cx,cy)].append(i)
print(f"{len(parks['features'])} parks · {len(cell2park):,} park cells · states done  ({time.time()-t0:.0f}s)", flush=True)

# ---- one pass over the deck observation cells ------------------------------
con=duckdb.connect()
acc=defaultdict(lambda: defaultdict(int))
for k,cx,cy,n in con.sql("""SELECT k,cx,cy,sum(n) FROM read_parquet('../../data/deck_obs_points.parquet')
                            GROUP BY 1,2,3""").fetchall():
    ps=cell2park.get((cx,cy))
    if ps:
        for p in ps: acc[p][k]+=int(n)
out={str(p):sorted(d.items(),key=lambda kv:-kv[1])[:400] for p,d in acc.items()}
json.dump(out, open('../../explorer/data/park_species.json','w'), separators=(',',':'))
json.dump(parks, open('../../explorer/data/parks.json','w'), separators=(',',':'))
sz=os.path.getsize('../../explorer/data/park_species.json')//1024
y=[f for f in parks['features'] if f['properties']['name']=='Yellowstone'][0]
print(f"park_species.json: {len(out)} parks with species, {sz} KB; Yellowstone state={y['properties']['state']}, spp={len(out.get(str(parks['features'].index(y)),[]))}")
print(f"DONE ({time.time()-t0:.0f}s)")
