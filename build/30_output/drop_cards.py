# %% [markdown]
# # Take cards out of the shipped data
#
# Some species should not be cards at all (user, 2026-11-17: "remove the human card —
# that shouldn't be in the game"). `generate_catalog.py` leaves them out on a full rebuild
# (its NOT_IN_GAME list); this script makes the same cut in the data that is already
# shipped in `explorer/data`, so a change does not have to wait for the hours-long chain.
#
# For each dropped card it:
# - removes the card from `catalog.json` and `quiz.json`
# - KEEPS it as a named partner in other cards' food webs, marked as not a card. Those are
#   real records (people hunt the Goliath Frog, the pangolin, the Red River Hog), and for
#   twelve cards it is the only food-web record they have: cutting the name too would cost
#   those cards their food-web question, and on a rebuild their place in the deck. Set
#   KEEP_AS_PARTNER = False to cut the name as well; the food-web question of a card whose
#   answer it was is then re-answered with the next best partner, or dropped.
# - removes it from look-alikes and from size-comparison opponents
# - removes it from the ecoregion and near-the-pin rankings, the photo, framing,
#   second-photo and seasonality tables, and the explorer's candidate pool
#
# Run from `build/30_output`:  python3 drop_cards.py          (dry run, prints what would change)
#                              python3 drop_cards.py --write

# %%
import glob, json, sys

# keep in step with NOT_IN_GAME in generate_catalog.py
DROP = [
    {"id": "human", "name": "Human", "sci": "Homo sapiens"},
]
KEEP_AS_PARTNER = True
WRITE = "--write" in sys.argv
D = "../../explorer/data"
ids = {d["id"] for d in DROP}; names = {d["name"] for d in DROP}; scis = {d["sci"] for d in DROP}
def load(f): return json.load(open(f"{D}/{f}"))
def save(f, o):
    if WRITE: json.dump(o, open(f"{D}/{f}", "w"), ensure_ascii=False, separators=(",", ":"))

# %% catalog + quiz
catalog = load("catalog.json"); quiz = load("quiz.json")
before = len(catalog)
catalog = [c for c in catalog if c["id"] not in ids]
by_id = {c["id"]: c for c in catalog}
fw_cut = la_cut = q4_new = q4_gone = q3_cut = no_web = 0
for c in catalog:
    fw = c.get("foodweb") or {}
    for k in ("eats", "eatenBy"):
        if KEEP_AS_PARTNER:
            for e in fw.get(k, []):
                if e["name"] in names and (e.get("card") or e.get("inSet")): e["card"] = False; e["inSet"] = False; fw_cut += 1
            continue
        kept = [e for e in fw.get(k, []) if e["name"] not in names]
        fw_cut += len(fw.get(k, [])) - len(kept)
        if k in fw: fw[k] = kept
    if c.get("lookAlikes"):
        kept = [n for n in c["lookAlikes"] if n not in names]
        la_cut += len(c["lookAlikes"]) - len(kept); c["lookAlikes"] = kept
for i in ids: quiz.pop(i, None)
for cid, q in quiz.items():
    q4 = q.get("q4")
    if q4 and not KEEP_AS_PARTNER:
        for k in ("eats", "eatenBy"):
            part = q4.get(k)
            if not part: continue
            if part["answer"] in names:
                left = [e["name"] for e in (by_id.get(cid, {}).get("foodweb") or {}).get(k, [])]
                if left:
                    part["answer"] = left[0]
                    part["options"] = sorted(set([left[0]] + [o for o in part["options"] if o not in names]))
                    q4_new += 1
                else:
                    del q4[k]; q4_gone += 1
            elif any(o in names for o in part["options"]):
                part["options"] = [o for o in part["options"] if o not in names]
        if not q4:
            q["q4"] = None; no_web += 1
    q3 = q.get("q3")
    if q3 and q3.get("opponents"):
        kept = [o for o in q3["opponents"] if o["name"] not in names]
        q3_cut += len(q3["opponents"]) - len(kept); q3["opponents"] = kept
        if not kept: q["q3"] = None
print(f"catalog: {before:,} -> {len(catalog):,} cards")
print(f"food-web entries {'unlinked' if KEEP_AS_PARTNER else 'removed'}: {fw_cut} · look-alike entries removed: {la_cut} · size opponents removed: {q3_cut}")
print(f"food-web questions re-answered: {q4_new} · dropped: {q4_gone} · cards left with no food-web question: {no_web}")
save("catalog.json", catalog); save("quiz.json", quiz)
# the generator's own copies, which the shipped ones are copied from
if WRITE:
    import shutil
    shutil.copy(f"{D}/catalog.json", "catalog.json"); shutil.copy(f"{D}/quiz.json", "quiz.json")

# %% rankings: [[card id, count], ...] per ecoregion, and {cell: [[id, count], ...]} near the pin
n = 0
for f in glob.glob(f"{D}/eco_species/*.json"):
    rows = json.load(open(f)); kept = [r for r in rows if r[0] not in ids]
    if len(kept) != len(rows):
        n += 1
        if WRITE: json.dump(kept, open(f, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"eco_species files changed: {n}")
n = 0
for f in glob.glob(f"{D}/near/*.json"):
    cells = json.load(open(f)); hit = False
    for k, rows in cells.items():
        kept = [r for r in rows if r[0] not in ids]
        if len(kept) != len(rows): cells[k] = kept; hit = True
    if hit:
        n += 1
        if WRITE: json.dump(cells, open(f, "w"), ensure_ascii=False, separators=(",", ":"))
print(f"near files changed: {n}")

# %% tables keyed by card id, and the explorer's pool (rows start with the scientific name)
for f in ("photos.json", "framing.json", "second_photos.json", "seasonality.json", "inat_photos.json"):
    t = load(f); hit = [i for i in ids if i in t]
    for i in hit: del t[i]
    if hit: save(f, t)
    print(f"{f}: removed {len(hit)}")
pool = load("pool.json"); kept = [r for r in pool if r[0] not in scis]
print(f"pool.json: {len(pool):,} -> {len(kept):,}")
if len(kept) != len(pool): save("pool.json", kept)
print("written" if WRITE else "dry run — nothing written (pass --write)")
