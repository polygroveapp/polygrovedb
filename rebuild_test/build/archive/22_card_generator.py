# %% [markdown]
# # PolygroveDB — card generator: regenerate the demo's 15 species from real data (step 22)
#
# The demo app (`Polygrove Demo/.../App.jsx`) hand-authored a `SPECIES`/`FACT_CARDS`
# contract. This regenerates those 15 species **from PolygroveDB alone** — the only
# hand input is each species' scientific name (+ cosmetic emoji). Everything the
# quiz needs is derived and cited:
# - **sci**  ← GBIF backbone canonicalName
# - **group** (Taxonomy Q) ← class → the group vocabulary
# - **trophic / role / falseRole** (Feeding-Guild Q) ← vert_niche + species_trophic_roles
# - **habitat** (Habitat Q) ← AVONET / ReptTraits / AmphiBIO
# - **size** (Size Q) ← EOL / ReptTraits / AmphiBIO
# - **origin** (Origin Q, plants) ← WCVP
# - **eats / eatenBy / connections** (Food-web Q) ← GloBI interactions
#
# The demo's hand-written `fact`/`falseFact` (Level 4) is intentionally NOT
# reproduced — per the no-LLM principle it can't be sourced. It's replaced by the
# data-backed cards (Size / Origin / Habitat), each carrying real food-web
# endpoints for the Solar level.

