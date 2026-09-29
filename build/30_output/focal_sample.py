# %% [markdown]
# # PolygroveDB — is the subject of each card photo IN FRAME? (sample run, 2026-09-29)
#
# The cards centre-crop Wikipedia's lead photo into a hexagon that is taller
# than wide and loses all four corners — a whooping crane lost its head and
# feet (user, 2026-09-29). This measures the problem on a sample before any
# fix ships: for N cards, find the subject (focal.swift, Apple Vision), then
# classify how the photo could be framed in the card's hexagon:
#   ok      the centre crop already holds the subject (≥97% of its own pixels)
#   slide   sliding the photo (still filling the hexagon) brings it in
#   zoom    it needs to shrink ≤ 20% — the gap is filled with a blurred copy
#   far     still cut after that — keep the best slide, or swap the photo
# Judged by the subject's OUTLINE, not its bounding box (a box's corners are
# empty air; the first version of this flagged 90% of the deck).
# Outputs (build/cache/focal_sample/): boxes.jsonl, report.json, sheet.png
# (today vs proposed, side by side). Nothing here feeds the catalog yet.

# %%
import json, os, random, subprocess, sys, time, collections
import requests
from PIL import Image, ImageDraw, ImageFilter

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "build", "cache", "focal_sample"); IMG = os.path.join(OUT, "img")
os.makedirs(IMG, exist_ok=True)
photos = json.load(open(os.path.join(ROOT, "explorer", "data", "photos.json")))
cards = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "explorer", "data", "catalog.json")))}

# the same cards every run, spread across the groups the deck actually has
random.seed(20260929)
by_group = collections.defaultdict(list)
for cid, url in photos.items():
    if url and cid in cards: by_group[cards[cid]["group"]].append(cid)
total = sum(len(v) for v in by_group.values())
sample = []
for g, ids in sorted(by_group.items()):
    sample += random.sample(sorted(ids), max(2, round(N * len(ids) / total)) if len(ids) >= 2 else len(ids))
sample = sample[:N] if len(sample) > N else sample
print(f"{len(sample)} cards sampled from {total} with photos, {len(by_group)} groups")

# %% the photos, at the size the card shows them (500px bucket), politely
UA = {"User-Agent": "PolygroveDB/1.0 (https://polygrovedb.pages.dev; focal-point sample) python-requests"}
for i, cid in enumerate(sample):
    p = os.path.join(IMG, cid + ".jpg")
    if os.path.exists(p) and os.path.getsize(p) > 2000: continue
    url = __import__("re").sub(r"/\d+px-", "/500px-", photos[cid]).split("?")[0]
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200 and len(r.content) > 2000:
                Image.open(__import__("io").BytesIO(r.content)).convert("RGB").save(p, "JPEG", quality=90); break
            if r.status_code == 429: time.sleep(5 * (attempt + 1))
        except Exception: time.sleep(2)
    time.sleep(0.15)
have = [c for c in sample if os.path.exists(os.path.join(IMG, c + ".jpg"))]
print(f"{len(have)} photos on disk")

# %% where the subject is
boxes_path = os.path.join(OUT, "boxes.jsonl")
env = dict(os.environ, DEVELOPER_DIR="/Applications/Xcode.app/Contents/Developer")
t0 = time.time()
res = subprocess.run(["xcrun", "swift", os.path.join(os.path.dirname(os.path.abspath(__file__)), "focal.swift"), IMG],
                     capture_output=True, text=True, env=env)
if res.returncode != 0: sys.exit("focal.swift failed:\n" + res.stderr[-2000:])
open(boxes_path, "w").write(res.stdout)
boxes = {json.loads(l)["file"][:-4]: json.loads(l) for l in res.stdout.splitlines() if l.strip()}
print(f"{len(boxes)} photos analysed ({time.time()-t0:.0f}s)")

# %% the card's hexagon: pointy-top, 188 x 214 inside its border (HexPhoto 200x226, border 6)
import numpy as np
HW, HH = 188.0, 214.0
KEEP = 0.97           # "in frame" = at least this much of the SUBJECT ITSELF is inside the hexagon
INSET = 0.96          # …measured against a hexagon 4% smaller, so nothing sits on the border
MAX_SHRINK = 0.20     # beyond this the photo gets too small to be worth it
G = 48

