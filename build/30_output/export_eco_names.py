# %% [markdown]
# # PolygroveDB — LOCAL names per ecoregion (2026-09-26)
#
# "If you find a cougar in one ecoregion it should be called the local name
# for a cougar there so the card is unique." Each ecoregion is mapped to the
# countries it covers (Natural Earth admin-0 overlap, DuckDB spatial), the
# countries to a dominant language, and every card species gets its
# best-attested GBIF vernacular in that language — Suçuarana in the Atlantic
# Forest, Puma in the Andes, Cougar in Colorado.
#
# What the data can and can't do: GBIF's country tags are checklist artifacts
# (every US cougar name comes from ONE Vermont list), so regional English
# dialects (catamount vs mountain lion) are NOT recoverable — English-speaking
# ecoregions keep the default English name. Language IS reliable, so v1 is
# language-level, Latin-script only (the card font has no CJK/Cyrillic glyphs).
#
# Output: explorer/data/eco_names/<eid>.json = {"lang": "pt", "names": {sid: name}}
# holding only the overrides (local ≠ default), plus eco_meta[eid].lang.

# %%
import duckdb, json, os, re, time
t0 = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DATA = os.path.join(ROOT, 'explorer', 'data')
OUT = os.path.join(DATA, 'eco_names')

# ── country → dominant language (Latin-script languages GBIF actually covers).
# Anything not listed (English-speaking, or non-Latin script: ru/zh/ja/ar/…)
# keeps the default English card name.
LANG = {}
def L(lang, *isos):
    for i in isos: LANG[i] = lang
L('es', 'ES','MX','AR','CL','CO','PE','VE','EC','BO','PY','UY','GT','HN','SV','NI','CR','PA','CU','DO','GQ')
L('pt', 'BR','PT','AO','MZ','GW','CV','ST','TL')
L('fr', 'FR','SN','ML','BF','NE','TD','CI','GN','TG','BJ','GA','CG','CD','CF','CM','MG','DJ','BI','KM','HT','MC','LU','NC','PF')
L('de', 'DE','AT','CH','LI')
L('nl', 'NL','BE','SR')
L('it', 'IT','SM')
L('sv', 'SE')
L('da', 'DK','GL')
L('fo', 'FO')
L('no', 'NO')
L('fi', 'FI')
L('is', 'IS')
L('et', 'EE')
L('lv', 'LV')
L('lt', 'LT')
L('pl', 'PL')
L('cs', 'CZ')
L('sk', 'SK')
L('hu', 'HU')
L('sl', 'SI')
L('hr', 'HR','BA','ME')
L('ro', 'RO','MD')
L('tr', 'TR')
L('ca', 'AD')
L('id', 'ID')
L('ms', 'MY','BN')
L('vi', 'VN')
L('sw', 'TZ')
# English-speaking countries count AGAINST a local language in the plurality —
# the Sonoran (US 54% / MX 46%) stays English
L('en', 'US','CA','GB','IE','AU','NZ','ZA','NG','GH','KE','UG','ZM','ZW','BW','NA','MW','LR','SL','GM','IN','PK','PH','SG','JM','TT','BZ','GY','PG','FJ','SS','LK','BD')
# sub-national overrides (Natural Earth admin-1 iso_3166_2)
LANG1 = {'CA-QC': 'fr', 'US-PR': 'es'}
# GBIF language codes that mean the same card language
ALIAS = {'nb': 'no', 'nn': 'no'}

con = duckdb.connect()
con.sql("INSTALL spatial; LOAD spatial;")

# %% ── ecoregion → language: area-share overlap with countries (+ admin-1 overrides)
con.sql(f"CREATE TABLE eco AS SELECT eco, name, st_makevalid(geom) geom FROM st_read('{DATA}/ecoregions.geojson')")
# Natural Earth codes France and Norway as ISO_A2 '-99' — ISO_A2_EH carries the
# real codes (N. Cyprus / Somaliland / Kosovo stay -99 and are dropped)
con.sql(f"""CREATE TABLE c0 AS
  SELECT coalesce(nullif(ISO_A2, '-99'), ISO_A2_EH) iso, st_makevalid(geom) geom
  FROM st_read('{ROOT}/data/ne_110m_admin_0.geojson')
  WHERE coalesce(nullif(ISO_A2, '-99'), ISO_A2_EH) <> '-99'""")
con.sql(f"CREATE TABLE c1 AS SELECT iso_3166_2 code, st_makevalid(geom) geom FROM st_read('{ROOT}/data/ne_50m_admin_1.geojson') WHERE iso_3166_2 IN {tuple(LANG1)}")
con.sql("""CREATE TABLE ov AS
  SELECT e.eco, c.iso, st_area(st_intersection(e.geom, c.geom)) a
  FROM eco e JOIN c0 c ON st_intersects(e.geom, c.geom)""")
con.sql("""CREATE TABLE ov1 AS
  SELECT e.eco, c.code, st_area(st_intersection(e.geom, c.geom)) a
  FROM eco e JOIN c1 c ON st_intersects(e.geom, c.geom)""")