# %%
import duckdb, json
con = duckdb.connect("../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

# the ONLY hand input: slug, scientific name, cosmetic emoji + curated common name
SEED = [
 ("banana-slug","Ariolimax columbianus","Banana Slug","🐌"),
 ("raccoon","Procyon lotor","Raccoon","🦝"),
 ("stellers-jay","Cyanocitta stelleri","Steller's Jay","🐦"),
 ("ca-newt","Taricha torosa","California Newt","🦎"),
 ("deer","Odocoileus hemionus","Black-tailed Deer","🦌"),
 ("woodpecker","Melanerpes formicivorus","Acorn Woodpecker","🪶"),
 ("redwood-sorrel","Oxalis oregana","Redwood Sorrel","🍀"),
 ("tan-oak","Notholithocarpus densiflorus","Tan Oak","🌳"),
 ("garter-snake","Thamnophis sirtalis","CA Red-sided Garter Snake","🐍"),
 ("redwood","Sequoia sempervirens","Coast Redwood","🌲"),
 ("mountain-lion","Puma concolor","Mountain Lion","🦁"),
 ("turkey-tail","Trametes versicolor","Turkey Tail Fungus","🍄"),
 ("tree-frog","Pseudacris regilla","Pacific Tree Frog","🐸"),
 ("douglas-fir","Pseudotsuga menziesii","Coast Douglas-fir","🌲"),
 ("murrelet","Brachyramphus marmoratus","Marbled Murrelet","🪽"),
]
con.sql("CREATE OR REPLACE TEMP TABLE seed(slug VARCHAR, sci VARCHAR, cname VARCHAR, emoji VARCHAR)")
for slug,sci,cn,em in SEED:
    con.sql("INSERT INTO seed VALUES (?,?,?,?)", params=[slug,sci,cn,em])
con.sql("""CREATE OR REPLACE TEMP TABLE sid AS
  SELECT DISTINCT ON (seed.slug) seed.slug, seed.sci, seed.cname, seed.emoji,
         sp.species_id, sp.canonicalName, sp.class
  FROM seed JOIN name2sid n ON n.norm_name=norm(seed.sci)
            JOIN species sp ON sp.species_id=n.species_id
  ORDER BY seed.slug, sp.species_id;""")

# resolved GloBI edges WITH evidence count (# records backing each directed pair
# = how well-established the link is → the food-web curation ranking signal)
con.sql("""
CREATE OR REPLACE TEMP TABLE edges AS
SELECT ns.species_id AS pred_sid, nt.species_id AS prey_sid, count(*) AS evidence
FROM interactions i
JOIN name2sid ns ON ns.norm_name=norm(i.sourceTaxonName)
JOIN name2sid nt ON nt.norm_name=norm(i.targetTaxonName)
WHERE i.interactionTypeName IN ('eats','preysOn') AND ns.species_id<>nt.species_id
GROUP BY 1,2;
""")
# "documented enough to be a card?" proxy — a node is navigable if we have trait
# data or a common name for it (the food web gets more tappable as the catalog grows)
con.sql("""
CREATE OR REPLACE TEMP TABLE cardable AS SELECT DISTINCT species_id FROM (
  SELECT species_id FROM vert_niche WHERE niche IS NOT NULL
  UNION SELECT species_id FROM species_trophic_roles
  UNION SELECT species_id FROM species_common_names);
""")

# %% [markdown]
# ## Derivation maps (deterministic, no LLM)

# %%
GROUP_FROM_CLASS = {
 'Gastropoda':'Mollusk','Bivalvia':'Mollusk','Cephalopoda':'Mollusk',
 'Mammalia':'Mammal','Aves':'Bird','Amphibia':'Amphibian',
 'Squamata':'Reptile','Testudines':'Reptile','Crocodylia':'Reptile',
 'Actinopterygii':'Fish','Chondrichthyes':'Fish','Insecta':'Insect','Arachnida':'Arachnid',
 'Agaricomycetes':'Fungus','Magnoliopsida':'Plant','Liliopsida':'Plant',
 'Pinopsida':'Plant','Polypodiopsida':'Plant',
}
def niche_trophic(n):
    if n is None: return None
    if n in ('Herbivore','Herbivore terrestrial','Herbivore aquatic','Granivore','Frugivore','Nectarivore'): return 'Herbivore'
    if n=='Omnivore': return 'Omnivore'
    if n in ('Vertivore','Invertivore','Aquatic predator','Scavenger','Planktivore','Carnivore'): return 'Carnivore'
    return None
ROLE_TROPHIC = {'producer':'Producer','decomposer':'Decomposer','carnivore':'Carnivore',
                'herbivore':'Herbivore','omnivore':'Omnivore'}
ROLE  = {'Carnivore':'a carnivore','Herbivore':'a herbivore','Omnivore':'an omnivore',
         'Producer':'a producer','Decomposer':'a decomposer'}
FALSE = {'Carnivore':'a herbivore','Herbivore':'an omnivore','Omnivore':'a strict herbivore',
         'Producer':'a decomposer','Decomposer':'a producer'}
COLOR = {'Producer':'#FFD54F','Decomposer':'#A0785A','Herbivore':'#81C784',
         'Omnivore':'#64B5F6','Carnivore':'#E57373'}

rows = con.sql("SELECT slug, sci, cname, emoji, species_id, canonicalName, class FROM sid").fetchall()
by_sid = {r[4]: r[0] for r in rows}          # species_id -> slug (in-set membership)

def top_prey(spid, k=4):   # focal eats these — top k by evidence
    return con.sql(f"SELECT prey_sid, evidence FROM edges WHERE pred_sid={spid} ORDER BY evidence DESC LIMIT {k}").fetchall()
def top_preds(spid, k=4):  # focal eaten by these — top k by evidence
    return con.sql(f"SELECT pred_sid, evidence FROM edges WHERE prey_sid={spid} ORDER BY evidence DESC LIMIT {k}").fetchall()
def is_card(spid):
    return con.sql(f"SELECT 1 FROM cardable WHERE species_id={spid}").fetchone() is not None

def size_of(spid):
    r = con.sql("SELECT value FROM species_size WHERE species_id=? LIMIT 1", params=[spid]).fetchone()
    if r: return ("EOL", str(r[0]))
    r = con.sql("SELECT mass FROM bird_traits WHERE species_id=? AND mass IS NOT NULL", params=[spid]).fetchone()
    if r: return ("AVONET", f"{r[0]} g")
    r = con.sql("SELECT m.mass FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) WHERE n.species_id=? AND m.mass IS NOT NULL LIMIT 1", params=[spid]).fetchone()
    if r: return ("EltonTraits", f"{r[0]} g")
    r = con.sql("SELECT max_length_cm FROM fish_traits WHERE species_id=? AND max_length_cm IS NOT NULL", params=[spid]).fetchone()
    if r: return ("FishBase", f"{r[0]} cm")
    r = con.sql("SELECT mass_g, max_tl_mm FROM reptile_traits WHERE species_id=?", params=[spid]).fetchone()
    if r and (r[0] or r[1]): return ("ReptTraits", f"{r[0]} g" if r[0] else f"{r[1]} mm TL")
    r = con.sql("SELECT body_size_mm, mass FROM amphibian_traits WHERE species_id=?", params=[spid]).fetchone()
    if r and (r[0] or r[1]): return ("AmphiBIO", f"{r[0]} mm" if r[0] else f"{r[1]} g")
    return None

def habitat_of(spid):
    r = con.sql("SELECT habitat FROM bird_traits WHERE species_id=? AND habitat IS NOT NULL", params=[spid]).fetchone()
    if r: return ("AVONET", r[0])
    r = con.sql("SELECT habitat FROM reptile_traits WHERE species_id=? AND habitat IS NOT NULL AND habitat<>'None'", params=[spid]).fetchone()
    if r: return ("ReptTraits", r[0])
    r = con.sql("SELECT habitat FROM amphibian_traits WHERE species_id=? AND habitat IS NOT NULL", params=[spid]).fetchone()
    if r: return ("AmphiBIO", r[0])
    return None

def origin_of(spid):
    r = con.sql("SELECT string_agg(native_continent,', ') FROM species_native_origin WHERE species_id=?", params=[spid]).fetchone()
    return ("WCVP", r[0]) if r and r[0] else None

def trophic_of(spid):
    vn = con.sql("SELECT niche FROM vert_niche WHERE species_id=?", params=[spid]).fetchone()
    t = niche_trophic(vn[0]) if vn else None
    if t is None:
        rr = con.sql("SELECT role FROM species_trophic_roles WHERE species_id=? ORDER BY 1 LIMIT 1", params=[spid]).fetchone()
        if rr: t = ROLE_TROPHIC.get(rr[0])
    return t

# %% [markdown]
# ## Assemble SPECIES + data-backed CARDS

# %%
def disp_name(spid):     # prefer in-set curated name, then CrypticBio common name, then canonical
    slug = by_sid.get(spid)
    if slug: return next(r[2] for r in rows if r[0]==slug)
    r = con.sql(f"SELECT common_name FROM species_common_names WHERE species_id={spid} LIMIT 1").fetchone()
    if r: return r[0]
    r = con.sql(f"SELECT canonicalName FROM species WHERE species_id={spid}").fetchone()
    return r[0] if r else str(spid)

SPECIES, CARDS = [], []
for slug, sci, cname, emoji, spid, canon, cls in rows:
    group   = GROUP_FROM_CLASS.get(cls, cls)
    trophic = trophic_of(spid)
    # curated food web: top 4 eats + top 4 eaten-by, ranked by GloBI evidence,
    # each node tagged card|wild and inSet (which of our cards it links to)
    def node(sid, ev):
        return {"name": disp_name(sid), "evidence": ev,
                "card": is_card(sid), "inSet": by_sid.get(sid)}
    eats_web    = [node(s,e) for s,e in top_prey(spid)]
    eatenBy_web = [node(s,e) for s,e in top_preds(spid)]
    eats        = [n["name"] for n in eats_web]
    eatenBy     = [n["name"] for n in eatenBy_web]
    connections = sorted({n["inSet"] for n in eats_web+eatenBy_web if n["inSet"]})
    hab = habitat_of(spid); sz = size_of(spid); org = origin_of(spid)
    sp = {
      "id": slug, "name": cname, "sci": canon, "group": group,
      "trophic": trophic, "emoji": emoji,
      "color": COLOR.get(trophic, "#9E9E9E"), "accent": COLOR.get(trophic, "#9E9E9E"),
      "role":  ROLE.get(trophic),  "falseRole": FALSE.get(trophic),
      "base": {"habitat": hab[1] if hab else None},
      "foodweb": {"eats": eats_web, "eatenBy": eatenBy_web},   # curated top-N, with evidence
      "eats": eats, "eatenBy": eatenBy, "connections": connections,
      "_sources": {"sci":"GBIF","group":"GBIF-class","trophic":"vert_niche/trophic_roles",
                   "habitat": hab[0] if hab else None, "foodweb":"GloBI (top-N by evidence)"},
    }
    SPECIES.append(sp)
    # data-backed cards: one per available real attribute; solar endpoints = best-evidenced edges
    solarEats    = eats[0]    if eats    else None
    solarEatenBy = eatenBy[0] if eatenBy else None
    for label, val, src in [("Size", sz, sz[0] if sz else None),
                            ("Origin", org, "WCVP"),
                            ("Habitat", hab, hab[0] if hab else None)]:
        if val:
            CARDS.append({"speciesId": slug, "label": label, "value": val[1],
                          "source": val[0], "solarEats": solarEats, "solarEatenBy": solarEatenBy})

out = {"SPECIES": SPECIES, "CARDS": CARDS}
with open("generated_cards.json","w") as f: json.dump(out, f, indent=2, ensure_ascii=False)
print(f"wrote generated_cards.json — {len(SPECIES)} species, {len(CARDS)} data-backed cards")

# %% [markdown]
# ## Coverage: which of the data-backed questions each species supports

# %%
Q = ["Taxonomy","Feeding","Habitat","Foodweb","Size","Origin"]
print(f"{'species':<18}{'group':<9}{'trophic':<11} " + " ".join(f"{q[:4]:>5}" for q in Q))
for sp in SPECIES:
    has = {
      "Taxonomy": bool(sp["group"]), "Feeding": bool(sp["trophic"]),
      "Habitat": bool(sp["base"]["habitat"]), "Foodweb": bool(sp["eats"] or sp["eatenBy"]),
      "Size": any(c["speciesId"]==sp["id"] and c["label"]=="Size" for c in CARDS),
      "Origin": any(c["speciesId"]==sp["id"] and c["label"]=="Origin" for c in CARDS),
    }
    print(f"{sp['name']:<18}{str(sp['group']):<9}{str(sp['trophic']):<11} " +
          " ".join(f"{'  ✓' if has[q] else '  ·':>5}" for q in Q))

# %%
con.close()
