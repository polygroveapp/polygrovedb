# %% [markdown]
# # PolygroveDB — which recordings actually have something in them (2026-10-07)
#
# The audio pull keeps up to three licensed clips per species; some are dead air
# (user: "some audio doesn't really have anything … filter out the really bad
# ones with no signal; they're generally bad recordings so we don't want to be
# too strict"). Each clip's first 20 s is decoded (PyAV, streamed, no download
# kept) and measured in 100 ms windows:
#   peak   — loudest sample, dBFS
#   floor  — the 10th-percentile window RMS (the background)
#   snr    — 90th-percentile window RMS minus the floor: how far the loud
#            moments stand above the background
#   active — share of windows at least 6 dB above the floor
# A clip is DEAD when it fails to decode, runs under 1 s, peaks below -45 dBFS
# (silence), or its snr is under 3 dB with nothing active (flat hiss). Everything
# else stays — a faint field recording with a real call is still worth hearing.
# Clips are then ordered best-first (snr, then peak), so the card plays the
# strongest one. Output: data/audio_quality.json (per url), and audio.json
# rebuilt with dead clips dropped.

# %%
import json, os, time, numpy as np, av
from concurrent.futures import ThreadPoolExecutor
Q='../../data/audio_quality.json'
q=json.load(open(Q)) if os.path.exists(Q) else {}
res=json.load(open('../../data/species_audio.json'))
urls=sorted({c['url'] for v in res.values() for c in (v or [])} - set(q))
print(f"{len(urls):,} clips to measure ({len(q):,} already)", flush=True)

def measure(url):
    try:
        if not url.rsplit('.',1)[-1].split('?')[0].lower() in ('wav','m4a','mp3','mpga','ogg','flac','aac','mp4'): return url, {'dead': True, 'why': 'not audio'}
        c=av.open(url, timeout=(10,30)); st=c.streams.audio[0]
        rs=av.AudioResampler(format='fltp', layout='mono', rate=16000); buf=[]; n=0
        for fr in c.decode(st):
            for f in rs.resample(fr):
                a=f.to_ndarray()[0]; buf.append(a); n+=len(a)
            if n>=16000*20: break
        c.close()
        if not buf: return url, {'dead': True, 'why': 'no frames'}
        x=np.concatenate(buf).astype(np.float32); dur=len(x)/16000
        if dur<1: return url, {'dead': True, 'why': 'under 1 s', 'dur': round(dur,2)}
        peak=float(20*np.log10(np.abs(x).max()+1e-9))
        win=1600; w=x[:len(x)//win*win].reshape(-1,win)
        rms=20*np.log10(np.sqrt((w**2).mean(1))+1e-9)
        floor=float(np.percentile(rms,10)); loud=float(np.percentile(rms,90)); snr=loud-floor
        active=float((rms>floor+6).mean())
        dead = peak<-45 or (snr<3 and active<0.05)
        return url, {'dead': bool(dead), 'dur': round(dur,2), 'peak': round(peak,1), 'floor': round(floor,1), 'snr': round(snr,1), 'active': round(active,3)}
    except Exception as e:
        return url, {'dead': True, 'why': f'decode: {type(e).__name__}'}

t0=time.time(); done=0
with ThreadPoolExecutor(6) as ex:
    for url, m in ex.map(measure, urls):
        q[url]=m; done+=1
        if done%100==0:
            json.dump(q, open(Q,'w'))
            print(f"  {done:,}/{len(urls):,} · dead so far {sum(1 for v in q.values() if v.get('dead')):,} · {(time.time()-t0)/60:.0f}m", flush=True)
json.dump(q, open(Q,'w'))

# rebuild audio.json: dead clips out, best first, species with nothing left dropped
cards=json.load(open('../../explorer/data/catalog.json'))
au={}
for c in cards:
    clips=[k for k in (res.get(str(c['species_id'])) or []) if not q.get(k['url'],{}).get('dead')]
    clips.sort(key=lambda k: (-(q.get(k['url'],{}).get('snr') or 0), -(q.get(k['url'],{}).get('peak') or -99)))
    if clips: au[c['sci']]=clips
json.dump(au, open('../../explorer/data/audio.json','w'), ensure_ascii=False, separators=(',',':'))
dead=sum(1 for v in q.values() if v.get('dead'))
print(f"DONE: {len(q):,} clips measured, {dead:,} dead; audio.json: {len(au):,} species  ({(time.time()-t0)/60:.0f}m)", flush=True)