# islands too small for 110m countries: nearest country by centroid
con.sql("""CREATE TABLE nearest AS
  SELECT e.eco, arg_min(c.iso, st_distance(st_centroid(e.geom), c.geom)) iso
  FROM eco e, c0 c WHERE e.eco NOT IN (SELECT eco FROM ov) GROUP BY e.eco""")

shares = {}
for eco, iso, a in con.sql("SELECT eco, iso, a FROM ov").fetchall():
    shares.setdefault(eco, {})[iso] = shares.get(eco, {}).get(iso, 0) + a
for eco, iso in con.sql("SELECT eco, iso FROM nearest").fetchall():
    shares[eco] = {iso: 1.0}
sub = {}
for eco, code, a in con.sql("SELECT eco, code, a FROM ov1").fetchall():
    sub.setdefault(eco, {})[code] = a

eco_lang = {}
for eco, byiso in shares.items():
    total = sum(byiso.values()) or 1
    # language shares: an admin-1 override moves its area to the override language
    ls = {}
    for iso, a in byiso.items():
        lang = LANG.get(iso)
        if lang: ls[lang] = ls.get(lang, 0) + a
    for code, a in sub.get(eco, {}).items():
        ls[LANG1[code]] = ls.get(LANG1[code], 0) + a
        parent = LANG.get(code[:2])
        if parent: ls[parent] = max(0, ls.get(parent, 0) - a)
    if not ls: continue
    # plurality language with at least 35% of the area — multi-country
    # ecoregions (Western European broadleaf: DE 40 / FR 38 / CZ 11) still get a
    # local language; English or a non-Latin script (unlisted) = no override
    lang, a = max(ls.items(), key=lambda x: x[1])
    if lang != 'en' and a / total >= 0.35: eco_lang[eco] = lang
print(f"ecoregions with a local language: {len(eco_lang)} / {len(shares)}  ({time.time()-t0:.0f}s)")

# %% ── best-attested clean name per (species, language)
cards = json.load(open(f'{DATA}/catalog.json'))
default = {c['species_id']: c['name'] for c in cards}
sci = {c['species_id']: c['sci'].lower() for c in cards}
con.sql("CREATE TABLE cat AS SELECT unnest(?) sid", params=[list(default)])
con.sql(f"""CREATE TABLE v AS
  SELECT try_cast(taxonID AS BIGINT) sid, trim(vernacularName) n, language lang, source src
  FROM read_csv('{ROOT}/data/backbone/VernacularName.tsv', delim='\t', header=true, quote='', ignore_errors=true, all_varchar=true)""")
langs = sorted(set(eco_lang.values()))
con.sql("CREATE TABLE lv AS SELECT DISTINCT sid, n, lang, src FROM v JOIN cat USING (sid) WHERE n IS NOT NULL AND lang IS NOT NULL")
rows = con.sql("SELECT sid, n, lang, count(DISTINCT src) srcs FROM lv GROUP BY 1,2,3").fetchall()

CLEAN = re.compile(r"^[^\d,;:/()\[\]\"«»]{3,40}$")
best = {}   # (sid, lang) → (score, name)
for sid, n, lang, srcs in rows:
    lang = ALIAS.get(lang, lang)
    if lang not in langs or not CLEAN.match(n) or n.lower() == sci.get(sid): continue
    name = n[0].upper() + n[1:]     # first letter only — natives don't Title Case
    key = (sid, lang)
    score = (srcs, -len(name), name)   # most attested, then shortest, then stable
    if key not in best or score > best[key][0]: best[key] = (score, name)
print(f"(species, language) names: {len(best)}  ({time.time()-t0:.0f}s)")

# %% ── per-ecoregion override files (only where local ≠ default)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT): os.remove(os.path.join(OUT, f))
n_files = n_pairs = n_over = 0
for eco, lang in eco_lang.items():
    names = {}
    for c in cards:
        if eco not in (c.get('ecoregions') or []): continue
        n_pairs += 1
        b = best.get((c['species_id'], lang))
        if b and b[1].lower() != default[c['species_id']].lower():
            names[c['species_id']] = b[1]
    if not names: continue
    n_over += len(names); n_files += 1
    with open(f'{OUT}/{eco}.json', 'w') as fh:
        json.dump({'lang': lang, 'names': names}, fh, ensure_ascii=False, separators=(',', ':'))

meta_path = f'{DATA}/eco_meta.json'
meta = json.load(open(meta_path))
for eid, m in meta.items():
    m.pop('lang', None)
    if int(eid) in eco_lang: m['lang'] = eco_lang[int(eid)]
json.dump(meta, open(meta_path, 'w'), ensure_ascii=False, separators=(',', ':'))
print(f"eco_names: {n_files} files, {n_over:,} local names over {n_pairs:,} (species, ecoregion) pairs in named ecoregions  ({time.time()-t0:.0f}s)")

# %% iconic sanity — the cougar around the world
puma = next(c for c in cards if c['sci'] == 'Puma concolor')
for lang in ['es', 'pt', 'fr', 'de']:
    print(f"  Puma concolor [{lang}] -> {best.get((puma['species_id'], lang), (None, '(none)'))[1]}")
