# %% [markdown]
# # PolygroveDB — field-note cleanup (step 8)
#
# The raw field notes (step 2) had visible problems: section headings glued to
# sentences (`"Genetics In July 2021…"`), measurements stripped by `{{convert}}`
# removal (`"the stipe is white, high by wide"`), and tone-inappropriate content.
# This re-extracts the demo species with a cleaner pipeline:
#
# 1. **Strip section headings** before sentence-splitting.
# 2. **Preserve `{{convert}}` measurements** (pull the value+unit before stripping).
# 3. **Tone filter** — drop clearly inappropriate sentences (sexual violence,
#    gore) that citation-quality filtering doesn't catch.
#
# (Off-topic sentences — e.g. the Captain Cook line — are semantic and left for a
# later pass; the point of a *pool* is the card selects good ones from it.)

# %%
import duckdb, bz2, re, html
import pandas as pd
import mwparserfromhell as mw
con = duckdb.connect("../../polygrove.duckdb")
DUMP = "../../data/enwiki-multistream.xml.bz2"
REF_RE  = re.compile(r"<ref[^>]*>(.*?)</ref>", re.DOTALL | re.IGNORECASE)

# --- new cleanup regexes ---
HEADING_RE = re.compile(r"(?m)^=+\s*.+?\s*=+\s*$")                     # == Section ==
import sys; sys.path.insert(0, "../30_output")
from wiki_convert import render_converts                                  # {{convert}} ranges written out: 35–46 cm
TONE_BLOCK = re.compile(r"\b(rap(e|es|ed|ing)|molest|mutilat|disembowel|dismember|slaughter)\w*", re.I)

# --- seek helpers (same mechanism as step 2) ---
def read_stream(off):
    with open(DUMP,"rb") as fh:
        fh.seek(off); dec=bz2.BZ2Decompressor(); out=b""
        while not dec.eof:
            c=fh.read(1<<20)
            if not c: break
            out+=dec.decompress(c)
        return out.decode("utf-8","replace")
def article_text(blob,title):
    for pm in re.finditer(r"<page>(.*?)</page>",blob,re.DOTALL):
        p=pm.group(1); tm=re.search(r"<title>(.*?)</title>",p,re.DOTALL)
        if tm and tm.group(1)==title:
            xm=re.search(r"<text[^>]*>(.*?)</text>",p,re.DOTALL)
            return html.unescape(xm.group(1)) if xm else ""
    return None
def offset_for(title):
    r=con.execute("SELECT byte_offset FROM wiki_index WHERE title=? LIMIT 1",[title]).fetchone()
    return r[0] if r else None
def get_wikitext(title,hops=0):
    off=offset_for(title)
    if off is None: return None
    wt=article_text(read_stream(off),title)
    if wt is None: return None
    m=re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)",wt,re.IGNORECASE)
    if m and hops<2:
        t=m.group(1).strip(); return get_wikitext(t[:1].upper()+t[1:],hops+1)
    return wt

# --- improved extraction ---
def field_notes(wt):
    wt = HEADING_RE.sub("", wt or "")          # 1. drop section headings
    wt = render_converts(wt)                   # 2. preserve measurements (ranges too)
    out=[]
    for para in re.split(r"\n\n+", wt):
        if "<ref" not in para: continue
        text = mw.parse(REF_RE.sub("", para)).strip_code()
        for s in re.split(r"(?<=[.!?])\s+", text):
            s=re.sub(r"\s+"," ",s).strip()
            if not (10<=len(s.split())<=45 and s[:1].isupper()): continue
            if "|" in s or "=" in s: continue
            if s.startswith(("It ","They ","These ","This species","He ","She ")): continue
            if TONE_BLOCK.search(s): continue    # 3. tone filter
            out.append(s)
    seen=set(); return [x for x in out if not (x in seen or seen.add(x))]

# %% [markdown]
# ## Re-extract the demo species and rebuild field_notes + facts

# %%
targets=["Amanita muscaria","Ariolimax columbianus","Puma concolor",
         "Loxodonta africana","Cyanocitta stelleri","Welwitschia mirabilis"]
rows=[]
for sp in targets:
    fns=field_notes(get_wikitext(sp))
    rows += [{"species":sp,"field_note":s} for s in fns]
    print(f"{sp:<24} {len(fns):>3} field notes")
df=pd.DataFrame(rows)
con.sql("CREATE OR REPLACE TABLE field_notes AS SELECT * FROM df")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("""CREATE OR REPLACE TABLE facts AS
  SELECT DISTINCT gn.accepted_id AS species_id, f.field_note AS sentence,
         'sourced' AS provenance, 'wikipedia' AS source_type
  FROM field_notes f JOIN gbif_names gn ON gn.norm_name = norm(f.species)
  JOIN species s ON s.species_id = gn.accepted_id;""")
con.sql("SELECT count(*) AS facts_rows, count(DISTINCT species_id) AS sp FROM facts").show()

# %% [markdown]
# ## Did the fixes land? (the previously-broken cases)

# %%
def show(sp, needle):
    r=con.execute("""SELECT DISTINCT sentence FROM facts f JOIN species s ON s.species_id=f.species_id
        WHERE s.canonicalName=? AND sentence ILIKE ? LIMIT 2""",[sp,f"%{needle}%"]).fetchall()
    for (s,) in r: print(f"  ✓ {s[:150]}")
    if not r: print("  (no match)")
print("measurements preserved (Amanita stipe / Welwitschia temp):")
show("Amanita muscaria","stipe"); show("Welwitschia mirabilis","temperature")
print("\nheadings gone (should read as clean sentences):")
show("Cyanocitta stelleri","formally described"); show("Welwitschia mirabilis","genome")
print("\ntone filter (elephant grim line should be ABSENT):")
show("Loxodonta africana","rhinoceros")

# %%
con.close()
