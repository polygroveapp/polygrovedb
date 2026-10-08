# %% [markdown]
# # PolygroveDB — generate the REAL card catalog (step 24)
#
# nb22 regenerated the 15 demo species. This scales it: pull EVERY species that
# supports all six data-backed levels (Taxonomy + Feeding + Size + Food web +
# Habitat/Origin/Biome + Is-this-your-card), straight from the DB — no hand seed.
# Efficient/set-based: precompute each signal once, window the food web top-N.

# %%
import duckdb, json, os, time
con = duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
t0=time.time()

# Ectoparasite/louse/tick/flea/mite genera. GloBI records these as "eats" edges and
# name-resolution collisions (e.g. Myrsidea louse ← mysid shrimp) inflate their evidence,
# so they surface as bogus Q4 answers ("panda most known to eat a bird louse"). Blocklist
# both endpoints. Partial by design — the highest-frequency offenders in the flagship set.
con.sql("""CREATE OR REPLACE TEMP TABLE parasite_sids AS
SELECT species_id FROM species WHERE split_part(canonicalName,' ',1) IN
 ('Myrsidea','Menacanthus','Brueelia','Philopterus','Columbicola','Degeeriella','Ricinus',
  'Menopon','Menoponidae','Colpocephalum','Austromenopon','Amyrsidea','Machaerilaemus',
  'Ixodes','Dermacentor','Amblyomma','Rhipicephalus','Haemaphysalis','Argas','Ornithodoros',
  'Ctenocephalides','Xenopsylla','Pulex','Ceratophyllus',
  'Haematopinus','Linognathus','Bovicola','Trichodectes','Felicola','Damalinia','Polyplax',
  'Hoplopleura','Pediculus','Pthirus','Solenopotes','Werneckiella',
  -- round 2: waterfowl lice (Holomenopon "eats oak"), bat flies recorded as bat prey
  'Holomenopon','Trinoton','Anaticola','Anatoecus','Ornithobius','Pseudomenopon',
  'Leptocyclopodia','Cyclopodia','Nycteribia','Basilia','Penicillidia','Trichobius','Streblidae',
  'Laelaps','Ornithonyssus','Dermanyssus','Varroa','Sarcoptes','Demodex','Psoroptes');""")
# Curated known-bad edges. These are upstream GloBI mislabels with enough repeat
# records to clear any evidence floor, so they need naming individually. Each entry
# documents WHY (the bar for adding one: the claim is biologically impossible or a
# demonstrable name mixup, not merely surprising).
con.sql("""CREATE OR REPLACE TEMP TABLE blocked_edges AS
SELECT a.species_id pred_sid, b.species_id prey_sid FROM (VALUES
  ('orcinus orca','panthera leo'),          -- "sea lion" records mislabeled as lion (orca is marine; ev 4)
  ('carcharodon carcharias','panthera leo'),-- same mixup, great white "preying on" lion
  ('ursus maritimus','pusa sibirica'),      -- Baikal seal is LANDLOCKED; these are ringed-seal (P. hispida) mislabels (ev 203)
  ('desmodus rotundus','panthera leo')      -- vampire bat is Neotropical, lion African: zoo/captivity records, not wild ecology
) v(p,q)
JOIN name2sid a ON a.norm_name=v.p JOIN name2sid b ON b.norm_name=v.q;""")
# evidence-counted food-web edges (restricted later to the flagship set)
con.sql("""CREATE OR REPLACE TEMP TABLE edges AS
SELECT ns.species_id pred_sid, nt.species_id prey_sid, count(*) evidence,
       count(*) FILTER (WHERE i.interactionTypeName='preysOn') AS predation
FROM interactions i JOIN name2sid ns ON ns.norm_name=norm(i.sourceTaxonName)
JOIN name2sid nt ON nt.norm_name=norm(i.targetTaxonName)
JOIN species sk ON sk.species_id=ns.species_id
JOIN species tk ON tk.species_id=nt.species_id
-- hasHost from an INSECT onto a PLANT is herbivory (caterpillar/aphid/gall-wasp hostplants):
-- a food-web edge GloBI types differently. Animal hosts (parasitism) stay excluded.
WHERE (i.interactionTypeName IN ('eats','preysOn')
       OR (i.interactionTypeName='hasHost' AND sk.class='Insecta' AND tk.kingdom='Plantae'))
  AND ns.species_id<>nt.species_id
  AND ns.species_id NOT IN (SELECT species_id FROM parasite_sids)
  AND nt.species_id NOT IN (SELECT species_id FROM parasite_sids)
  AND NOT EXISTS (SELECT 1 FROM blocked_edges be
                  WHERE be.pred_sid=ns.species_id AND be.prey_sid=nt.species_id)
GROUP BY 1,2;""")

# TetrapodTraits CLASS GATE. TT rows carry their own Class; if name resolution put a
# TT row on a species of a different class, the row is a collision and every field on
# it is wrong (a Malagasy bird's mass/diet landed on a Malagasy TREE, which then read
# "Carnivore, 25.3 g, Arboreal"). Require the GBIF class to match TT's own class, so a
# mis-resolved row is dropped rather than silently pasted onto the wrong organism.
con.sql("""CREATE OR REPLACE TEMP TABLE tt_ok AS
SELECT t.* FROM tetrapod_traits t JOIN species s ON s.species_id=t.species_id
WHERE (t.class='Aves'     AND s.class='Aves')
   OR (t.class='Mammalia' AND s.class='Mammalia')
   OR (t.class='Amphibia' AND s.class='Amphibia')
   OR (t.class='Reptilia' AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia'));""")

