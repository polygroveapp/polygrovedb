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
import os
# export_dossier.py imports this module for the sentence scorer alone and
# sets LEADS_NO_DB so no second database handle is opened
_con=None
if not os.environ.get("LEADS_NO_DB"):
    _con=duckdb.connect(); _con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")
import threading
_tl=threading.local()
def _conn():
    # one cursor per thread: the index lookups run from a thread pool
    if not hasattr(_tl,'c'): _tl.c=_con.cursor()
    return _tl.c
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
    r=_conn().execute("SELECT byte_offset FROM pg.wiki_index WHERE title=? LIMIT 1",[title]).fetchone()
    if not r: return None,None
    wt=article_text(read_stream(r[0]),title)
    if wt is None: return None,None
    m=re.match(r"\s*#REDIRECT\s*\[\[([^\]|#]+)",wt,re.IGNORECASE)
    if m and hops<2:
        t=m.group(1).strip(); return get_wikitext(t[:1].upper()+t[1:],hops+1)
    return wt,title
from wiki_convert import render_converts   # {{convert}} ranges written out: 35–46 cm
def lead_candidates(wt, n=3):
    """The first n real sentences of the lead, cleaned (the field note is picked
    from these by pick_lead)."""
    if not wt: return []
    body=re.split(r"(?m)^=+",wt)[0]                      # lead section only
    body=render_converts(body)
    body=re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>","",body,flags=re.DOTALL)
    code=mw.parse(body)
    # remove File:/Image: links BEFORE strip_code — their captions otherwise glue
    # onto the first sentence ("thumb|Illustration of wormwood… Artemisia absinthium
    # … is a species…"), sinking it (412 cards shipped a pronoun opener that way)
    for ln in code.filter_wikilinks():
        t=str(ln.title).strip().lower()
        if t.startswith(("file:","image:")):
            try: code.remove(ln)
            except ValueError: pass
    text=code.strip_code()
    # re-join fragments split at abbreviations ("the Lake Mweru endemic, L. miodon",
    # "described by John O. Westwood") — 266 leads shipped truncated at these
    ABBR=re.compile(r"\b(?:[A-Z]|sp|subsp|ssp|var|cf|ca|St|Mt|no|subg|sect|et al)\.$")
    sents=[]; buf=""
    for f in re.split(r"(?<=[.!?])\s+",text.strip()):
        buf=(buf+" "+f).strip()
        if ABBR.search(buf): continue
        sents.append(buf); buf=""
    if buf: sents.append(buf)
    good=[]
    for s in sents:
        s=re.sub(r"\s+"," ",s).strip()
        if len(s.split())<6 or not s[:1].isupper(): continue
        if "|" in s or "{" in s or "}" in s: continue
        if is_junk(s): continue
        good.append(s)
        if len(good)==n: break
    return good

# an infobox that survived strip_code reads "Scientific Classification Kingdom:
# Animalia Phylum: Chordata …" (the western rattlesnake's card showed it,
# 2026-10-06) — never a field note
JUNK=re.compile(r"scientific classification|binomial name|conservation status|\bkingdom:|\bphylum:|\bclass:|\border:|\bfamily:|\bgenus:|\bspecies:",re.IGNORECASE)
def is_junk(s):
    return bool(JUNK.search(s)) or len(re.findall(r"\b[A-Z][a-z]+:",s))>=3

# THE MOST INTERESTING SENTENCE (user, 2026-10-06: "find the most interesting
# sentence out of the first 3 wikipedia sentences"). Before this the card took
# sentence two blind. Now each of the first three is scored: taxonomy and
# name-list boilerplate ("is a species of…", "common names include…", "in the
# family Asteraceae") loses points, and the things a person would repeat —
# a number, a superlative, a use, a danger, a habit, a story behind the name —
# gain them. Ties go to the earlier sentence; sentence one starts a point down
# because the card's own header already says what the species is.
DULL=[(2,r"\bis an? (?:\w+ ){0,3}(?:species|genus|member|type|kind|group|subspecies)\b"),
      (2,r"\b(?:common names?|other names?|names?) (?:include|are|is|includes)\b|\b(?:also|commonly|otherwise|sometimes|variously) (?:known|called|referred to) as\b|\bsynonyms?\b|\bvarious common names\b"),
      (1.5,r"\b(?:family|subfamily|order|suborder|tribe|subgenus|superfamily|class|phylum|clade)\b|\w+(?:aceae|idae|inae|ales|iformes)\b"),
      (1,r"\b(?:was |were )?(?:first )?(?:described|named|classified|placed|moved|erected|circumscribed) (?:by|in|as)\b|\bbinomial\b|\btaxonom|\bthe type species\b"),
      (1,r"\b(?:native|endemic|indigenous) to\b|\bis found (?:in|from|throughout)\b|\b(?:is )?distributed\b|\boccurs (?:in|from|throughout)\b|\bits (?:natural )?(?:habitats?|range) (?:is|are|includes)\b"),
      (1,r"\b(?:is|are) an? (?:small|large|medium-sized )?(?:perennial|annual|biennial|herbaceous|evergreen|deciduous|flowering|woody|aquatic)\b")]
