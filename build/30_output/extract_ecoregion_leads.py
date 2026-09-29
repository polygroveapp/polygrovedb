# %% [markdown]
# # PolygroveDB — one Wikipedia lead sentence per ecoregion (offline, from the dump)
# Same index-seek machinery as the species leads; titles are the RESOLVE ECO_NAMEs
# (redirects followed — e.g. "Mascarene forests" -> "Mascarene Islands").
# Output: data/ecoregion_leads.json {eco_id: {lead, lead2, title}} — app layer (CC-BY-SA).
# lead2 = the article's SECOND sentence (user, 2026-09-29: "have the ecoregion
# sentence be the second sentence on the wikipedia page") — the first is nearly
# always the definition ("X is a … ecoregion in …"), the second says something.

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
CONVERT_RE=re.compile(r"\{\{(?:convert|cvt)\s*\|\s*([^|}]+)\s*\|\s*([^|}]+)[^}]*\}\}", re.I)
def lead_sentences(wt, n=2):
    """the first n clean sentences of the article's lead section"""
    if not wt: return []
    body=re.split(r"(?m)^=+",wt)[0]; body=CONVERT_RE.sub(r"\1 \2",body)
    body=re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>","",body,flags=re.DOTALL)
    text=mw.parse(body).strip_code()
    out=[]
    for s in re.split(r"(?<=[.!?])\s+",text.strip()):
        s=re.sub(r"\s+"," ",s).strip()
        s=re.sub(r"\(\s*[;,]\s*","(",s); s=re.sub(r"\(\s*\)","",s)
        if len(s.split())<6 or not s[:1].isupper(): continue
        if "|" in s or "{" in s or "}" in s: continue
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
    if (i+1)%150==0: print(f"  {i+1}/{len(ecos)} · {len(out)} with leads · {(time.time()-t0)/60:.1f}m", flush=True)
json.dump(out, open("../../data/ecoregion_leads.json","w"))
print(f"DONE: {len(out)}/{len(ecos)} ecoregions have a lead sentence, {sum(1 for v in out.values() if 'lead2' in v)} a second  ({(time.time()-t0)/60:.1f}m)", flush=True)
