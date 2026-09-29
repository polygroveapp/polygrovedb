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

# %% how each photo could sit in the card's hexagon
import numpy as np
from framing_geom import HW, HH, KEEP, classify

report = []
for cid in have:
    b = boxes.get(cid)
    if not b: continue
    r = classify(b["w"], b["h"], b["grid"])
    if r: report.append({"id": cid, "group": cards[cid]["group"], "w": b["w"], "h": b["h"], "box": b["box"], "how": b["how"], **r})
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
