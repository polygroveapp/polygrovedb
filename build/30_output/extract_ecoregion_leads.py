# %% [markdown]
# # PolygroveDB — one Wikipedia lead sentence per ecoregion (offline, from the dump)
# Same index-seek machinery as the species leads; titles are the RESOLVE ECO_NAMEs
# (redirects followed — e.g. "Mascarene forests" -> "Mascarene Islands").
# Output: data/ecoregion_leads.json {eco_id: {lead, lead2, title}} — app layer (CC-BY-SA).
# lead2 = the article's SECOND sentence (user, 2026-09-29: "have the ecoregion
# sentence be the second sentence on the wikipedia page") — the first is nearly
# always the definition ("X is a … ecoregion in …"), the second says something.
# ecology = the first sentence of the article's "Ecology" section, preferred
# over both when the article has one.

# %%
import duckdb, bz2, re, html, json, time
import mwparserfromhell as mw
DUMP="../../data/enwiki-multistream.xml.bz2"
_con=duckdb.connect(); _con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")
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
def get_wikitext(title,hops=0):
    r=_con.execute("SELECT byte_offset FROM wiki_index WHERE title=? LIMIT 1",[title]).fetchone()
    if not r: return None,None
    wt=article_text(read_stream(r[0]),title)
    if wt is None: return None,None
    m=re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)",wt,re.IGNORECASE)
    if m and hops<2:
        t=m.group(1).strip(); return get_wikitext(t[:1].upper()+t[1:],hops+1)
    return wt,title
from wiki_convert import render_converts   # {{convert}} ranges written out: 35–46 cm
def section_text(wt, names):
    """the wikitext under the first heading whose title is one of `names` (any level)"""
    for m in re.finditer(r"(?m)^(=+)\s*(.*?)\s*\1\s*$", wt):
        if m.group(2).strip().lower() in names:
            rest=wt[m.end():]
            nxt=re.search(r"(?m)^=+[^=\n].*?=+\s*$", rest)
            return rest[:nxt.start()] if nxt else rest
    return None
# Wikipedia's pointer lines written as plain text, not templates, so strip_code
# keeps them: "See Sierra Nevada for general information about the mountain
# range …" stood in for the Sierra Nevada forests description (2026-11-16)
HATNOTE=re.compile(r"(See\s.+\sfor\s|For\s.+,\s*see\s|Further information|Main article|This article is about|Not to be confused)", re.IGNORECASE)
# abbreviations are not sentence ends: "located in the U.S. state of California"
# was cut to "The ecology of the Sierra Nevada, located in the U.S." (2026-11-16)
ABBREV=re.compile(r"\b(U\.S|U\.K|U\.N|e\.g|i\.e|St|Mt|Ft|Pt|approx|ca|c|No|Dr|vs|var|subsp|spp|sp)\.")
def split_sentences(text):
    """split on . ! ? without breaking after an abbreviation; § stands in for its dots"""
    safe=ABBREV.sub(lambda m: m.group(0).replace(".", "\u00a7"), text.strip())
    return re.split(r"(?<=[.!?])\s+", safe)
def clean_sentences(body, n):
    body=render_converts(body)
    body=re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>","",body,flags=re.DOTALL)
    body=re.sub(r"(?m)^\s*\[\[(File|Image):[^\n]*$","",body)
    text=mw.parse(body).strip_code()
    out=[]
    for s in split_sentences(text):
        s=re.sub(r"\s+"," ",s).strip().replace("\u00a7",".")
        s=re.sub(r"\(\s*[;,]\s*","(",s); s=re.sub(r"\(\s*\)","",s)
        if len(s.split())<6 or not s[:1].isupper(): continue
        if "|" in s or "{" in s or "}" in s or s.lower().startswith(("thumb","main article","see also")): continue
        if HATNOTE.match(s): continue
        out.append(s)
        if len(out)>=n: break
    return out
def ecology_sentence(wt):
    """the first sentence of the article's Ecology section, when it has one
    (user, 2026-09-29: "if they have an ecology tab use that sentence")"""
    if not wt: return None
    sec=section_text(wt, {"ecology"})
    ss=clean_sentences(sec,1) if sec else []
    return ss[0] if ss else None
def lead_sentences(wt, n=2):
    """the first n clean sentences of the article's lead section"""
    if not wt: return []
    body=re.split(r"(?m)^=+",wt)[0]; body=render_converts(body)
    body=re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>","",body,flags=re.DOTALL)
    text=mw.parse(body).strip_code()
    out=[]
    for s in split_sentences(text):
        s=re.sub(r"\s+"," ",s).strip().replace("\u00a7",".")
        s=re.sub(r"\(\s*[;,]\s*","(",s); s=re.sub(r"\(\s*\)","",s)
        if len(s.split())<6 or not s[:1].isupper(): continue
        if "|" in s or "{" in s or "}" in s: continue
        if HATNOTE.match(s): continue
        out.append(s)
        if len(out)>=n: break
    return out
ecos=_con.sql("SELECT ECO_ID, ECO_NAME FROM pg.ecoregions WHERE ECO_NAME IS NOT NULL ORDER BY ECO_ID").fetchall()
out={}; t0=time.time()
for i,(eid,name) in enumerate(ecos):
    wt,resolved=get_wikitext(name)
    ss=lead_sentences(wt) if wt else []
    if ss:
        out[str(eid)]={"lead":ss[0],"title":resolved}
        if len(ss)>1: out[str(eid)]["lead2"]=ss[1]
        eco_s=ecology_sentence(wt)
        if eco_s: out[str(eid)]["ecology"]=eco_s
    if (i+1)%150==0: print(f"  {i+1}/{len(ecos)} · {len(out)} with leads · {(time.time()-t0)/60:.1f}m", flush=True)
json.dump(out, open("../../data/ecoregion_leads.json","w"))
print(f"DONE: {len(out)}/{len(ecos)} ecoregions have a lead sentence, {sum(1 for v in out.values() if 'lead2' in v)} a second, {sum(1 for v in out.values() if 'ecology' in v)} an Ecology sentence  ({(time.time()-t0)/60:.1f}m)", flush=True)
