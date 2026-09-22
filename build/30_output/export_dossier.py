# %% [markdown]
# # PolygroveDB — full per-species dossier export for the explorer
#
# "Every fact the database knows about a species": all trait tables unpivoted to
# long format (source · fact · value), every GloBI interaction TYPE both
# directions (not just the card's eats/eaten-by), habitats, origins, ecoregion
# summary, common names, field notes. Restricted to the >=3-question pool (57k
# species), sharded by hash(sci)%256 into explorer/data/dossier/NNN.json so the
# static site fetches one small file per species. Read-only on the DB.

# %%
import duckdb, json, os, time
from collections import defaultdict
t0=time.time()
con = duckdb.connect()
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")
con.sql(r"""CREATE OR REPLACE TEMP MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""CREATE TEMP TABLE pool_sids AS SELECT species_id FROM card_pool
  WHERE has_feeding+has_size+has_foodweb+has_slot5+has_biome >= 3;""")

# %% -- long-format facts from every trait table (class-gated where collisions can occur)
con.sql("""
CREATE TEMP TABLE dossier AS
SELECT species_id sid, src, fact, val FROM (
  SELECT species_id, 'AVONET' src, 'diet niche' fact, niche val FROM bird_traits WHERE niche IS NOT NULL
  UNION ALL SELECT species_id,'AVONET','trophic level',trophic_level FROM bird_traits WHERE trophic_level IS NOT NULL
  UNION ALL SELECT species_id,'AVONET','lifestyle',lifestyle FROM bird_traits WHERE lifestyle IS NOT NULL
  UNION ALL SELECT species_id,'AVONET','habitat',habitat FROM bird_traits WHERE habitat IS NOT NULL
  UNION ALL SELECT species_id,'AVONET','body mass',round(mass,1)::varchar||' g' FROM bird_traits WHERE mass>0
  UNION ALL SELECT n.species_id,'EltonTraits','diet niche',m.niche FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) WHERE m.niche IS NOT NULL
  UNION ALL SELECT n.species_id,'EltonTraits','lifestyle',m.lifestyle FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) WHERE m.lifestyle IS NOT NULL
  UNION ALL SELECT n.species_id,'EltonTraits','body mass',round(m.mass,1)::varchar||' g' FROM mammal_traits m JOIN name2sid n ON n.norm_name=norm(m.sciname) WHERE m.mass>0
  UNION ALL SELECT species_id,'ReptTraits','diet niche',niche FROM reptile_traits WHERE niche IS NOT NULL
  UNION ALL SELECT species_id,'ReptTraits','microhabitat',microhabitat FROM reptile_traits WHERE microhabitat IS NOT NULL
  UNION ALL SELECT species_id,'ReptTraits','habitat',habitat FROM reptile_traits WHERE habitat IS NOT NULL AND habitat<>'None'
  UNION ALL SELECT species_id,'ReptTraits','active time',active_time FROM reptile_traits WHERE active_time IS NOT NULL
  UNION ALL SELECT species_id,'ReptTraits','body mass',round(mass_g,1)::varchar||' g' FROM reptile_traits WHERE mass_g>0
  UNION ALL SELECT species_id,'ReptTraits','max total length',round(max_tl_mm)::varchar||' mm' FROM reptile_traits WHERE max_tl_mm>0
  UNION ALL SELECT species_id,'AmphiBIO','diet niche',niche FROM amphibian_traits WHERE niche IS NOT NULL
  UNION ALL SELECT species_id,'AmphiBIO','lifestyle',lifestyle FROM amphibian_traits WHERE lifestyle IS NOT NULL
  UNION ALL SELECT species_id,'AmphiBIO','habitat',habitat FROM amphibian_traits WHERE habitat IS NOT NULL
  UNION ALL SELECT species_id,'AmphiBIO','body size',round(body_size_mm,1)::varchar||' mm' FROM amphibian_traits WHERE body_size_mm>0
  UNION ALL SELECT t.species_id,'TetrapodTraits','body size',t.size_val FROM tetrapod_traits t JOIN species s ON s.species_id=t.species_id
    AND ((t.class='Aves' AND s.class='Aves') OR (t.class='Mammalia' AND s.class='Mammalia') OR (t.class='Amphibia' AND s.class='Amphibia')
      OR (t.class='Reptilia' AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia'))) WHERE t.size_val IS NOT NULL
  UNION ALL SELECT t.species_id,'TetrapodTraits','diet guild',t.niche FROM tetrapod_traits t JOIN species s ON s.species_id=t.species_id
    AND ((t.class='Aves' AND s.class='Aves') OR (t.class='Mammalia' AND s.class='Mammalia') OR (t.class='Amphibia' AND s.class='Amphibia')
      OR (t.class='Reptilia' AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia'))) WHERE t.niche IS NOT NULL
  UNION ALL SELECT t.species_id,'TetrapodTraits','vertical stratum',t.habitat FROM tetrapod_traits t JOIN species s ON s.species_id=t.species_id
    AND ((t.class='Aves' AND s.class='Aves') OR (t.class='Mammalia' AND s.class='Mammalia') OR (t.class='Amphibia' AND s.class='Amphibia')
      OR (t.class='Reptilia' AND s.class IN ('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia'))) WHERE t.habitat IS NOT NULL
  UNION ALL SELECT species_id,'LepTraits','wingspan',wingspan_mm::varchar||' mm' FROM lep_traits WHERE wingspan_mm>0
  UNION ALL SELECT species_id,'LepTraits','recorded hostplant families',hostplant_fams::varchar FROM lep_traits WHERE hostplant_fams>0
  UNION ALL SELECT species_id,'World Spider Traits','body length',body_mm::varchar||' mm' FROM spider_traits
  UNION ALL SELECT species_id,'Odonate Phenotypic DB','body length',body_mm::varchar||' mm' FROM odonate_traits
  UNION ALL SELECT species_id,'AnimalTraits','body mass',mass_g::varchar||' g' FROM animaltraits_size
  UNION ALL SELECT species_id,'EOL TraitBank','height',round(height,1)::varchar||' '||coalesce(units,'cm') FROM plant_fungi_size
  UNION ALL SELECT species_id,'EOL/'||source,'habitat label',habitat_raw FROM species_habitats WHERE habitat_raw IS NOT NULL
  UNION ALL SELECT species_id,'WCVP','native to',native_continent FROM species_native_origin
  UNION ALL SELECT species_id, CASE source WHEN 'taxonomy' THEN 'Taxonomy floor' ELSE 'EOL TraitBank' END,'trophic role',role FROM species_trophic_roles
  UNION ALL SELECT species_id,'GloBI (derived)','diet guild from prey',niche FROM globi_feeding
  UNION ALL SELECT species_id,'GBIF vernacular','common name',common_name FROM species_common_names
  UNION ALL SELECT species_id,'Wikipedia extracts (sourced)','candidate field note',sentence FROM facts WHERE sentence IS NOT NULL
) WHERE species_id IN (SELECT species_id FROM pool_sids);""")
print("trait rows:", con.sql("SELECT count(*) FROM dossier").fetchone()[0], f"({time.time()-t0:.0f}s)", flush=True)