def kept(pts, w, h, rel, ox, oy):
    """share of the subject's points that land inside the (inset) hexagon"""
    cover = max(HW / w, HH / h); s = cover * rel
    x = np.abs(ox + pts[:, 0] * w * s); y = np.abs(oy + pts[:, 1] * h * s)
    hw, hh = HW * INSET, HH * INSET
    return float(np.mean((x <= hw / 2) & (y <= hh / 2 - x * hh / (2 * hw))))

def offsets(w, h, rel):
    """every way the photo can sit: it keeps covering the hexagon where it is
    big enough to, and is centred in a dimension where it is not"""
    cover = max(HW / w, HH / h); dw, dh = w * cover * rel, h * cover * rel
    xs = [-(dw / 2)] if dw <= HW else list(np.linspace(-(dw - HW / 2), -HW / 2, 21))
    ys = [-(dh / 2)] if dh <= HH else list(np.linspace(-(dh - HH / 2), -HH / 2, 21))
    return [(ox, oy) for ox in xs for oy in ys], dw, dh

def best_at(pts, w, h, rel):
    offs, dw, dh = offsets(w, h, rel)
    # most of the subject kept; among equals, the one nearest today's centre crop
    return max(((kept(pts, w, h, rel, ox, oy), -(abs(ox + dw / 2) + abs(oy + dh / 2)), ox, oy) for ox, oy in offs))

report = []
for cid in have:
    b = boxes.get(cid)
    if not b: continue
    w, h = b["w"], b["h"]
    g = np.array([c == "1" for c in b["grid"]]).reshape(G, G)
    ys, xs = np.nonzero(g)
    if len(xs) == 0: continue
    pts = np.stack([(xs + 0.5) / G, (ys + 0.5) / G], axis=1)
    cover = max(HW / w, HH / h)
    today = kept(pts, w, h, 1.0, -w * cover / 2, -h * cover / 2)
    k1, _, ox1, oy1 = best_at(pts, w, h, 1.0)
    if today >= KEEP: kind, rel, ox, oy, k = "ok", 1.0, -w * cover / 2, -h * cover / 2, today
    elif k1 >= KEEP: kind, rel, ox, oy, k = "slide", 1.0, ox1, oy1, k1
    else:
        kind = "far"; rel, ox, oy, k = 1.0, ox1, oy1, k1          # if nothing works: the best slide
        for step in range(1, int(MAX_SHRINK * 100) + 1):
            r = 1.0 - step / 100
            kk, _, oxx, oyy = best_at(pts, w, h, r)
            if kk >= KEEP: kind, rel, ox, oy, k = "zoom", r, oxx, oyy, kk; break
    report.append({"id": cid, "group": cards[cid]["group"], "w": w, "h": h, "box": b["box"], "how": b["how"], "kind": kind,
                   "today": round(today, 3), "kept": round(k, 3), "scale": rel, "ox": ox, "oy": oy,
                   "fills": round(float(np.mean(g)), 3)})
json.dump(report, open(os.path.join(OUT, "report.json"), "w"), indent=1)

n = len(report); c = collections.Counter(r["kind"] for r in report)
print(f"\n{n} cards · in frame = {int(KEEP*100)}% of the subject inside the hexagon")
for k, label in [("ok", "already in frame"), ("slide", "fixed by sliding the photo"), ("zoom", "fixed by zooming out ≤20% (blurred fill)"), ("far", "still cut after that")]:
    print(f"  {label:44} {c[k]:4}  {100*c[k]/n:5.1f}%")
