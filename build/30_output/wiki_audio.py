# %% [markdown]
# # PolygroveDB — Wikipedia's own recordings (2026-10-07)
#
# Every deck species' article is scanned in the local dump for embedded audio
# ([[File:…ogg]] links and {{Listen}} templates). Each file's licence, recordist
# and direct URL come from the Commons API; CC0, public domain, CC BY and CC
# BY-SA are kept (user, 2026-10-07: BY-SA is fine for playing a clip unchanged
# with credit — the field notes already run on Wikipedia text under it);
# anything NonCommercial or unlicensed is dropped. These clips are curated by
# editors, so they go FIRST, ahead of the GBIF pull's — output
# data/wiki_audio.json, folded into audio.json by score_audio.py's rebuild.

# %%
import json, re, time, os, requests
from concurrent.futures import ThreadPoolExecutor
import extract_lead_sentences as els
lead=json.load(open('../../data/wiki_lead.json'))
cards=json.load(open('../../explorer/data/catalog.json'))
AUD=re.compile(r'\[\[(?:File|Image):([^|\]]+\.(?:ogg|oga|mp3|wav|flac|opus))', re.I)
LIS=re.compile(r'\{\{\s*listen[^}]*?\|\s*filename\s*=\s*([^|}\n]+)', re.I)
def scan(c):
    d=lead.get(str(c['species_id'])); title=(d or {}).get('title') or c['sci']
    try: wt,_=els.get_wikitext(title)
    except Exception: return c, set()
    if not wt: return c, set()
    return c, {m.strip().replace('_',' ') for m in AUD.findall(wt)}|{m.strip().replace('_',' ') for m in LIS.findall(wt) if re.search(r'\.(ogg|oga|mp3|wav|flac|opus)$',m.strip(),re.I)}
t0=time.time(); found={}
with ThreadPoolExecutor(6) as ex:
    for i,(c,files) in enumerate(ex.map(scan, cards)):
        if files: found[c['sci']]=sorted(files)[:4]
        if (i+1)%2000==0: print(f"  scanned {i+1:,}/{len(cards):,} · {len(found):,} with audio · {(time.time()-t0)/60:.0f}m", flush=True)
print(f"scan done: {len(found):,} species carry audio files ({(time.time()-t0)/60:.0f}m)", flush=True)

# Commons: licence + recordist + URL, 50 titles a call
S=requests.Session(); S.headers.update({"User-Agent":"PolygroveDB/0.1 (open species database; polygrovedb.pages.dev)"})
OK=re.compile(r'^(cc0|public domain|pd|cc[- ]by(?:[- ]sa)?(?:[- ]\d(\.\d)?)?)', re.I)
titles=sorted({f for fs in found.values() for f in fs}); info={}
for i in range(0,len(titles),50):
    batch=titles[i:i+50]
    for attempt in range(3):
        try:
            r=S.get("https://commons.wikimedia.org/w/api.php", params={"action":"query","prop":"imageinfo","iiprop":"url|extmetadata","iiextmetadatafilter":"License|LicenseShortName|Artist|Credit","titles":"|".join("File:"+t for t in batch),"format":"json","redirects":1}, timeout=60)
            if r.status_code!=200: time.sleep(5); continue
            q=r.json().get('query',{})
            norm={n['to']:n['from'] for n in q.get('normalized',[])}; redir={n['to']:n['from'] for n in q.get('redirects',[])}
            for p in q.get('pages',{}).values():
                ii=(p.get('imageinfo') or [{}])[0]; em=ii.get('extmetadata',{})
                lic=(em.get('LicenseShortName',{}).get('value') or '').strip()
                artist=re.sub(r'<[^>]+>','',em.get('Artist',{}).get('value') or '').strip()
                t=p['title']; t=redir.get(t,t); t=norm.get(t,t)
                info[t.replace('File:','')]={'url':ii.get('url'),'lic':lic,'by':artist[:80]}
            break
        except Exception: time.sleep(5)
    time.sleep(0.5)
out={}; dropped={}
for sci,fs in found.items():
    keep=[]
    for f in fs:
        m=info.get(f)
        if not m or not m.get('url'): dropped['no info']=dropped.get('no info',0)+1; continue
        if not OK.match(m['lic']): dropped[m['lic'] or 'unlicensed']=dropped.get(m['lic'] or 'unlicensed',0)+1; continue
        keep.append({'url':m['url'],'by':m['by'],'lic':m['lic'],'ds':'Wikimedia Commons'})
    if keep: out[sci]=keep
json.dump(out, open('../../data/wiki_audio.json','w'), ensure_ascii=False)
print(f"DONE: {len(out):,} species with Commons recordings, {sum(len(v) for v in out.values()):,} clips; dropped: {dropped}  ({(time.time()-t0)/60:.0f}m)", flush=True)
