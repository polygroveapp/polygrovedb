# %% [markdown]
# # PolygroveDB — Wikipedia LEAD sentence for every deck card (app layer)
#
# Field-note candidates were CITED sentences only; lead sentences rarely carry <ref>
# tags, so 467 cards with articles had zero candidates — and 569 cards have no species
# article at all (user found Adeloneivaia boisduvalii → only the GENUS has a page).
# This extracts the first real sentence of the species article, falling back to the
# genus article (marked level:'genus'). Output data/wiki_lead.json — CC-BY-SA app
# layer like all Wikipedia text, never the DB.

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
def lead_sentence(wt):
    """First real sentence of the lead: skip templates/infobox, strip markup."""
    if not wt: return None
    body=re.split(r"(?m)^=+",wt)[0]                      # lead section only
    body=CONVERT_RE.sub(r"\1 \2",body)
    body=re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>","",body,flags=re.DOTALL)
    text=mw.parse(body).strip_code()
    for s in re.split(r"(?<=[.!?])\s+",text.strip()):
        s=re.sub(r"\s+"," ",s).strip()
        if len(s.split())<6 or not s[:1].isupper(): continue
        if "|" in s or "{" in s or "}" in s: continue
        return s
    return None
# deck + their wiki titles (from the fame pass) + genus
deck=_con.sql("""SELECT c.species_id, s.canonicalName, split_part(s.canonicalName,' ',1) genus
  FROM pg.catalog c JOIN pg.species s USING(species_id) ORDER BY c.species_id""").fetchall()
fame={r[0]:r[2] for r in json.load(open('../../data/wiki_fame.json'))}
out={}; t0=time.time(); n_sp=n_gen=0
for i,(sid,sci,genus) in enumerate(deck):
    title=fame.get(sid) or sci
    wt,resolved=get_wikitext(title)
    lvl='species'
    if wt is None and genus!=title:
        wt,resolved=get_wikitext(genus); lvl='genus'
    if wt is None: continue
    s=lead_sentence(wt)
    if s:
        out[str(sid)]={"lead":s,"level":lvl,"title":resolved}
        n_sp+= lvl=='species'; n_gen+= lvl=='genus'
    if (i+1)%1000==0:
        print(f"  {i+1:,}/{len(deck):,} · species-level {n_sp:,} · genus-fallback {n_gen:,} · {(time.time()-t0)/60:.0f}m", flush=True)
json.dump(out,open('../../data/wiki_lead.json','w'))
print(f"DONE: {len(out):,}/{len(deck):,} cards have a lead sentence ({n_sp:,} species, {n_gen:,} genus)  ({(time.time()-t0)/60:.0f}m)", flush=True)
