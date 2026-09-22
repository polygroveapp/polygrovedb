# %% [markdown]
# # PolygroveDB — resolve names + extract field notes (step 2)
#
# Picks up from `01_build_substrate` (same `polygrove.duckdb`). Two parts:
#
# 1. **Name resolution** — match EOL/GloBI names onto the GBIF backbone so
#    coverage counts are *resolved species*, not raw name strings.
# 2. **Field notes** — read the Wikipedia `.bz2` the right way (Python `bz2` +
#    the multistream **index seek**, following redirects), extract cited
#    sentences with `mwparserfromhell`.
#
# **Prereqs:** `pip install duckdb mwparserfromhell pandas`. Note: the Wikipedia
# files are **bzip2** — Finder and DuckDB can't open them; only the code below
# (Python `bz2`) reads them.

# %%
import duckdb, bz2, re, html, os, subprocess
import pandas as pd
import mwparserfromhell as mw

DATA = "../../data"
SCRATCH = "../_scratch"; os.makedirs(SCRATCH, exist_ok=True)
con = duckdb.connect("../../polygrove.duckdb")
print("tables:", [r[0] for r in con.sql("SHOW TABLES").fetchall()])

# %% [markdown]
# ## Part 1 — Name resolution (the real coverage numbers)
# `01` reported *raw* name-string counts. Here we resolve onto `taxon`
# (accepted GBIF species) by canonical name, so the numbers mean "how many
# backbone species actually have this field."

# %%
# distinct lowercased names that carry each property (fast hash-join keys)
con.sql("""
CREATE OR REPLACE TEMP TABLE k_trophic AS
  SELECT DISTINCT lower(scientific_name) k FROM eol_traits WHERE lower(predicate) LIKE '%troph%';
CREATE OR REPLACE TEMP TABLE k_habitat AS
  SELECT DISTINCT lower(scientific_name) k FROM eol_traits WHERE lower(predicate) LIKE '%habitat%';
CREATE OR REPLACE TEMP TABLE k_globi AS
  SELECT DISTINCT lower(sourceTaxonName) k FROM interactions;
""")
con.sql("""
CREATE OR REPLACE TABLE species_coverage AS
SELECT s.taxonID, s.canonicalName, s.kingdom, s.class,
       (t.k IS NOT NULL) AS has_trophic,
       (h.k IS NOT NULL) AS has_habitat,
       (g.k IS NOT NULL) AS has_interaction
FROM (SELECT *, lower(canonicalName) nk FROM taxon) s
LEFT JOIN k_trophic t ON t.k = s.nk
LEFT JOIN k_habitat h ON h.k = s.nk
LEFT JOIN k_globi   g ON g.k = s.nk;
""")
con.sql("""
SELECT count(*) backbone_species,
       sum(has_trophic::int)     AS resolved_trophic,
       sum(has_habitat::int)     AS resolved_habitat,
       sum(has_interaction::int) AS resolved_interaction
FROM species_coverage
""").show()

# %% [markdown]
# Resolved coverage by taxonomic class (top classes) — the bias view.

# %%
con.sql("""
SELECT class,
       count(*) species,
       round(100.0*avg(has_trophic::int),1)     AS pct_trophic,
       round(100.0*avg(has_habitat::int),1)     AS pct_habitat,
       round(100.0*avg(has_interaction::int),1) AS pct_interaction
FROM species_coverage
WHERE class IS NOT NULL
GROUP BY class HAVING count(*) > 500
ORDER BY species DESC LIMIT 15
""").show()

# %% [markdown]
# ## Part 2 — Field notes from Wikipedia (index seek, redirect-aware)
# Build a `wiki_index` (title → byte offset) so we can (a) jump straight to any
# article's stream in the 25 GB dump and (b) resolve redirects. The index is
# bzip2; we decompress it once, load it, then delete the text.

# %%
if "wiki_index" not in [r[0] for r in con.sql("SHOW TABLES").fetchall()]:
    subprocess.run(f"bzip2 -dkc {DATA}/enwiki-multistream-index.txt.bz2 > {SCRATCH}/idx.txt",
                   shell=True, check=True)
    # each line is  offset:pageid:title  (title may contain ':'), so read whole
    # lines then split on the first two colons only.
    con.sql(f"""
    CREATE OR REPLACE TABLE wiki_index AS
    SELECT CAST(regexp_extract(line, '^([0-9]+):', 1) AS BIGINT)            AS byte_offset,
           CAST(regexp_extract(line, '^[0-9]+:([0-9]+):', 1) AS BIGINT)     AS page_id,
           regexp_replace(line, '^[0-9]+:[0-9]+:', '')                      AS title
    FROM read_csv('{SCRATCH}/idx.txt', columns={{'line':'VARCHAR'}},
                  delim='\x01', header=false, quote='');
    """)
    os.remove(f"{SCRATCH}/idx.txt")