# per-signal sets
# feeding guild, PRIORITY-ranked so a good source always wins the bucket. Priorities are
# now DISTINCT per source: arg_min ties were being broken arbitrarily, which is how EOL's
# bogus "decomposer" beat a real Herbivore reading on the same species.
# 0 = kingdom floor (definitional) > 1 = measured trait DBs > 2 = TetrapodTraits
# > 3 = EOL TraitBank guilds > 4 = GloBI-derived (inferred, last resort).
# The floor is restricted to source='taxonomy' (producer=Plantae/Chromista,
# decomposer=Fungi — true BY DEFINITION). EOL's 17,052 'decomposer' rows are all on
# ANIMALS (beaver, porcupine, squirrel) — that's not a decomposer, it's bad data, and it
# was being asserted as a TRUE quiz answer under a "definitional" provenance label. Dropped.
con.sql("""CREATE OR REPLACE TEMP TABLE feed AS
SELECT sid, arg_min(t, lpad(pri::VARCHAR,2,'0')||'|'||t) AS t, arg_min(src, lpad(pri::VARCHAR,2,'0')||'|'||t||'|'||src) AS src, arg_min(conf, lpad(pri::VARCHAR,2,'0')||'|'||t||'|'||conf) AS conf FROM (
  SELECT species_id sid, CASE role WHEN 'producer' THEN 'Producer' WHEN 'decomposer' THEN 'Decomposer' END AS t, 0 AS pri, 'taxonomy floor' AS src, 'definitional' AS conf
  FROM species_trophic_roles WHERE role IN ('producer','decomposer') AND source='taxonomy'
  -- BIRDS: use AVONET's Trophic.LEVEL, not its Niche. AVONET-niche 'Omnivore' means
  -- "multiple resource niches in equal proportion" — a macaw eating seeds+fruit+nectar
  -- (100% plants) is niche-Omnivore but level-Herbivore. Mapping niche->guild mislabeled
  -- 737 herbivorous + 172 carnivorous birds as game-Omnivores (caught by the user on the
  -- Scarlet Macaw card, 2026-09-08).
  UNION ALL SELECT species_id, CASE WHEN trophic_level IN ('Herbivore') THEN 'Herbivore'
       WHEN trophic_level='Omnivore' THEN 'Omnivore'
       WHEN trophic_level IN ('Carnivore','Scavenger') THEN 'Carnivore' END, 1, 'trait database', 'measured'
  FROM bird_traits WHERE trophic_level IS NOT NULL
  UNION ALL SELECT species_id, CASE WHEN niche IN ('Herbivore','Herbivore terrestrial','Herbivore aquatic','Granivore','Frugivore','Nectarivore') THEN 'Herbivore'
       WHEN niche='Omnivore' THEN 'Omnivore' WHEN niche IN ('Vertivore','Invertivore','Aquatic predator','Scavenger','Planktivore','Carnivore') THEN 'Carnivore' END, 1, 'trait database', 'measured'
  FROM vert_niche WHERE niche IS NOT NULL AND grp<>'bird'
  -- fish: CC-licensed FishBase replacement (Beukhof/FishTraits/Parravicini; see
  -- 10_sources/fish_traits_cc.py) — table is already fish-gated
  UNION ALL SELECT species_id, niche, 1, 'trait database', 'measured'
  FROM fish_traits_cc WHERE niche IS NOT NULL
  UNION ALL SELECT species_id, niche, 2, 'TetrapodTraits', 'measured' FROM tt_ok WHERE niche IS NOT NULL
  UNION ALL SELECT species_id,
    CASE WHEN count(DISTINCT role)>1 THEN 'Omnivore'          -- EOL says carnivore AND herbivore => omnivore
         WHEN max(role)='carnivore' THEN 'Carnivore' WHEN max(role)='herbivore' THEN 'Herbivore' ELSE 'Omnivore' END,
    3, 'EOL TraitBank', 'measured'
  FROM species_trophic_roles WHERE role IN ('carnivore','herbivore','omnivore') GROUP BY species_id
  UNION ALL SELECT species_id, 'Herbivore', 1, 'LepTraits (recorded hostplants)', 'measured'
  FROM lep_traits WHERE hostplant_fams >= 1
  -- order-level floors: every odonate and (to a textbook-exception) every spider is
  -- predatory — true by group membership, so 'definitional', and ranked above the
  -- GloBI record-count inference but below anything measured per-species.
  UNION ALL SELECT species_id, 'Carnivore', 4, 'taxonomy floor', 'definitional'
  FROM species WHERE "order" IN ('Odonata','Araneae')
  -- DECOMPOSERS BY GROUP (user, 2026-10-07: "make sure there is an accurate
  -- decomposer class"): the detritivores every ecology class names — earthworms,
  -- millipedes, springtails, woodlice, termites, dung beetles, carrion and hide
  -- beetles — are decomposers by what the whole group does, so 'definitional',
  -- ranked above EOL's guilds (which call earthworms herbivores) and below a
  -- per-species measurement. Scavenging birds and mammals are NOT here: a vulture
  -- is a carnivore in the game's five roles, as the trait databases say.
  UNION ALL SELECT species_id, 'Decomposer', 2, 'taxonomy floor', 'definitional'
  FROM species WHERE class IN ('Diplopoda','Collembola') OR "order"='Collembola'
     OR family IN ('Lumbricidae','Megascolecidae','Glossoscolecidae','Acanthodrilidae','Eudrilidae','Octochaetidae',
                   'Armadillidiidae','Porcellionidae','Oniscidae','Philosciidae','Trichoniscidae','Trachelipodidae','Agnaridae','Cylisticidae','Platyarthridae',
                   'Termitidae','Rhinotermitidae','Kalotermitidae','Termopsidae','Hodotermitidae','Mastotermitidae','Archotermopsidae',
                   'Silphidae','Trogidae','Dermestidae')
     OR (family='Scarabaeidae' AND genus IN ('Onthophagus','Aphodius','Phanaeus','Canthon','Scarabaeus','Copris','Geotrupes','Dichotomius','Deltochilum','Onitis','Sisyphus','Kheper','Gymnopleurus'))
  UNION ALL SELECT species_id, niche, 5, 'GloBI (from recorded prey)', 'inferred' FROM globi_feeding WHERE niche IS NOT NULL) sub
WHERE t IS NOT NULL GROUP BY sid;""")
# SIZE — only UNIT-TAGGED sources so a same-group comparison is like-with-like
# (each group uses one measure: birds/mammals/reptiles=g, fish/plants=cm, amph=mm).
# Raw EOL species_size is DROPPED: it's unitless and mixes mass with length, which
# makes "which is larger" nonsense (comparing mm to g).
# kingdom/class guards: a trait-DB name can collide with an unrelated species
# (a plant sharing a binomial with a bird), which would paste a bird's mass onto
# the plant. Gate every vertebrate source to its own class so that can't happen.
# priority-ranked like feed: within a species, a class-specific length source (mm)
# beats the generic AnimalTraits mass fallback, so insect/arachnid sizes stay
# length-based and comparable within their group.
con.sql("""CREATE OR REPLACE TEMP TABLE sz AS SELECT sid, arg_min(src, lpad(pri::VARCHAR,2,'0')||printf('%022.6f', 1e13-coalesce(TRY_CAST(split_part(val,' ',1) AS DOUBLE),0))||'|'||src) src, arg_min(val, lpad(pri::VARCHAR,2,'0')||printf('%022.6f', 1e13-coalesce(TRY_CAST(split_part(val,' ',1) AS DOUBLE),0))||'|'||src) val FROM (
  SELECT b.species_id sid, 'AVONET' src, b.mass::varchar||' g' val, 1 pri FROM bird_traits b JOIN species s ON s.species_id=b.species_id AND s.class='Aves' WHERE b.mass>0
  UNION ALL SELECT n.species_id,'EltonTraits', m.mass::varchar||' g', 1 FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) JOIN species s ON s.species_id=n.species_id AND s.class='Mammalia' WHERE m.mass>0
  UNION ALL SELECT r.species_id,'ReptTraits', r.mass_g::varchar||' g', 1 FROM reptile_traits r JOIN species s ON s.species_id=r.species_id AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia') WHERE r.mass_g>0
  UNION ALL SELECT a.species_id,'AmphiBIO', a.body_size_mm::varchar||' mm', 1 FROM amphibian_traits a JOIN species s ON s.species_id=a.species_id AND s.class='Amphibia' WHERE a.body_size_mm>0
  UNION ALL SELECT p.species_id,'EOL-height', round(p.height)::varchar||' cm', 1 FROM plant_fungi_size p JOIN species s ON s.species_id=p.species_id AND s.kingdom IN ('Plantae','Fungi') WHERE p.height>0
  -- BIEN (CC BY) + AusTraits (CC BY 4.0) plant heights (2026-10-05, plant_height_open.py): EOL covered ~4,000 plants; these cover far more
  UNION ALL SELECT p.species_id, p.src, round(p.height_cm)::varchar||' cm', 1 FROM plant_height_open p JOIN species s ON s.species_id=p.species_id AND s.kingdom='Plantae' WHERE p.height_cm>0
  UNION ALL SELECT species_id,'TetrapodTraits', size_val, 2 FROM tt_ok WHERE size_val IS NOT NULL
  UNION ALL SELECT l.species_id,'LepTraits', l.wingspan_mm::varchar||' mm wingspan', 1 FROM lep_traits l JOIN species s ON s.species_id=l.species_id AND s.class='Insecta' WHERE l.wingspan_mm>0
  UNION ALL SELECT o.species_id,'Odonate Phenotypic Database', o.body_mm::varchar||' mm', 1 FROM odonate_traits o JOIN species s ON s.species_id=o.species_id AND s.class='Insecta' WHERE o.body_mm>0
  UNION ALL SELECT w.species_id,'World Spider Traits', w.body_mm::varchar||' mm', 1 FROM spider_traits w JOIN species s ON s.species_id=w.species_id AND s.class='Arachnida' WHERE w.body_mm>0
  UNION ALL SELECT m.species_id,'EOL TraitBank (body mass)', m.mass_g::varchar||' g', 1 FROM mollusc_mass m JOIN species s ON s.species_id=m.species_id AND s.phylum='Mollusca' WHERE m.mass_g>0
  UNION ALL SELECT species_id, src, round(length_cm)::varchar||' cm', 1 FROM fish_traits_cc WHERE length_cm>0
  UNION ALL SELECT a.species_id,'AnimalTraits', a.mass_g::varchar||' g', 3 FROM animaltraits_size a JOIN species s ON s.species_id=a.species_id AND s.kingdom='Animalia' AND s.class NOT IN ('Aves','Mammalia','Amphibia','Squamata','Testudines','Crocodylia','Actinopterygii','Chondrichthyes') WHERE a.mass_g>0) GROUP BY sid;""")