# %% -- ecoregion summary + ALL GloBI interaction types, both directions
con.sql("""
INSERT INTO dossier
SELECT se.species_id sid,'RESOLVE ecoregions' src,'range' fact,
  count(*)::varchar||' ecoregions; primary: '||arg_max(e.ECO_NAME, se.occurrence_count) val
FROM species_ecoregions se JOIN ecoregions e ON e.ECO_ID=se.ecoregion_id
WHERE se.species_id IN (SELECT species_id FROM pool_sids) GROUP BY 1;""")

con.sql("""
CREATE TEMP TABLE inter AS
WITH e AS (
  SELECT ns.species_id a, nt.species_id b, i.interactionTypeName t
  FROM interactions i
  JOIN name2sid ns ON ns.norm_name=norm(i.sourceTaxonName)
  JOIN name2sid nt ON nt.norm_name=norm(i.targetTaxonName)
  WHERE ns.species_id<>nt.species_id),
g AS (
  SELECT a sid, t, 'of' dir, b p, count(*) n FROM e WHERE a IN (SELECT species_id FROM pool_sids) GROUP BY 1,2,3,4
  UNION ALL
  SELECT b, t, 'by', a, count(*) FROM e WHERE b IN (SELECT species_id FROM pool_sids) GROUP BY 1,2,3,4),
r AS (SELECT *, row_number() OVER (PARTITION BY sid,t,dir ORDER BY n DESC) rn,
        sum(n) OVER (PARTITION BY sid,t,dir) tot, count(*) OVER (PARTITION BY sid,t,dir) np FROM g)
SELECT r.sid, 'GloBI' src,
  r.t || CASE r.dir WHEN 'by' THEN ' (as target)' ELSE '' END
      || ' — ' || any_value(r.np)::varchar || ' partners, ' || any_value(r.tot)::varchar || ' records' AS fact,
  'top: ' || string_agg(coalesce(cn.common_name, s.canonicalName), ', ' ORDER BY r.rn) AS val
FROM r JOIN species s ON s.species_id=r.p
LEFT JOIN species_common_names cn ON cn.species_id=r.p
WHERE r.rn<=3 GROUP BY r.sid, r.t, r.dir;""")
con.sql("INSERT INTO dossier SELECT sid, src, fact, val FROM inter;")
print("dossier total rows:", con.sql("SELECT count(*) FROM dossier").fetchone()[0], f"({time.time()-t0:.0f}s)", flush=True)