FUN=[(1.5,r"\d"),
     (2,r"\b(?:largest|smallest|longest|tallest|shortest|heaviest|lightest|fastest|slowest|oldest|only|sole|rarest|second-largest|among the|one of the|the (?:most|least))\b"),   # bare "most" matched "most of Canada" (2026-10-06)
     (2,r"\b(?:used|eaten|edible|cultivated|ornamental|medicin|spice|dye|timber|crop|harvested|hunted|fished|pets?|domesticat|cuisine|cooked|brewed|wine|spirit|tea|coffee|oil|perfume|flavou?r)"),
     (2,r"\b(?:poison|toxic|venom|sting|bites?|deadly|lethal|invasive|pest|weed|endangered|extinct|threatened|vulnerable|critically)"),
     (2,r"\b(?:named|name|epithet) (?:after|comes|derives|refers|honou?rs|is derived|means|was given)\b|\bknown for\b|\bfamous\b|\bpopular\b|\biconic\b|\bsymbol\b|\bnational (?:bird|animal|flower|tree)\b|\bstate (?:bird|animal|flower|tree|fish|insect)\b|\bfolklore\b|\bmyth"),
     (1.5,r"\b(?:unlike|despite|although|unusual|unique|remarkabl|distinctive|striking|notabl|peculiar|surprising|unexpectedly|misnomer|confused with|mistaken for|niche|species pair|closest (?:living )?relative|sister species)\b"),
     (1.5,r"\b(?:can|may|able to) (?:live|grow|reach|weigh|fly|run|dive|survive|jump|swim|climb|exceed|produce|lay)\b|\byears?\b|\bdecades\b"),
     (1.5,r"\b(?:nocturnal|diurnal|migrat|hibernat|burrow|nests?|song|calls?|sings|mimic|hunts?|preys?|feeds? on|\bdiet\b|pollinat|parasit|symbio|glow|bioluminesc|camoufla|mimicry|carnivorous|hermaphrod|lives? in (?:colonies|groups|packs|flocks|herds)|spawn|venomous|regenerat|courtship|display)"),
     (1,r'"|\u201c|\bso-called\b|\bnicknamed\b')]
def score_lead(s, i):
    sc = -1.0 if i==0 else 0.0
    for w,rx in DULL:
        if re.search(rx,s,re.IGNORECASE): sc-=w
    for w,rx in FUN:
        if re.search(rx,s,re.IGNORECASE): sc+=w
    n=len(s.split())
    if n>48: sc-=1.5          # a paragraph crammed into one sentence
    elif n>38: sc-=0.5
    if n<9: sc-=0.5
    if re.match(r"^(?:It|They|This|These|The (?:species|genus|plant|tree|bird|fish))\b",s): sc-=0   # pronoun openers read fine on a card
    return sc
def pick_lead(cands):
    """index of the sentence the card should show, or None"""
    if not cands: return None
    best=max(range(len(cands)), key=lambda i:(score_lead(cands[i],i), -abs(i-1)))
    return best
def lead_sentence(wt):
    """Kept for reextract_convert_notes.py: the picked sentence of the lead."""
    c=lead_candidates(wt); i=pick_lead(c)
    return c[i] if i is not None else None
def _extract(job):
    sid,sci,genus,title=job
    wt,resolved=get_wikitext(title)
    lvl='species'
    if wt is None and genus!=title:
        wt,resolved=get_wikitext(genus); lvl='genus'
    if wt is None: return sid,None
    c=lead_candidates(wt); i=pick_lead(c)
    if i is None: return sid,None
    return sid,{"lead":c[i],"level":lvl,"title":resolved,"sents":c,"pick":i}
if __name__=="__main__":   # importable: reextract_convert_notes.py reuses lead_sentence()
    # deck + their wiki titles (from the fame pass) + genus
    deck=_con.sql("""SELECT c.species_id, s.canonicalName, split_part(s.canonicalName,' ',1) genus
      FROM pg.catalog c JOIN pg.species s USING(species_id) ORDER BY c.species_id""").fetchall()
    fame={r[0]:r[2] for r in json.load(open('../../data/wiki_fame.json'))}
    jobs=[(sid,sci,genus,fame.get(sid) or sci) for sid,sci,genus in deck]
    out={}; t0=time.time(); n_sp=n_gen=0
    # six threads: bz2 decompression releases the GIL, and that is most of the
    # work (processes would be faster still, but fork() and spawn both fight
    # macOS + DuckDB)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as pool:
        for i,(sid,d) in enumerate(pool.map(_extract,jobs)):
            if d:
                out[str(sid)]=d
                n_sp+= d['level']=='species'; n_gen+= d['level']=='genus'
            if (i+1)%1000==0:
                print(f"  {i+1:,}/{len(deck):,} · species-level {n_sp:,} · genus-fallback {n_gen:,} · {(time.time()-t0)/60:.0f}m", flush=True)
    json.dump(out,open('../../data/wiki_lead.json','w'))
    from collections import Counter
    print(f"DONE: {len(out):,}/{len(deck):,} cards have a lead sentence ({n_sp:,} species, {n_gen:,} genus); picked sentence: {dict(Counter(d['pick']+1 for d in out.values()))}  ({(time.time()-t0)/60:.0f}m)", flush=True)