# habitat vocabulary is CONTROLLED at the end: each source DB has its own casing and
# near-synonyms ('aquatic'/'Aquatic', 'Wetland'/'Wetlands'), which made the same concept
# read as different habitats across cards. Capitalize, then merge known variants.
con.sql("""CREATE OR REPLACE TEMP TABLE hab AS
SELECT sid, src, CASE h WHEN 'Wetlands' THEN 'Wetland' WHEN 'Rocky' THEN 'Rock'
                        WHEN 'Marine Neritic' THEN 'Marine' WHEN 'Marine Coastal' THEN 'Coastal'
                        WHEN 'Caves' THEN 'Cave' ELSE h END AS val
FROM (SELECT sid, arg_min(src, printf('%d|',pri)||val||'|'||src) src,
             upper(substr(arg_min(val, printf('%d|',pri)||val),1,1))||substr(arg_min(val, printf('%d|',pri)||val),2) AS h FROM (
  -- was any_value(): DuckDB's explicitly-nondeterministic pick — a toad with an AmphiBIO
  -- 'aquatic' row AND a TetrapodTraits 'terrestrial' row flipped between runs (caught by
  -- the clean-rebuild byte-diff). Group-specific measured DBs (pri 0) beat TT (pri 1);
  -- remaining ties break on the value itself.
  SELECT b.species_id sid, 0 pri, 'AVONET' src, b.habitat val FROM bird_traits b JOIN species s ON s.species_id=b.species_id AND s.class='Aves' WHERE b.habitat IS NOT NULL
  UNION ALL SELECT r.species_id, 0, 'ReptTraits',r.habitat FROM reptile_traits r JOIN species s ON s.species_id=r.species_id AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia') WHERE r.habitat IS NOT NULL AND r.habitat<>'None'
  UNION ALL SELECT a.species_id, 0, 'AmphiBIO',a.habitat FROM amphibian_traits a JOIN species s ON s.species_id=a.species_id AND s.class='Amphibia' WHERE a.habitat IS NOT NULL
  UNION ALL SELECT species_id, 0, src, habitat FROM fish_traits_cc WHERE habitat IS NOT NULL
  UNION ALL SELECT species_id, 1, 'TetrapodTraits',habitat FROM tt_ok WHERE habitat IS NOT NULL) GROUP BY sid);""")
# origin: DISTINCT + ORDER BY makes the continent list deterministic — previously
# 'NORTHERN AMERICA, SOUTHERN AMERICA' and its reverse both shipped as different strings.
con.sql("CREATE OR REPLACE TEMP TABLE orig AS SELECT species_id sid, string_agg(DISTINCT native_continent, ', ' ORDER BY native_continent) val FROM species_native_origin GROUP BY 1;")
# MIN_EV — a superlative claim ("MOST known to eat X") needs more than one record
# behind it. 42% of Q4 answers rested on a single GloBI row, and that thin band is
# exactly where the absurd answers lived (a dove "eating" a dove, evidence 2). Raising
# the floor is the single highest-leverage filter: it costs coverage, not correctness.
MIN_EV = 2

# PLAUSIBILITY, keyed off the SAME resolved guild the card displays (`feed`), so a card
# can no longer contradict itself. Previously only carnivores were filtered, which let
# 59 cards read "a herbivore" (Q2) and "most known to eat [an animal]" (Q4) at once —
# reversed edges (a fruit bat "eating" the kite that eats it), phoresy, and mislabels.
#   Carnivore -> prey must be an ANIMAL (a plant is perching/foraging substrate, not diet)
#   Herbivore -> prey must NOT be an animal
#   Producer  -> eats nothing
# Omnivore/Decomposer are genuinely broad, so they stay unfiltered.
con.sql(f"""CREATE OR REPLACE TEMP TABLE eats_ok AS
  SELECT e.pred_sid, e.prey_sid, e.evidence, e.predation
  FROM edges e
  JOIN species tp ON tp.species_id=e.prey_sid
  LEFT JOIN feed f ON f.sid=e.pred_sid
  WHERE e.evidence >= {MIN_EV}
    AND NOT (f.t='Carnivore' AND tp.kingdom<>'Animalia')
    AND NOT (f.t='Herbivore' AND tp.kingdom='Animalia')
    AND coalesce(f.t,'') <> 'Producer';""")
# food-web eligible = has real prey OR a real "eaten by" edge (kingdom-aware).
con.sql(f"""CREATE OR REPLACE TEMP TABLE fwset AS
  SELECT DISTINCT pred_sid sid FROM eats_ok
  UNION SELECT e.prey_sid FROM edges e JOIN species s ON s.species_id=e.prey_sid
    WHERE (s.kingdom='Animalia' AND e.predation>={MIN_EV}) OR (s.kingdom<>'Animalia' AND e.evidence>={MIN_EV});""")
con.sql("CREATE OR REPLACE TEMP TABLE biome AS SELECT DISTINCT species_id sid FROM species_ecoregions;")
# Q6 is now the same-family-nearest-location fallback (CrypticBio dropped — CC-BY-NC),
# so its eligibility is simply "has a location" (biome).

# card_pool: EVERY species with its per-signal flags — the permanent "which facts
# exist / which are missing" table. The explorer's every-species-has-a-card view
# and the commissioning batches read this; the flagship catalog is just its
# levels=5 slice.
con.sql("""CREATE OR REPLACE TABLE card_pool AS
  SELECT s.species_id, s.canonicalName,
    -- the GBIF backbone gives BONY FISH no class (only sharks/rays get one), so
    -- "class IS NOT NULL" silently erased ~43k fish incl. salmon (user caught it,
    -- 2026-09-09). Chordates with an order but no class are exactly that gap:
    -- label them 'Fish' so they enter the pool as their own group.
    coalesce(s.class, CASE WHEN s.phylum='Chordata' AND s."order" IS NOT NULL THEN 'Fish' END) AS class,
    s.kingdom,
    (s.species_id IN (SELECT sid FROM feed))::int  AS has_feeding,
    (s.species_id IN (SELECT sid FROM sz))::int    AS has_size,
    (s.species_id IN (SELECT sid FROM fwset))::int AS has_foodweb,
    ((s.species_id IN (SELECT sid FROM hab)) OR (s.species_id IN (SELECT sid FROM orig)) OR (s.species_id IN (SELECT sid FROM biome)))::int AS has_slot5,
    (s.species_id IN (SELECT sid FROM biome))::int AS has_biome
  FROM species s WHERE s.class IS NOT NULL OR (s.phylum='Chordata' AND s."order" IS NOT NULL);""")
con.sql("""CREATE OR REPLACE TABLE catalog AS
SELECT species_id, canonicalName, class, kingdom,
       has_feeding+has_size+has_foodweb+has_slot5+has_biome AS levels
FROM card_pool
WHERE has_feeding+has_size+has_foodweb+has_slot5+has_biome = 5;""")   # all 5 content levels present = every card has 6 questions
N=con.sql("SELECT count(*) FROM catalog").fetchone()[0]
print(f"catalog (every card = all 6 questions): {N:,} species  ({time.time()-t0:.0f}s)")
con.sql("SELECT levels+1 AS total_levels, count(*) n FROM catalog GROUP BY 1 ORDER BY 1 DESC").show()

# %% [markdown]
# ## Precompute lookups + windowed food web (top-4 each side by evidence)

# %%
def as_map(sql):
    return {r[0]: r[1] for r in con.sql(sql).fetchall()}
# display name: English vernacular when the backbone has one, else the canonical.
# Case-fix only vernaculars ("coast redwood" -> "Coast Redwood") — never touch a
# scientific name (title-casing an epithet would corrupt it).
def fixcase(s): return ' '.join(w if w[:1].isupper() else w[:1].upper()+w[1:] for w in s.split())
NAME = {}
WIKITITLE = dict(con.sql("SELECT species_id, wiki_title FROM species_fame WHERE wiki_title IS NOT NULL").fetchall())
for sid, common, canon0 in con.sql("""SELECT s.species_id, cn.common_name, s.canonicalName
    FROM species s LEFT JOIN species_common_names cn USING(species_id)""").fetchall():
    # prefer the Wikipedia article title when it is an English common name (fame-based
    # tiebreak: "Cougar" vs "Puma" resolves to whatever the world looks it up as)
    wt = WIKITITLE.get(sid)
    if common and wt and wt != canon0 and '(' not in wt and not wt[:1].islower():
        NAME[sid] = fixcase(wt)          # article title IS an English name -> use it
    else:
        NAME[sid] = fixcase(common) if common else canon0
