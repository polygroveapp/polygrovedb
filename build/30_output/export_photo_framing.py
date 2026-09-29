# %% [markdown]
# # PolygroveDB — framing.json: how each card photo sits in the card's hexagon
#
# The cards centre-cropped Wikipedia's lead photo into a tall hexagon, which cut
# the subject on four cards in five (a whooping crane lost its head and feet —
# user, 2026-09-29; measured by focal_sample.py). This finds the subject of
# EVERY card photo (focal.swift, Apple Vision, on this Mac) and works out the
# framing that keeps it in: slide the photo first, zoom out up to 20% if that
# is not enough (the app and the explorer fill the gap with a blurred copy of
# the same photo), and when even that fails keep the best slide.
#
# Output: explorer/data/framing.json  {card id: [aspect, scale, cx, cy]}
#   aspect  the photo's width / height
#   scale   relative to cover (1 = fills the hexagon)
#   cx, cy  where the photo's CENTRE sits, relative to the hexagon's centre, as
#           a fraction of the hexagon's width / height (0,0 = the old centre crop)
# Only cards whose framing differs from the centre crop are listed.
# Photos are cached in data/card_photos/ (330px), subject grids in
# data/photo_boxes.jsonl — both resumable, neither in git.

# %%
import io, json, os, re, subprocess, sys, time, collections
from concurrent.futures import ThreadPoolExecutor
import requests
from PIL import Image
from framing_geom import HW, HH, classify

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
IMG = os.path.join(ROOT, "data", "card_photos"); os.makedirs(IMG, exist_ok=True)
BOXES = os.path.join(ROOT, "data", "photo_boxes.jsonl")
OUT = os.path.join(ROOT, "explorer", "data", "framing.json")
REPORT = os.path.join(ROOT, "build", "cache", "photo_framing_report.json")
photos = {k: v for k, v in json.load(open(os.path.join(ROOT, "explorer", "data", "photos.json"))).items() if v}
cards = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "explorer", "data", "catalog.json")))}
ids = sorted(k for k in photos if k in cards)
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None
if LIMIT: ids = ids[:LIMIT]
print(f"{len(ids)} card photos", flush=True)

# %% the photos — the app's 330px bucket is plenty for finding a subject
UA = {"User-Agent": "PolygroveDB/1.0 (https://polygrovedb.pages.dev; card photo framing) python-requests"}
path = lambda cid: os.path.join(IMG, cid + ".jpg")
def fetch(cid):
    p = path(cid)
    if os.path.exists(p) and os.path.getsize(p) > 1500: return True
    url = re.sub(r"/\d+px-", "/330px-", photos[cid]).split("?")[0]
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200 and len(r.content) > 1500:
                Image.open(io.BytesIO(r.content)).convert("RGB").save(p, "JPEG", quality=88); return True
            if r.status_code in (429, 503): time.sleep(4 * (attempt + 1))
            elif r.status_code == 404: return False
        except Exception: time.sleep(2)
    return False
t0 = time.time(); todo = [c for c in ids if not (os.path.exists(path(c)) and os.path.getsize(path(c)) > 1500)]
print(f"{len(todo)} to download", flush=True)
with ThreadPoolExecutor(3) as ex:          # three at a time: polite to Wikimedia's thumbnail servers
    for i, ok in enumerate(ex.map(fetch, todo)):
        if (i + 1) % 500 == 0: print(f"  downloaded {i+1}/{len(todo)}  ({(time.time()-t0)/60:.1f}m)", flush=True)
have = [c for c in ids if os.path.exists(path(c)) and os.path.getsize(path(c)) > 1500]
print(f"{len(have)} photos on disk ({(time.time()-t0)/60:.1f}m)", flush=True)

# %% where the subject is — four Vision processes side by side, resumable
boxes = {}
if os.path.exists(BOXES):
    for l in open(BOXES):
        try: b = json.loads(l); boxes[b["file"][:-4]] = b
        except Exception: pass
todo = [c for c in have if c not in boxes]
print(f"{len(todo)} to analyse", flush=True)
if todo:
    t0 = time.time(); env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer")
    # compile once: the interpreter would re-parse the script in every process
    exe = os.path.join(ROOT, "data", "focal")
    c = subprocess.run(["xcrun", "swiftc", "-O", os.path.join(HERE, "focal.swift"), "-o", exe], capture_output=True, text=True, env=env)
    if c.returncode != 0: sys.exit("focal.swift did not compile:\n" + c.stderr[-2000:])
    procs = []
    for k in range(4):
        part = todo[k::4]
        if not part: continue
        lst = os.path.join(ROOT, "data", f"focal_list_{k}.txt")
        open(lst, "w").write("\n".join(path(c) for c in part))
        procs.append(subprocess.Popen([exe, lst], stdout=subprocess.PIPE, text=True))
    with open(BOXES, "a") as out:
        for p in procs:
            for l in p.stdout:
                try: b = json.loads(l)
                except Exception: continue
                boxes[b["file"][:-4]] = b; out.write(l); out.flush()
            p.wait()
    print(f"{len(boxes)} photos analysed ({(time.time()-t0)/60:.1f}m)", flush=True)

# %% the framing
framing, report = {}, []
for cid in have:
    b = boxes.get(cid)
    if not b: continue
    r = classify(b["w"], b["h"], b["grid"])
    if not r: continue
    w, h = b["w"], b["h"]; cover = max(HW / w, HH / h)
    dw, dh = w * cover * r["scale"], h * cover * r["scale"]
    cx, cy = (r["ox"] + dw / 2) / HW, (r["oy"] + dh / 2) / HH
    report.append({"id": cid, "group": cards[cid]["group"], "kind": r["kind"], "today": r["today"], "kept": r["kept"], "how": b["how"], "fills": r["fills"]})
    if r["kind"] != "ok" and (r["scale"] < 0.999 or abs(cx) > 0.004 or abs(cy) > 0.004):
        framing[cid] = [round(w / h, 3), round(r["scale"], 2), round(cx, 3), round(cy, 3)]
json.dump(framing, open(OUT, "w"), separators=(",", ":"))

n = len(report); c = collections.Counter(r["kind"] for r in report)
worst = sorted((r for r in report if r["kind"] == "far"), key=lambda r: r["kept"])
json.dump({"cards": n, "kinds": dict(c), "detector": dict(collections.Counter(r["how"] for r in report)),
           "by_group": {g: dict(collections.Counter(r["kind"] for r in report if r["group"] == g)) for g in sorted({r["group"] for r in report})},
           "swap_candidates": [{"id": r["id"], "kept": r["kept"], "fills": r["fills"]} for r in worst[:400]]},
          open(REPORT, "w"), indent=1)
print(f"\n{n} cards")
for k, label in [("ok", "already in frame"), ("slide", "fixed by sliding the photo"), ("zoom", "fixed by zooming out up to 20%"), ("far", "still cut: best slide kept")]:
    print(f"  {label:36} {c[k]:5}  {100*c[k]/max(1,n):5.1f}%")
print(f"framing.json: {len(framing)} cards re-framed, {os.path.getsize(OUT)//1024} KB")
