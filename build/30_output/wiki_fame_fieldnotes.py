# %% [markdown]
# # PolygroveDB — Wikipedia "fame" + field-note candidates for every deck card
#
# "Most known" ≠ "most observed". Observation counts (species_popularity) reward
# birder volume; cultural salience is better proxied by how much Wikipedia says
# about a species — the count of CITED sentences its article yields (user rule).
# Index-seek into the local 25GB dump for each deck species (sci name, falling
# back to its common name; redirects followed), computing fame AND producing the
# field-note candidates (app-layer dossier shards, never the DB). Parallel workers.
# Output: data/wiki_fame.json  → species_fame table is built from it afterwards.

import duckdb, bz2, re, html, json, os, sys, time
from multiprocessing import Pool
import mwparserfromhell as mw

DATA="../../data"; DUMP=f"{DATA}/enwiki-multistream.xml.bz2"
REF_RE=re.compile(r"<ref[^>]*>(.*?)</ref>", re.DOTALL|re.IGNORECASE)
HEADING_RE=re.compile(r"(?m)^=+\s*.+?\s*=+\s*$")
CONVERT_RE=re.compile(r"\{\{(?:convert|cvt)\s*\|\s*([^|}]+)\s*\|\s*([^|}]+)[^}]*\}\}", re.I)
TONE_BLOCK=re.compile(r"\b(rap(e|es|ed|ing)|molest|mutilat|disembowel|dismember|slaughter)\w*", re.I)
_con=None
def con():
    global _con
    if _con is None:
        _con=duckdb.connect(); _con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")
    return _con
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
    r=con().execute("SELECT byte_offset FROM wiki_index WHERE title=? LIMIT 1",[title]).fetchone()
    return r[0] if r else None
def get_wikitext(title,hops=0):
    off=offset_for(title)
    if off is None: return None,None
    wt=article_text(read_stream(off),title)
    if wt is None: return None,None
    m=re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)",wt,re.IGNORECASE)
    if m and hops<2:
        t=m.group(1).strip(); return get_wikitext(t[:1].upper()+t[1:],hops+1)
    return wt,title
def field_notes(wt):
    wt=HEADING_RE.sub("",wt or ""); wt=CONVERT_RE.sub(r"\1 \2",wt)
    out=[]
    for para in re.split(r"\n\n+",wt):
        if "<ref" not in para: continue
        text=mw.parse(REF_RE.sub("",para)).strip_code()
        for s in re.split(r"(?<=[.!?])\s+",text):
            s=re.sub(r"\s+"," ",s).strip()
            if not (10<=len(s.split())<=45 and s[:1].isupper()): continue
            if "|" in s or "=" in s: continue
            if s.startswith(("It ","They ","These ","This species","He ","She ")): continue
            if TONE_BLOCK.search(s): continue
            out.append(s)
    seen=set(); return [x for x in out if not (x in seen or seen.add(x))]

def work(item):
    sid, sci, common = item
    try:
        wt,title=get_wikitext(sci)
        if wt is None and common and common!=sci: wt,title=get_wikitext(common)
        if wt is None: return (sid, sci, None, 0, 0, 0, [])
        notes=field_notes(wt)
        return (sid, sci, title, len(wt), len(REF_RE.findall(wt)), len(notes), notes)
    except Exception as e:
        return (sid, sci, None, 0, 0, 0, [])

if __name__=="__main__":
    c=con()
    items=c.sql("""SELECT c.species_id, c.canonicalName, cn.common_name FROM catalog c
      LEFT JOIN species_common_names cn USING(species_id) ORDER BY c.canonicalName""").fetchall()
    _con.close(); _con=None
    print(f"{len(items):,} deck species", flush=True)
    t0=time.time(); out=[]; done=0
    with Pool(6) as pool:
        for r in pool.imap_unordered(work, items, chunksize=8):
            out.append(r); done+=1
            if done%500==0: print(f"  {done:,}/{len(items):,}  ({(time.time()-t0)/60:.0f}m)", flush=True)
    json.dump([list(r) for r in out], open(f"{DATA}/wiki_fame.json","w"), ensure_ascii=False)
    hit=sum(1 for r in out if r[2])
    print(f"DONE: {hit:,}/{len(out):,} articles found, {sum(r[5] for r in out):,} field-note candidates  ({(time.time()-t0)/60:.0f}m)", flush=True)