# iNaturalist's preferred common name, for species with no other English name
# (2026-10-08: 2,769 cards were "Acantholycosa pedestris · Acantholycosa pedestris");
# fetched by fetch_inat_taxa.py, cached, applied last so every other source wins
_inat_names_path = "../cache/inat_names.json"
if os.path.exists(_inat_names_path):
    _n = 0
    for _sid, _nm in json.load(open(_inat_names_path)).items():
        _sid = int(_sid)
        if _sid in NAME and NAME[_sid] == con.sql("SELECT canonicalName FROM species WHERE species_id=?", params=[_sid]).fetchone()[0]:
            NAME[_sid] = fixcase(_nm); _n += 1
    print(f"iNaturalist common names applied: {_n}")
FEED = as_map("SELECT sid, t FROM feed")
# GLOBAL fame = Wikidata sitelink count (languages with an article) — language-neutral.
# English cited-sentence depth is deliberately NOT used for ranking (a worse version).
FAME = as_map("SELECT species_id, coalesce(sitelinks,0) FROM species_fame")
# sid -> [(category, share|None, source)]: EltonTraits shares first (real %), then
# TetrapodTraits presence flags. Among presence-only categories, a fixed SPECIFICITY
# order picks the answer (fish beats "plants"): deterministic and always a true food.
_SPEC = ['fish','nectar','seeds','fruit','carrion','reptiles and amphibians','mammals and birds',
         'other vertebrates','insects and other invertebrates','plants']
DIET = {}
for _sid,_cat,_fr,_src in con.sql("""SELECT species_id, category, max(frac), min(source) FROM diet_categories
    GROUP BY 1,2""").fetchall():
    DIET.setdefault(_sid, []).append((_cat, (round(_fr,2) if _fr is not None else None), _src))
for _sid in DIET:
    DIET[_sid].sort(key=lambda t: (0 if t[1] is not None else 1, -(t[1] or 0), _SPEC.index(t[0]) if t[0] in _SPEC else 99))
ALL_DIET_CATS = sorted({c for v in DIET.values() for c,_,_ in v})
POPU = as_map("SELECT species_id, obs_count FROM species_popularity")
FEED_SRC = {r[0]:(r[1],r[2]) for r in con.sql("SELECT sid,src,conf FROM feed").fetchall()}  # sid -> (source, confidence)
SZ   = {r[0]:(r[1],r[2]) for r in con.sql("SELECT sid,src,val FROM sz").fetchall()}
HAB  = {r[0]:(r[1],r[2]) for r in con.sql("SELECT sid,src,val FROM hab").fetchall()}
ORIG = as_map("SELECT sid, val FROM orig")
# primary biome: most records wins; on a TIE the SMALLER ecoregion wins — same
# record count in less area = higher density = likelier to actually encounter it
# there (user rule). eco id last so reruns are byte-identical.
# ...and ranked on PURE OBSERVATION COUNTS (the full-scan parquet), not the mixed
# species_ecoregions weights (obs counts / PHYLACINE cells / GARD km² / flat 100s —
# incomparable units, and the flat 100s were the source of most biome ties).
# Expert ranges are only the FALLBACK for species with no observations at all.
con.sql("""CREATE OR REPLACE TEMP TABLE obs_eco AS
  SELECT n.species_id, o.ecoregion_id, sum(o.occurrence_count) recs
  FROM read_parquet('../../data/occurrence_ecoregions_full.parquet') o
  JOIN name2sid n ON n.norm_name = norm(o.species)
  WHERE n.species_id IN (SELECT species_id FROM catalog) GROUP BY 1,2;""")
BIOME = as_map("""SELECT species_id, eco_name FROM (
  SELECT x.species_id, e.ECO_NAME AS eco_name,
         row_number() OVER (PARTITION BY x.species_id ORDER BY x.w DESC, a.km2 ASC, e.ECO_ID) rn
  FROM (
    SELECT species_id, ecoregion_id, recs AS w FROM obs_eco
    UNION ALL   -- fallback: expert-range weights, only where no observations exist
    SELECT se.species_id, se.ecoregion_id, se.occurrence_count FROM species_ecoregions se
    WHERE se.species_id IN (SELECT species_id FROM catalog)
      AND se.species_id NOT IN (SELECT species_id FROM obs_eco)) x
  JOIN ecoregions e ON e.ECO_ID = x.ecoregion_id
  JOIN ecoregion_area a ON a.ECO_ID = e.ECO_ID)
  WHERE rn = 1""")
# per-card range = its ecoregion ids (top 60 by weight caps the map payload;
# beyond that a range is visually saturated anyway).
# MEMBERSHIP FLOOR (user, 2026-09-26 — "are there really lions in Alaska?"):
# a single stray record doesn't put a species in a deck (MIN_RECS=2). NOT higher,
# and NO share-of-records rule: GBIF is so undersampled in Africa that a 1% rule
# threw the Stone-curlew and the Elephant out of the Sahel, and the African Bush
# Elephant's real Sahel presence is 2 records. Counts can't tell a zoo from a
# habitat anyway — captives are a MAMMAL problem ("there aren't really zoos for
# insects, and trees in a zoo are still part of the ecosystem") and are handled by
# the PHYLACINE range filter below. Ranked on PURE observation counts (obs_eco),
# not the mixed species_ecoregions weights; expert ranges (PHYLACINE/GARD) stay
# the fallback for species with no observations at all.
# RAISED TO 10 (user, 2026-10-08: "why are there so many species in each
# ecoregion" — half of every deck was species with fewer than ten records
# there; a deck should feel like the place), with every species keeping its
# best ecoregion whatever the count (below). Expert ranges (PHYLACINE/GARD)
# are untouched: a mammal's range still floors its membership.
MIN_RECS, MIN_SHARE = 10, 0.0
# MAMMAL RANGE FILTER (part 2): a mammal's observed ecoregion counts only if it lies
# inside its PHYLACINE 1.2 CURRENT range (mammal_ranges, written by
# 20_derive/phylacine.py — NOT species_ecoregions, which occurrence_integrate.py
# tops up with observations, zoo sightings included). Outside the range = a zoo, an
# escapee or a stray: European zoo photos are 13% of every Lion record on GBIF, so
# no share-of-records override can be trusted. Mammals PHYLACINE doesn't map keep
# their observations (nothing to filter against). Only mammals: birds migrate (both
# decks are true), and nobody keeps insects in zoos.
con.sql("""CREATE OR REPLACE TEMP TABLE mam_range AS
  SELECT species_id, ecoregion_id FROM mammal_ranges;""")
con.sql("""CREATE OR REPLACE TEMP TABLE mam_mapped AS
  SELECT DISTINCT species_id FROM mammal_ranges;""")
