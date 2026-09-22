# Extract Wikipedia field-note candidates for specific species and merge them
# into the explorer's dossier shards (APP-LAYER only — CC-BY-SA text stays out
# of the CC-BY database, per the license rule). DB is touched read-only (wiki
# index lookup). Reuses the exact extraction+cleanup rules of the pilot
# (20_derive/wiki_fieldnotes + fieldnote_cleanup).
#
#   python3 extract_fieldnotes_species.py "Sequoia sempervirens" "Sequoiadendron giganteum"

import duckdb, bz2, re, html, json, os, sys
import mwparserfromhell as mw

DATA="../../data"; DUMP=f"{DATA}/enwiki-multistream.xml.bz2"
con=duckdb.connect(); con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")

REF_RE=re.compile(r"<ref[^>]*>(.*?)</ref>", re.DOTALL|re.IGNORECASE)
HEADING_RE=re.compile(r"(?m)^=+\s*.+?\s*=+\s*$")
CONVERT_RE=re.compile(r"\{\{(?:convert|cvt)\s*\|\s*([^|}]+)\s*\|\s*([^|}]+)[^}]*\}\}", re.I)
TONE_BLOCK=re.compile(r"\b(rap(e|es|ed|ing)|molest|mutilat|disembowel|dismember|slaughter)\w*", re.I)

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

def djb2(s):
    h=5381
    for ch in s: h=((h*33)+ord(ch))&0xffffffff
    return h%256

for sci in sys.argv[1:]:
    wt=get_wikitext(sci)
    notes=field_notes(wt) if wt else []
    print(f"{sci}: {len(notes)} candidate notes" + ("" if wt else "  (NO ARTICLE FOUND)"))
    if not notes: continue
    shard=f"../../explorer/data/dossier/{djb2(sci)}.json"
    data=json.load(open(shard)) if os.path.exists(shard) else {}
    entry=[r for r in data.get(sci,[]) if r[0]!='Wikipedia extracts (sourced)']
    entry+= [['Wikipedia extracts (sourced)','candidate field note',n] for n in notes]
    data[sci]=entry
    json.dump(data,open(shard,"w"),ensure_ascii=False,separators=(',',':'))
    print(f"  -> merged into dossier shard {djb2(sci)}.json")
con.close()