# %% -- shard by hash(canonicalName) % 256  (djb2, mirrored in the explorer JS)
def djb2(s):
    h=5381
    for ch in s: h=((h*33)+ord(ch))&0xffffffff
    return h%256
rows=con.sql("""SELECT s.canonicalName, d.src, d.fact, d.val FROM dossier d
  JOIN species s ON s.species_id=d.sid
  WHERE s.canonicalName IS NOT NULL
  ORDER BY s.canonicalName, d.src, d.fact""").fetchall()
shards=defaultdict(dict)
for sci,src,fact,val in rows:
    shards[djb2(sci)].setdefault(sci,[]).append([src,fact,val])
outdir="../../explorer/data/dossier"; os.makedirs(outdir, exist_ok=True)
# app-layer field-note candidates (CC-BY-SA text never enters the DB): merge from the
# extraction output so a re-export never wipes them
if os.path.exists("../../data/wiki_fame.json"):
    for r in json.load(open("../../data/wiki_fame.json")):
        sci, notes = r[1], r[6]
        if notes: shards[djb2(sci)].setdefault(sci,[]).extend(['Wikipedia extracts (sourced)','candidate field note',n] for n in notes)
# the guaranteed baseline: the article's LEAD sentence (species-level, or the genus
# article's when no species page exists — 1,036 cards had NO text before this)
if os.path.exists("../../data/wiki_lead.json"):
    # sid->sci from the CATALOG, not wiki_fame.json — the fame cache lags a deck
    # change (the 2026-09-09 fish cards had leads extracted but silently skipped here)
    sid2sci={str(sid):sci for sid,sci in con.sql("SELECT species_id, canonicalName FROM catalog").fetchall()}
    import re as _re
    def _tidy(t):
        # husks left by stripped templates: "The cougar ( ; Puma concolor)" -> "(Puma concolor)"
        t=_re.sub(r"\(\s*[;,·]\s*", "(", t); t=_re.sub(r"\(\s*\)", "", t)
        t=_re.sub(r"\s+([,.;])", r"\1", t); return _re.sub(r"\s{2,}", " ", t).strip()
    for sid, d in json.load(open("../../data/wiki_lead.json")).items():
        sci=sid2sci.get(sid)
        if not sci: continue
        d={**d, 'lead': _tidy(d['lead'])}
        label='lead sentence' if d['level']=='species' else 'lead sentence (genus article)'
        shards[djb2(sci)].setdefault(sci,[]).insert(0, ['Wikipedia extracts (sourced)', label, d['lead']])
for sh,data in shards.items():
    json.dump(data, open(f"{outdir}/{sh}.json","w"), ensure_ascii=False, separators=(',',':'))
print(f"wrote {len(shards)} shards, {len(rows):,} facts, {sum(len(v) for v in shards.values()):,} species  ({time.time()-t0:.0f}s)")
con.close()