ECOS = {}
# outer ORDER BY is load-bearing: without it the parallel scan returns rows in arbitrary
# order and the per-card list (which IS the card's ranked range) reshuffles between runs.
for sid, eco, _rn in con.sql(f"""SELECT species_id, ecoregion_id, rn FROM (
    SELECT species_id, ecoregion_id,
           row_number() OVER (PARTITION BY species_id ORDER BY w DESC, ecoregion_id) rn
    FROM (
      -- one row per (species, ecoregion): an observation inside a mammal's range
      -- appears in both branches below; keep the stronger weight
      SELECT species_id, ecoregion_id, max(w) AS w FROM (
      SELECT o.species_id, o.ecoregion_id, o.recs AS w
      FROM (SELECT species_id, ecoregion_id, recs,
                   recs * 1.0 / sum(recs) OVER (PARTITION BY species_id) AS frac,
                   row_number() OVER (PARTITION BY species_id ORDER BY recs DESC, ecoregion_id) AS rnk
            FROM obs_eco) o
      JOIN species s ON s.species_id = o.species_id
      -- a species' BEST ecoregion always counts (user, 2026-10-08: "are there any
      -- cards that are left out of the game now that we set a floor?" — at a flat
      -- floor of 10, 1,148 cards would have belonged to no deck: GBIF is thin
      -- outside North America and Europe, so a Goliath Frog has 2 records
      -- anywhere). The floor trims a species' OTHER, stray memberships only.
      WHERE (o.recs >= {MIN_RECS} OR o.rnk = 1) AND o.frac >= {MIN_SHARE}
        AND (s.class <> 'Mammalia'
             OR o.species_id NOT IN (SELECT species_id FROM mam_mapped)
             OR (o.species_id, o.ecoregion_id) IN (SELECT species_id, ecoregion_id FROM mam_range))
      UNION ALL   -- mapped mammals: the PHYLACINE range is the FLOOR of membership
      -- (2026-09-27): the Elephant's only Sahel records were museum specimens, so
      -- sightings-only observation left it out of a deck its expert range puts it
      -- squarely in. Range cells rank below observation counts, so observed
      -- ecoregions still lead the card's list; the floor just never drops out.
      SELECT mr.species_id, mr.ecoregion_id, mr.cells * 0.001 AS w
      FROM mammal_ranges mr
      WHERE mr.species_id IN (SELECT species_id FROM catalog)
        AND mr.species_id IN (SELECT species_id FROM obs_eco)
      UNION ALL   -- fallback: expert-range weights, only where no observations exist
      SELECT se.species_id, se.ecoregion_id, se.occurrence_count FROM species_ecoregions se
      WHERE se.species_id IN (SELECT species_id FROM catalog)
        AND se.species_id NOT IN (SELECT species_id FROM obs_eco)
      ) GROUP BY species_id, ecoregion_id))
  WHERE rn<=60 ORDER BY species_id, rn""").fetchall():
    ECOS.setdefault(sid, []).append(eco)
print("ecoregion memberships:", sum(len(v) for v in ECOS.values()), "pairs across", len(ECOS), "species",
      f"(threshold >={MIN_RECS} recs & >={MIN_SHARE:.0%} of the species' records)")
cat_ids = [r[0] for r in con.sql("SELECT species_id FROM catalog").fetchall()]
catset = set(cat_ids)
CARDABLE = set(r[0] for r in con.sql("""SELECT DISTINCT species_id FROM (
  SELECT species_id FROM vert_niche WHERE niche IS NOT NULL UNION SELECT species_id FROM species_trophic_roles)""").fetchall())

# windowed top-4 eats + top-4 eaten-by for the whole catalog at once
con.sql("""CREATE OR REPLACE TEMP TABLE fw_eats AS
  SELECT pred_sid sid, prey_sid partner, evidence FROM eats_ok WHERE pred_sid IN (SELECT species_id FROM catalog)
  QUALIFY row_number() OVER (PARTITION BY pred_sid ORDER BY evidence DESC, prey_sid)<=12;""")
con.sql(f"""CREATE OR REPLACE TEMP TABLE fw_eb AS
  SELECT prey_sid sid, pred_sid partner, ev AS evidence FROM (
    SELECT e.prey_sid, e.pred_sid,
      CASE WHEN s.kingdom='Animalia' THEN e.predation ELSE e.evidence END AS ev
    FROM edges e JOIN species s ON s.species_id=e.prey_sid
    WHERE e.prey_sid IN (SELECT species_id FROM catalog))
  WHERE ev>={MIN_EV}
  QUALIFY row_number() OVER (PARTITION BY prey_sid ORDER BY ev DESC, pred_sid)<=12;""")
from collections import defaultdict
EATS=defaultdict(list); EB=defaultdict(list)
# ORDER BY evidence DESC so node[0] is genuinely the highest-evidence ("most known") edge
for sid,p,e in con.sql("SELECT sid,partner,evidence FROM fw_eats ORDER BY sid, evidence DESC, partner").fetchall(): EATS[sid].append((p,e))
for sid,p,e in con.sql("SELECT sid,partner,evidence FROM fw_eb   ORDER BY sid, evidence DESC, partner").fetchall(): EB[sid].append((p,e))
# DETERMINISTIC, MEANINGFUL tie-breaking. 40% of Q4 pools have an exact or near tie at
# the top, so "which one is first" was a coin flip between runs. Order ties toward the
# partner that is itself a deck card (the player can meet it — same logic as Q6's
# in-deck decoys), then one with a common name, then by id so reruns are identical.
HASCN = set(r[0] for r in con.sql("SELECT species_id FROM species_common_names").fetchall())
# RANGE-OVERLAP tiebreak (user rule): among tied partners prefer the one whose observed
# ecoregions overlap the species' own the most — the interaction most likely to happen
# in this species' actual world. Top-30 ecoregions per side, same metric as look-alikes.
con.sql("""CREATE OR REPLACE TEMP TABLE fw_pairs AS
  SELECT sid, partner FROM fw_eats UNION SELECT sid, partner FROM fw_eb;""")
con.sql("""CREATE OR REPLACE TEMP TABLE pair_eco AS
  SELECT species_id, ecoregion_id FROM (
    SELECT species_id, ecoregion_id,
           row_number() OVER (PARTITION BY species_id ORDER BY occurrence_count DESC, ecoregion_id) rn
    FROM species_ecoregions
    WHERE species_id IN (SELECT sid FROM fw_pairs UNION SELECT partner FROM fw_pairs))
  WHERE rn<=30;""")
SHARED = {(r[0],r[1]):r[2] for r in con.sql("""
  SELECT fp.sid, fp.partner, count(*) FROM fw_pairs fp
  JOIN pair_eco a ON a.species_id=fp.sid
  JOIN pair_eco b ON b.species_id=fp.partner AND b.ecoregion_id=a.ecoregion_id
  GROUP BY 1,2""").fetchall()}
# order: evidence > is a deck card > range overlap > has common name > id (stable)
def _rank(sid, pe):
    p,e = pe
    return (-e, 0 if p in catset else 1, -SHARED.get((sid,p),0), 0 if p in HASCN else 1, p)
for _d in (EATS, EB):
    for _k in _d:
        _d[_k].sort(key=lambda pe, _k=_k: _rank(_k, pe))
        del _d[_k][4:]   # SQL fetched a deterministic top-12 so ties are fully visible; card shows 4
# Q6 look-alikes: 2 decoy CARDS FROM THE DECK ("which is your card?" shows 3 real
# cards at once — the original design). Decoys must be deck cards so a wrong pick
# resolves coherently: "that's the leopard" is a card you can then meet, not a random
# backbone species with no photo and no place in the game. (This also kills the
# fossil-decoy problem — extinct species can't be cards.) Ranked by confusability,
# filled GREEDILY down the tiers so nearly every card gets 2 decoys:
#   tier 1: same family, range overlaps (what you'd actually confuse in the field)
#   tier 2: same family, elsewhere      (looks alike, lives apart)
#   tier 3: same order, range overlaps  (a local relative, e.g. another hawk)
#   tier 4: same class, range overlaps  (a local same-group card, last resort)
# Within a tier: same genus first, then most shared ecoregions.
# Pure GBIF taxonomy + RESOLVE ecoregions — both CC-BY.
LA=defaultdict(list)
for sid,p in con.sql("""
WITH deck AS (
  SELECT c.species_id AS sid, s.genus, s.family, s."order" AS ord, s.class
  FROM catalog c JOIN species s ON s.species_id=c.species_id
), deck_eco AS (  -- top-30 ecoregions per deck species (full table self-join would
                  -- explode now that the occurrence run put 6.5M pairs in)
  SELECT species_id, ecoregion_id FROM (
    SELECT species_id, ecoregion_id,
           row_number() OVER (PARTITION BY species_id ORDER BY occurrence_count DESC, ecoregion_id) rn
    FROM species_ecoregions WHERE species_id IN (SELECT sid FROM deck))
  WHERE rn<=30
), shared AS (   -- shared-ecoregion counts between deck cards of the same class
  SELECT a.species_id p, b.species_id q, count(DISTINCT a.ecoregion_id) n
  FROM deck_eco a JOIN deck_eco b
    ON b.ecoregion_id=a.ecoregion_id AND b.species_id<>a.species_id
  GROUP BY 1,2
), cand AS (
  SELECT d.sid, o.sid AS partner,
    CASE WHEN o.family=d.family AND sh.n>0 THEN 1
         WHEN o.family=d.family            THEN 2
         WHEN o.ord=d.ord     AND sh.n>0   THEN 3
         WHEN sh.n>0                       THEN 4 END AS tier,
    coalesce((o.genus=d.genus)::int,0) AS sg, coalesce(sh.n,0) AS shared_ecos
  FROM deck d
  JOIN deck o ON o.class=d.class AND o.sid<>d.sid
  LEFT JOIN shared sh ON sh.p=d.sid AND sh.q=o.sid
)
SELECT sid, partner FROM (
  SELECT sid, partner, row_number() OVER (PARTITION BY sid
    ORDER BY tier, sg DESC, shared_ecos DESC, partner) AS rn
  FROM cand WHERE tier IS NOT NULL)
WHERE rn<=2 ORDER BY sid, rn""").fetchall():
    LA[sid].append(p)