con.sql("SELECT count(*) pages_in_index FROM wiki_index").show()

# %%
DUMP = f"{DATA}/enwiki-multistream.xml.bz2"
REF_RE = re.compile(r"<ref[^>]*>(.*?)</ref>", re.DOTALL | re.IGNORECASE)

def read_stream(offset):
    """Decompress the single multistream block at `offset` (~100 pages)."""
    with open(DUMP, "rb") as fh:
        fh.seek(offset)
        dec = bz2.BZ2Decompressor(); out = b""
        while not dec.eof:
            chunk = fh.read(1 << 20)
            if not chunk: break
            out += dec.decompress(chunk)
        return out.decode("utf-8", "replace")

def article_text(blob, title):
    for pm in re.finditer(r"<page>(.*?)</page>", blob, re.DOTALL):
        p = pm.group(1)
        tm = re.search(r"<title>(.*?)</title>", p, re.DOTALL)
        if tm and tm.group(1) == title:
            xm = re.search(r"<text[^>]*>(.*?)</text>", p, re.DOTALL)
            return html.unescape(xm.group(1)) if xm else ""
    return None

def offset_for(title):
    r = con.execute("SELECT byte_offset FROM wiki_index WHERE title = ? LIMIT 1", [title]).fetchone()
    return r[0] if r else None

def get_wikitext(title, hops=0):
    off = offset_for(title)
    if off is None: return None
    wt = article_text(read_stream(off), title)
    if wt is None: return None
    m = re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)", wt, re.IGNORECASE)   # follow redirects
    if m and hops < 2:
        tgt = m.group(1).strip()
        tgt = tgt[:1].upper() + tgt[1:]        # Wikipedia titles are first-letter-case-insensitive
        return get_wikitext(tgt, hops + 1)
    return wt

def field_notes(wt):
    out = []
    for para in re.split(r"\n\n+", wt or ""):
        if "<ref" not in para: continue                     # only cited paragraphs
        text = mw.parse(REF_RE.sub("", para)).strip_code()
        for s in re.split(r"(?<=[.!?])\s+", text):
            s = re.sub(r"\s+", " ", s).strip()
            if (10 <= len(s.split()) <= 45 and s[:1].isupper()
                    and "|" not in s and "=" not in s
                    and not s.startswith(("It ", "They ", "These ", "This species", "He ", "She "))):
                out.append(s)
    seen = set(); return [x for x in out if not (x in seen or seen.add(x))]

# %% [markdown]
# Demo run on a few species (mix of own-page and redirect cases). In production
# you'd feed the full eligible-species list here instead.

# %%
targets = ["Amanita muscaria", "Ariolimax columbianus", "Puma concolor",
           "Loxodonta africana", "Cyanocitta stelleri", "Welwitschia mirabilis"]
rows = []
for sp in targets:
    wt = get_wikitext(sp)
    fns = field_notes(wt)
    print(f"{sp:<24} {len(fns):>3} cited field notes" + ("" if wt else "   (no article)"))
    if fns: print("     e.g.", fns[0][:130])
    rows += [{"species": sp, "field_note": s} for s in fns]

df = pd.DataFrame(rows)
con.sql("CREATE OR REPLACE TABLE field_notes AS SELECT * FROM df")
con.sql("SELECT species, count(*) n_field_notes FROM field_notes GROUP BY 1 ORDER BY 2 DESC").show()

# %% [markdown]
# ## Next steps
# - **GBIF occurrences** — query the S3 Parquet in place (`httpfs`), spatial-join
#   to `ecoregions` → `species_ecoregions`.
# - **Scale field notes** — feed the eligible-species list into the loop above;
#   add Phase-4 citation-quality filtering + the discourse-marker cleanup.
# - **Trait crosswalk** — EOL terms / Wikidata Q-IDs → 5 buckets; ENVO → 29 labels.
# - **Audit cross-tab** — join everything, coverage per ecoregion / taxonomic group.

# %%
con.sql("SHOW TABLES").show()
con.close()