cut = sorted(1 - r["today"] for r in report)
print(f"  today, share of the subject cut off: median {100*cut[len(cut)//2]:.0f}% · worst tenth ≥ {100*cut[int(len(cut)*0.9)]:.0f}%")
far = [r for r in report if r["kind"] == "far"]
if far: print(f"  the 'still cut' cards: best slide keeps a median {100*sorted(r['kept'] for r in far)[len(far)//2]:.0f}% of the subject; the subject fills a median {100*sorted(r['fills'] for r in far)[len(far)//2]:.0f}% of its photo")
print("  detector:", dict(collections.Counter(r["how"] for r in report)))
print("  by group (ok/slide/zoom/far):")
for gname in sorted({r["group"] for r in report}):
    gc = collections.Counter(r["kind"] for r in report if r["group"] == gname)
    print(f"    {gname:18} {gc['ok']:3} {gc['slide']:3} {gc['zoom']:3} {gc['far']:3}")

# %% the picture: today vs proposed, for the cards that change
S = 2                                                   # render at 2x
def hex_mask(wd, ht):
    m = Image.new("L", (wd, ht), 0)
    ImageDraw.Draw(m).polygon([(wd/2, 0), (wd, ht/4), (wd, 3*ht/4), (wd/2, ht), (0, 3*ht/4), (0, ht/4)], fill=255)
    return m
def render(im, rel, ox, oy, box=None):
    wd, ht = int(HW * S), int(HH * S); cover = max(HW / im.width, HH / im.height)
    canvas = Image.new("RGB", (wd, ht), (17, 17, 17))
    if rel < 0.999:                                     # the blurred, darkened backdrop
        bg = im.resize((max(1, int(im.width * cover * 1.25 * S)), max(1, int(im.height * cover * 1.25 * S))))
        bg = bg.filter(ImageFilter.GaussianBlur(18 * S)).point(lambda v: int(v * 0.7))
        canvas.paste(bg, ((wd - bg.width) // 2, (ht - bg.height) // 2))
    s = cover * rel * S
    fg = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    if rel < 0.999:                                     # the photo's edges melt into the backdrop
        f = 14 * S; a = Image.new("L", fg.size, 0)
        ImageDraw.Draw(a).rectangle([f, f, fg.width - f, fg.height - f], fill=255)
        canvas.paste(fg, (int(wd / 2 + ox * S), int(ht / 2 + oy * S)), a.filter(ImageFilter.GaussianBlur(f / 2)))
    else: canvas.paste(fg, (int(wd / 2 + ox * S), int(ht / 2 + oy * S)))
    if box:                                             # the detected subject, outlined
        x0 = wd / 2 + ox * S + box[0] * fg.width; y0 = ht / 2 + oy * S + box[1] * fg.height
        ImageDraw.Draw(canvas).rectangle([x0, y0, x0 + box[2] * fg.width, y0 + box[3] * fg.height], outline=(255, 225, 77), width=2)
    out = Image.new("RGB", (wd, ht), (26, 26, 26)); out.paste(canvas, (0, 0), hex_mask(wd, ht))
    return out
pick = [r for r in report if r["kind"] == "slide"][:8] + [r for r in report if r["kind"] == "zoom"][:10] + [r for r in report if r["kind"] == "far"][:6]
cols, cw, ch = 4, int(HW * S) * 2 + 30, int(HH * S) + 46
sheet = Image.new("RGB", (cols * cw + 20, ((len(pick) + cols - 1) // cols) * ch + 20), (13, 13, 13))
d = ImageDraw.Draw(sheet)
for i, r in enumerate(pick):
    im = Image.open(os.path.join(IMG, r["id"] + ".jpg")).convert("RGB")
    cover = max(HW / im.width, HH / im.height)
    x, y = 10 + (i % cols) * cw, 10 + (i // cols) * ch
    sheet.paste(render(im, 1.0, -im.width * cover / 2, -im.height * cover / 2, r["box"]), (x, y + 30))
    sheet.paste(render(im, r["scale"], r["ox"], r["oy"]), (x + int(HW * S) + 10, y + 30))
    d.text((x, y + 6), f"{cards[r['id']]['name'][:30]} - {r['kind']}" + (f" -{round((1-r['scale'])*100)}%" if r["scale"] < 0.999 else "") + f"  (in frame {round(r['today']*100)}% > {round(r['kept']*100)}%)", fill=(245, 240, 232))
sheet.save(os.path.join(OUT, "sheet.png"))
print(f"\nsheet.png: {len(pick)} cards, today (subject outlined) | proposed")