# %% [markdown]
# ## Emit the catalog JSON

# %%
GROUP={'Gastropoda':'Mollusk','Bivalvia':'Mollusk','Cephalopoda':'Mollusk','Mammalia':'Mammal','Aves':'Bird',
 'Amphibia':'Amphibian','Squamata':'Reptile','Testudines':'Reptile','Crocodylia':'Reptile',
 'Rhynchocephalia':'Reptile','Sphenodontia':'Reptile','Actinopterygii':'Fish',
 'Chondrichthyes':'Fish','Actinopteri':'Fish','Sarcopterygii':'Fish','Myxini':'Fish','Petromyzonti':'Fish',
 'Elasmobranchii':'Fish','Holocephali':'Fish',
 'Insecta':'Insect','Arachnida':'Arachnid','Malacostraca':'Crustacean','Branchiopoda':'Crustacean','Maxillopoda':'Crustacean',
 'Agaricomycetes':'Fungus','Basidiomycota':'Fungus','Ascomycota':'Fungus','Lecanoromycetes':'Fungus',
 'Magnoliopsida':'Plant','Liliopsida':'Plant','Pinopsida':'Plant','Polypodiopsida':'Plant',
 'Bryopsida':'Plant','Gnetopsida':'Plant','Cycadopsida':'Plant','Lycopodiopsida':'Plant','Marchantiopsida':'Plant',
 'Polyplacophora':'Mollusk','Scaphopoda':'Mollusk','Clitellata':'Worm','Polychaeta':'Worm',
 'Fish':'Fish'}   # the synthetic class for the backbone's class-less bony fish
# plants split into WCVP growth-form groups (user, 2026-09-09) — Tree/Shrub/Herb/
# Geophyte/Climber/etc from 20_derive/plant_lifeform.py; unmatched stay 'Plant'
LIFE={sid:lf for sid,lf in con.sql("SELECT species_id, lifeform FROM plant_lifeform").fetchall()}
# CLIMATE fact (user, 2026-09-09): tetrapods get range-average temperature +
# rainfall (TetrapodTraits/CHELSA — temperature is stored as deg C x 10), plants
# get WCVP's climate zone. AVG + min() for byte-deterministic single values.
CLIM={}
for sid,t,p,z in con.sql("""
  SELECT species_id,
    avg(value_num) FILTER (source='TetrapodTraits' AND trait='mean annual temperature'),
    avg(value_num) FILTER (source='TetrapodTraits' AND trait='annual precipitation'),
    min(val)       FILTER (source='WCVP' AND trait='climate')
  FROM traits_long
  WHERE (source='TetrapodTraits' AND trait IN ('mean annual temperature','annual precipitation'))
     OR (source='WCVP' AND trait='climate')
  GROUP BY 1""").fetchall():
    d={}
    if t is not None: d["tempC"]=round(t/10,1)
    if p is not None: d["precipMm"]=int(round(p))
    if z: d["zone"]=z
    if d: CLIM[sid]=d
import random
_GW  = {'Carnivore':'a carnivore','Herbivore':'a herbivore','Omnivore':'an omnivore'}
_OTH = {'Carnivore':['an omnivore','a herbivore'],'Herbivore':['an omnivore','a carnivore'],
        'Omnivore':['a carnivore','a herbivore']}
def q2_framing(sid, trophic):
    # Q2 feeding-guild true/false, on the REAL measured guild only. Producer<->
    # decomposer are each other's trap; carnivore/herbivore/omnivore trap = a
    # guild it isn't. "Apex predator" was dropped: our only apex signal was
    # "GloBI records no predator", which is sparsity — not apex status — and it
    # was asserting apex for 900+ herbivores/omnivores (factually false answers).
    rng = random.Random(sid*7+1)
    if trophic=='Producer':   return ("a producer","a decomposer")
    if trophic=='Decomposer': return ("a decomposer","a producer")
    guild = _GW.get(trophic, f"a {str(trophic).lower()}" if trophic else "a carnivore")
    false_word = rng.choice(_OTH.get(trophic,['an omnivore']))
    return (guild, false_word)
def q4_dir(sid, trophic, best_eats, best_eb):
    # Ask the question where the evidence lives. Plants can't eat -> eaten-by;
    # one-sided -> that side; and when one direction is >=10x better-attested,
    # take it (a lion with buffalo-prey at ev 160 shouldn't get "most eaten by a
    # martial eagle, ev 2" because a coin flip landed on the thin side). Only
    # genuinely comparable directions stay random.
    if trophic=='Producer' or not best_eats: return 'eatenBy'
    if not best_eb: return 'eats'
    if best_eats >= 10*best_eb: return 'eats'
    if best_eb >= 10*best_eats: return 'eatenBy'
    return 'eats' if random.Random(sid*13+3).random()<0.5 else 'eatenBy'
def slugify(name): return name.lower().replace(' ','-').replace("'","")
def node(sid,e): return {"name":NAME.get(sid,str(sid)),"evidence":e,"card":sid in CARDABLE,"inSet":sid in catset}
import re
def round_size(s):
    # trim raw float precision ("63.081208137225424 g" -> "63.1 g"); leave unit intact
    if not s: return s
    m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*(.*)$', str(s))
    if not m: return s
    val = float(m.group(1)); unit = m.group(2).strip()
    num = str(int(val)) if val == int(val) else f"{val:.1f}"
    if num.endswith(".0"): num = num[:-2]   # 51600.02 -> "51600.0" -> "51600"
    return f"{num} {unit}".strip()

import re as _re
def _sizeval(v):
    m=_re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*(.*)$', str(v or ''))
    return (float(m.group(1)), m.group(2).strip()) if m else (None, None)
# Q3 "Which is bigger?" opponents: same group + same measure (g vs g, mm wingspan vs
# mm wingspan), size differing by >=25% so the question has a real answer, ranked by
# GLOBAL fame (Wikidata sitelinks) then observation count — species people actually know.
_grp_members = {}
for _sid, _cls in con.sql("SELECT species_id, class FROM catalog").fetchall():
    _v,_u = _sizeval(SZ.get(_sid,(None,None))[1])
    if _v is None or _v<=0: continue
    _grp_members.setdefault((GROUP.get(_cls,_cls), _u), []).append((_sid,_v))
for _k in _grp_members:
    _grp_members[_k].sort(key=lambda t: (-FAME.get(t[0],0), -POPU.get(t[0],0), t[0]))
# Q3 SIZE BAND. Our sources give ONE central value per species, but real body size is a
# distribution (sex, age, geography — dimorphism alone can be 2x). So a pairwise "which is
# bigger" is only honest when the two means are far enough apart that the ranges can't
# plausibly overlap: >=3x. Above ~12x the answer is usually obvious (redwood vs barley),
# so 3-12x is the band we prefer; wider pairs are the fallback rather than the default.
Q3_MIN, Q3_MAX = 3.0, 12.0
# Q3 SIZE COMPARISON — three-way, measure-aware, and honest about what the number is.
# Our sources give ONE central value per species while real body size is a distribution,
# so the question asks about the AVERAGE and offers "about the same" as a real answer:
# pairs whose means are within SAME_BAND are genuinely indistinguishable, and saying so
# is correct rather than a coin flip. The verb follows the measure (mass->heavier,
# length->longer, height->taller, wingspan->wider).
# BANDS (user, 2026-09-08 — replaces the earlier 10% band + 10-50% dead zone):
# the grace window is ±5% AROUND THE CARD'S MEAN, and every pair outside it is a
# fair question with a definite answer. No dead zone: an opponent within
# [0.95v, 1.05v] makes "about the same" the correct answer; anything else is
# simply heavier/lighter (longer/shorter, taller/shorter, wider/narrower).
GRACE_PCT = 0.05
_MEASURE = {'g':          ('mass',     'heavier', 'lighter'),
            'mm':         ('length',   'longer',  'shorter'),
            'cm':         ('height',   'taller',  'shorter'),
            'mm wingspan':('wingspan', 'wider',   'narrower')}
def q3_opponents(sid, cls):
    v, u = _sizeval(SZ.get(sid,(None,None))[1])
    if v is None or v<=0 or u not in _MEASURE: return None
    measure, big_word, small_word = _MEASURE[u]
    buckets = {'same':[], 'bigger':[], 'smaller':[]}      # fame-ordered within each
    for osid, ov in _grp_members.get((GROUP.get(cls,cls), u), []):
        if osid==sid or ov<=0: continue
        d = abs(ov-v)/v                                    # opponent's offset from the card's mean
        if   d <= GRACE_PCT: b, ans = 'same', 'about the same'
        elif v > ov:         b, ans = 'bigger', big_word
        else:                b, ans = 'smaller', small_word
        if len(buckets[b]) >= 2: continue
        buckets[b].append({"name": NAME.get(osid,str(osid)), "size": round_size(SZ[osid][1]),
                           "answer": ans, "pctDiff": round(d*100)})
        if sum(len(x) for x in buckets.values()) >= 6: break
    out = [b[0] for b in (buckets['bigger'], buckets['smaller'], buckets['same']) if b]
    out += [o for b in buckets.values() for o in b[1:]]
    if not out: return None
    return {"measure": measure, "bigger": big_word, "smaller": small_word,
            "sameWithinPct": int(GRACE_PCT*100),
            "opponents": out[:4]}
# ---- Q4 OPTION LISTS -------------------------------------------------------
# Two lists per card: "what does it eat?" and "what eats it?", each 1 true partner
# + 2 distractors. A distractor is (a) the SAME trophic role as the true answer, so
# you can't reason it out from ecology alone, and (b) a species that shares NO
# ecoregion with this card — which is what makes "wrong" defensible: absence of a
# GloBI record isn't proof it doesn't eat something, but no range overlap is.
# Producers/decomposers don't eat: their "eats" answer is how they get energy.
ECO_SET = {}
for _sid, _eco in con.sql("""SELECT species_id, ecoregion_id FROM species_ecoregions
    WHERE species_id IN (SELECT species_id FROM catalog)""").fetchall():
    ECO_SET.setdefault(_sid, set()).add(_eco)
_CLS = dict(con.sql("SELECT species_id, class FROM species").fetchall())
_CANON2 = dict(con.sql("SELECT species_id, canonicalName FROM species").fetchall())
_GRP = lambda x: GROUP.get(_CLS.get(x), _CLS.get(x))
def _sz(x):
    v,_u = _sizeval(SZ.get(x,(None,None))[1]); return v
# candidates indexed by (trophic role, group) and fame-ordered; named species first so
# an option list reads like a field guide rather than a taxonomy dump
# Distractor pool = every species with a COMMON NAME (not just deck cards): a
# pelican's prey is a fish and a robin's is an earthworm, and neither group is in
# the deck, so drawing only from cards left those lists with no plausible options.
_CAND = {}
for _sid, _cn in con.sql("""SELECT cn.species_id, cn.common_name FROM species_common_names cn
    ORDER BY cn.species_id""").fetchall():
    _CAND.setdefault((FEED.get(_sid), _GRP(_sid)), []).append(_sid)
for _k in _CAND:
    _CAND[_k].sort(key=lambda x: (-FAME.get(x,0), -POPU.get(x,0), x))
_BY_GRP = {}
for (_r,_g), _lst in _CAND.items():
    _BY_GRP.setdefault(_g, []).extend(_lst)
for _g in _BY_GRP:
    _BY_GRP[_g].sort(key=lambda x: (-FAME.get(x,0), -POPU.get(x,0), x))
ENERGY = ['Photosynthesis', 'Decaying matter', 'Live prey', 'Leaves and plants']
# the deck: the species that are cards, and so have a photo in the app. A decoy
# is matched to the answer on this (user, 2026-10-07: "the answer always has no
# photo" — the answer is whatever the records name, the decoys were mostly cards,
# and the one empty hexagon gave it away)
CATALOG_IDS = set(r[0] for r in con.sql("SELECT species_id FROM catalog").fetchall())
def _distractors(sid, answer_sid, exclude, k=2):
    """Same group as the true answer (never crossed — a robin 'eating a hippo' is
    worse than a short list), same trophic role where possible, similar size, the
    same card-or-not standing as the answer (see CATALOG_IDS), and preferring
    species this card shares NO ecoregion with, which is what makes 'wrong'
    defensible: they never meet."""
    role, grp, asz = FEED.get(answer_sid), _GRP(answer_sid), _sz(answer_sid)
    mine = ECO_SET.get(sid, set())
    a_card = answer_sid in CATALOG_IDS
    def score(o):
        theirs = ECO_SET.get(o)
        overlap = 0 if (theirs is not None and not (mine & theirs)) else (1 if theirs is None else 2)
        osz = _sz(o)
        size_ok = 0 if (asz is not None and osz is not None and 0.25 <= osz/asz <= 4.0) else 1
        return (0 if (o in CATALOG_IDS) == a_card else 1, overlap, size_ok)
    seen, cands = set(), []
    for pool in (_CAND.get((role, grp), []), _BY_GRP.get(grp, [])):
        for osid in pool[:400]:
            if osid in (sid, answer_sid) or osid in exclude or osid in seen: continue
            seen.add(osid); cands.append(osid)
        if len(cands) >= 12: break
    cands.sort(key=score)
    return cands[:k]
def q4_lists(sid, trophic, eats, eb):
    partners = {p for p,_ in EATS.get(sid,[])} | {p for p,_ in EB.get(sid,[])} | {sid}
    # DIRECTION EVIDENCE RATIO (user, 2026-08-24): when both directions exist, only ask
    # the one(s) the evidence actually supports — if one side is >=10x better documented,
    # the weak side's question is dropped (the edge stays on the card as a fact). This is
    # what retires "cougar eaten by wolf" as a QUESTION (eats 1,569 vs eaten-by 23)
    # without curating any true record: symmetric, evidence-only, no species judgment.
    # A card whose ONLY direction is the weak one keeps it (eligibility: whichever exists).
    ea_tot = sum(e for _,e in EATS.get(sid,[]))
    eb_tot = sum(e for _,e in EB.get(sid,[]))
    if eats and eb and trophic not in ('Producer','Decomposer'):
        if ea_tot >= 10*eb_tot: eb = None
        elif eb_tot >= 10*ea_tot: eats = None
    out = {}
    if trophic in ('Producer','Decomposer'):
        ans = 'Photosynthesis' if trophic=='Producer' else 'Decaying matter'
        others = [e for e in ENERGY if e!=ans]
        out['eats'] = {"question": "How does it get its energy?", "answer": ans,
                       "options": sorted([ans]+random.Random(sid*23+7).sample(others, 2))}
    elif eats:
        a = EATS[sid][0][0]
        opts = [NAME.get(a,str(a))] + [NAME.get(d,str(d)) for d in _distractors(sid, a, partners)]
        out['eats'] = {"question": "What is it known to eat?", "answer": NAME.get(a,str(a)),
                       "options": sorted(set(opts))}
    if eb:
        a = EB[sid][0][0]
        opts = [NAME.get(a,str(a))] + [NAME.get(d,str(d)) for d in _distractors(sid, a, partners)]
        out['eatenBy'] = {"question": "What is it known to be eaten by?", "answer": NAME.get(a,str(a)),
                          "options": sorted(set(opts))}
    return out or None
cards=[]
for sid, canon, cls, kingdom, levels in con.sql("SELECT species_id,canonicalName,class,kingdom,levels FROM catalog ORDER BY species_id").fetchall():
    trophic=FEED.get(sid)
    nm = NAME.get(sid) or canon or str(sid)
    # producers don't eat — clear any reversed/spurious "eats" edges (a plant
    # showing up as source of an 'eats' record is noise)
    eats=[] if trophic=='Producer' else [node(p,e) for p,e in EATS.get(sid,[])]
    eb  =[node(p,e) for p,e in EB.get(sid,[])]
    # "apex" is gone entirely (user, 2026-08-24): apex status is a property of a
    # local food web, not a species — even ecologists keep no such list (their
    # citable proxy, Ripple 2014, is a SIZE cutoff). We claim only what's recorded.
    role, falseRole = q2_framing(sid, trophic)
    og = ORIG.get(sid)
    og = og.title() if og else None       # 'ASIA-TEMPERATE' -> 'Asia-Temperate' (WCVP ships TDWG ALL-CAPS)
    # lists are evidence-sorted, so [0] is each direction's best-attested edge
    d = q4_dir(sid, trophic, eats[0]['evidence'] if eats else 0, eb[0]['evidence'] if eb else 0)
    q4pool = eats if d=='eats' else eb
    diet = DIET.get(sid, [])          # shown on the card as context; NEVER the Q4 answer
    q4_kind = 'species' if q4pool else 'none'
    q4_answer = q4pool[0]['name'] if q4pool else None
    slot5type = 'habitat' if sid in HAB else ('origin' if sid in ORIG else 'biome')
    feed_src, feed_conf = FEED_SRC.get(sid, (None, None))
    # provenance per field: source + confidence tier (measured | definitional |
    # inferred | derived) so the card's "source" popup is honest about what's
    # known vs guessed — the scientific-database principle.
    prov = {
      "taxonomy": {"source":"GBIF Backbone", "confidence":"measured"},
      "feeding":  {"source": feed_src, "confidence": feed_conf},
      "size":     {"source": SZ.get(sid,(None,))[0], "confidence":"measured"},
      "slot5":    {"source": (HAB.get(sid,(None,))[0] if slot5type=='habitat' else 'WCVP' if slot5type=='origin' else 'GBIF/GARD/PHYLACINE occurrences → RESOLVE ecoregions'),
                   "confidence": "measured" if slot5type in ('habitat','origin') else "derived"},
      "foodweb":  {"source":"GloBI", "confidence":"measured"},
      "lookAlikes": {"source":"GBIF taxonomy + RESOLVE ecoregions", "confidence":"inferred"},
    }
    cards.append({
      "id": slugify(nm), "species_id": sid, "name": nm, "sci": canon,
      "levels": levels+1,
      "group": (LIFE.get(sid) if GROUP.get(cls)=='Plant' else None) or GROUP.get(cls,cls), "trophic": trophic,
      "role": role, "falseRole": falseRole,                      # Q2 feeding-guild T/F
      "size": round_size(SZ.get(sid,(None,None))[1]), "habitat": HAB.get(sid,(None,None))[1],
      "origin": og, "biome": BIOME.get(sid),
      "slot5": HAB.get(sid,(None,None))[1] or og or BIOME.get(sid), "slot5type": slot5type,
      "foodweb": {"eats":eats, "eatenBy":eb},
      "q4": q4_lists(sid, trophic, eats, eb),                   # Q4: two option lists, 1 true + 2 distractors each
      "diet": [{"category":c,"share":f,"source":src} for c,f,src in diet],
      "climate": CLIM.get(sid),                                 # {tempC, precipMm} and/or {zone}
      "q3": q3_opponents(sid, cls),                       # Q3: on-average size comparison, 3-way
      "lookAlikes": [NAME.get(p,str(p)) for p in LA.get(sid,[])],
      "ecoregions": ECOS.get(sid, []),                          # top-60, for the ecoregion FILTER and range tiebreaks;
                                                                # the MAP fills from explorer/data/range (every ecoregion, graded)                           # range map: RESOLVE eco ids
      "provenance": prov,
    })
# TWO FILES (2026-10-05): Cloudflare Pages caps a file at 25 MiB and the catalog
# passed 29 MiB when BIEN + AusTraits added 4,500 plant cards. The Q3/Q4 quiz
# payloads (a third of the bytes) go to quiz.json — {id: {q3, q4}} — and the
# catalog is written minified. The site's boot() and the app's loadCatalog()
# fetch both and put q3/q4 back on the card, so every reader sees the old shape.
quiz = {c["id"]: {k: c.pop(k) for k in ("q3", "q4") if k in c} for c in cards}
json.dump(cards, open("catalog.json","w"), ensure_ascii=False, separators=(',',':'))
json.dump(quiz, open("quiz.json","w"), ensure_ascii=False, separators=(',',':'))
print(f"wrote catalog.json + quiz.json — {len(cards):,} cards ({time.time()-t0:.0f}s total)")

# ---- explorer sync: pipeline pool WITH resolved values (not just flags) --------
# [sci, class, mask(f16 sz8 fw4 s5_2 b1), feeding, size, habitat, origin, biome, top-edge]
import os as _os
if _os.path.isdir("../../explorer/data"):
    pool_biome = as_map("""SELECT se.species_id, arg_max(e.ECO_NAME, [se.occurrence_count, -se.ecoregion_id])
      FROM species_ecoregions se JOIN ecoregions e ON e.ECO_ID=se.ecoregion_id GROUP BY 1""")
    top_edge = {r[0]:(r[1],r[2]) for r in con.sql("""
      SELECT sid, verb, partner FROM (
        SELECT pred_sid sid, 'eats' verb, prey_sid partner,
               row_number() OVER (PARTITION BY pred_sid ORDER BY evidence DESC, prey_sid) rn FROM eats_ok
        UNION ALL
        SELECT prey_sid, 'eaten by', pred_sid,
               row_number() OVER (PARTITION BY prey_sid ORDER BY predation DESC, pred_sid) rn FROM edges WHERE predation>0)
      WHERE rn=1""").fetchall()}
    pool=[]
    for sid, canon, cls, f, s2, fw, s5, b in con.sql("""
        SELECT species_id, canonicalName, class, has_feeding, has_size, has_foodweb, has_slot5, has_biome
        FROM card_pool WHERE has_feeding+has_size+has_foodweb+has_slot5+has_biome >= 4
        ORDER BY canonicalName""").fetchall():
        og2 = ORIG.get(sid); og2 = og2.title() if og2 else None
        te = top_edge.get(sid)
        pool.append([canon, cls, f*16+s2*8+fw*4+s5*2+b,
                     FEED.get(sid), round_size(SZ.get(sid,(None,None))[1]),
                     HAB.get(sid,(None,None))[1], og2, pool_biome.get(sid),
                     f"{te[0]} {NAME.get(te[1],'?')}" if te else None])
    json.dump(pool, open("../../explorer/data/pool.json","w"), ensure_ascii=False, separators=(',',':'))
    import shutil; shutil.copy("catalog.json","../../explorer/data/catalog.json"); shutil.copy("quiz.json","../../explorer/data/quiz.json")
    print(f"explorer sync: pool.json {len(pool):,} candidates + catalog.json copied")
con.sql("SELECT s.kingdom, s.class, count(*) n FROM catalog s GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12").show()
print("look-alikes present on:", sum(1 for c in cards if c['lookAlikes']), "cards")
print("\n=== 3 sample cards ===")
for c in cards[:3]:
    print(f"\n{c['name']} ({c['sci']}) — {c['group']}/{c['trophic']}, size {c['size']}, habitat {c['habitat']}, origin {c['origin']}")
    print(f"  eats: {[n['name'] for n in c['foodweb']['eats']]}")
    print(f"  eaten by: {[n['name'] for n in c['foodweb']['eatenBy']]}   look-alikes: {c['lookAlikes']}")
con.close()
