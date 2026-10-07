# Re-extract ONLY the Wikipedia notes whose {{convert}} measurements were cut
# ("grows to a length of 35 –." — Pacific baza), by index seek into the local dump:
# one ~1 MB block per article, the same mechanism as extract_ecoregion_leads.py.
# NOT the multi-hour dump scan.
#
#   python3 reextract_convert_notes.py                        # dry run: what would change
#   python3 reextract_convert_notes.py --write                # patch the caches + the dossier shards
#   python3 reextract_convert_notes.py --write "Aviceda subcristata" "Zea mays"   # named species only
#   python3 reextract_convert_notes.py --all                  # every deck article, not just the suspects
#
# Which species: by default the ones whose SHIPPED text shows what the old regex
# left behind — a number, a space, then a dash / to / and / or / by with no number after it.
# The proof it is safe: each article is first extracted the OLD way and must reproduce
# the shipped text exactly (same dump, same rules); only then is it extracted the new
# way and swapped in. Anything that does not reproduce is left alone and listed.
#
# Patches data/wiki_lead.json + data/wiki_fame.json (so a later export_dossier.py
# keeps the fix) and explorer/data/dossier/<shard>.json in place. APP-LAYER text only
# (CC-BY-SA) — the DB is opened read-only, and wiki_fame.json's cited-sentence COUNT
# (it feeds species_fame) is left as it was: this is a text fix, not a fame change.
# Readable text only — no size is read out of Wikipedia into a card fact.

import json, os, re, sys, time, shutil, random
from difflib import SequenceMatcher
import extract_lead_sentences as leads          # get_wikitext + lead_sentence (its main loop is guarded)
import wiki_fame_fieldnotes as cands            # field_notes
from wiki_convert import render_converts, render_converts_legacy

DATA="../../data"; SHARDS="../../explorer/data/dossier"
SRC='Wikipedia extracts (sourced)'
SUSPECT=re.compile(r"\d (?:[–—-](?![\d–—-])|(?:to|and|or|by|x|×)(?![\w])(?!\s*[-−+.]?\d))")

def djb2(s):
    h=5381
    for ch in s: h=((h*33)+ord(ch))&0xffffffff
    return h%256
def tidy(t):                                    # export_dossier.py's _tidy, applied to every shipped lead
    t=re.sub(r"\(\s*[;,·]\s*", "(", t); t=re.sub(r"\(\s*\)", "", t)
    t=re.sub(r"\s+([,.;])", r"\1", t); return re.sub(r"\s{2,}", " ", t).strip()
def numbers(t):
    """the numbers a sentence states, unit exponents and thousands commas aside"""
    t=re.sub(r"(?<=\d),(?=\d{3})","",t); t=re.sub(r"\be\d+(?=[A-Za-z])|(?<=[A-Za-zμ])[23]|[²³]","",t)
    return sorted(n.rstrip(".") for n in re.findall(r"\d+(?:\.\d+)?|\.\d+",t))
def loses_number(old, new):
    have=numbers(new)
    for n in numbers(old):
        if n in have: have.remove(n)
        else: return True
    return False
def both(mod, fn, wt):
    """(old way, new way) of one extraction"""
    mod.render_converts=render_converts_legacy; old=fn(wt)
    mod.render_converts=render_converts;        new=fn(wt)
    return old, new

args=[a for a in sys.argv[1:] if not a.startswith("--")]
WRITE="--write" in sys.argv; ALL="--all" in sys.argv
SAMPLE=next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--sample=")), 0)   # N UNsuspected species: how many does the pattern miss?

lead=json.load(open(f"{DATA}/wiki_lead.json"))
fame=json.load(open(f"{DATA}/wiki_fame.json"))
fame_by_sci={r[1]:r for r in fame}
sid2sci={str(sid):sci for sid,sci in leads._con.sql("SELECT species_id, canonicalName FROM catalog").fetchall()}
# cards that have left the deck since the leads were extracted still have their shipped shard rows
gone_sids=[int(s) for s in lead if s not in sid2sci]
if gone_sids:
    sid2sci.update({str(sid):sci for sid,sci in leads._con.execute(
        "SELECT species_id, canonicalName FROM species WHERE species_id IN (SELECT unnest(?))",[gone_sids]).fetchall()})
lead_by_sci={sid2sci[sid]:d for sid,d in lead.items() if sid in sid2sci}

known=sorted(set(lead_by_sci)|{r[1] for r in fame if r[6]})
suspect=[s for s in known
         if (s in lead_by_sci and SUSPECT.search(lead_by_sci[s]['lead']))
         or any(SUSPECT.search(n) for n in (fame_by_sci[s][6] if s in fame_by_sci else []))]
if args: todo=args
elif ALL: todo=known
elif SAMPLE:
    random.seed(20260929); todo=random.sample(sorted(set(known)-set(suspect)), SAMPLE)
else: todo=suspect
print(f"{len(known):,} species carry Wikipedia text · {len(suspect):,} match the suspect pattern · re-extracting {len(todo):,}", flush=True)

new_lead={}; new_notes={}; old_notes={}; unproven=[]; lossy=[]; changes=[]; t0=time.time()
for i,sci in enumerate(todo):
    d=lead_by_sci.get(sci)
    if d:
        wt,_=leads.get_wikitext(d['title'])
        old,new=both(leads, leads.lead_sentence, wt) if wt else (None,None)
        if old!=d['lead']: unproven.append((sci,'lead'))
        elif new and new!=old:
            if loses_number(old,new) and SequenceMatcher(None,old,new).ratio()>0.6: lossy.append((sci,'lead',old,new))
            else: new_lead[sci]=new; changes.append((sci,'lead',tidy(old),tidy(new)))
    r=fame_by_sci.get(sci)
    if r and r[6]:
        wt,_=leads.get_wikitext(r[2])
        old,new=both(cands, cands.field_notes, wt) if wt else (None,None)
        if old!=r[6]: unproven.append((sci,'candidates'))
        elif new!=old:
            pairs=[]
            gone=[o for o in old if o not in set(new)]; came=[n for n in new if n not in set(old)]
            for o in gone:                          # pair each old sentence with the new one it became
                best=max(came, key=lambda n: SequenceMatcher(None,o,n).ratio(), default=None)
                if best and SequenceMatcher(None,o,best).ratio()>0.6: came.remove(best)
                else: best=None                     # gone for good: past the 45-word limit once whole
                pairs.append((sci,'candidate',o,best))
            pairs += [(sci,'candidate',None,n) for n in came]       # long enough (10 words) once whole
            bad=[p for p in pairs if p[2] and p[3] and loses_number(p[2],p[3])]
            if bad: lossy += bad                    # never swap in a sentence that lost a number
            else: new_notes[sci]=new; old_notes[sci]=old; changes += pairs
    if (i+1)%250==0: print(f"  {i+1:,}/{len(todo):,} · {len(new_lead):,} leads + {len(new_notes):,} note lists change · {(time.time()-t0)/60:.1f}m", flush=True)

n_l=sum(1 for c in changes if c[1]=='lead'); n_c=sum(1 for c in changes if c[1]=='candidate')
print(f"\n{n_l:,} lead sentences and {n_c:,} candidate notes change, across {len(set(new_lead)|set(new_notes)):,} species  ({(time.time()-t0)/60:.1f}m)")
print(f"{len(unproven):,} extractions did not reproduce the shipped text and were left alone" + (": "+", ".join(f"{s} ({k})" for s,k in unproven[:12]) if unproven else ""))
print(f"{len(lossy):,} notes would have LOST a number the shipped text states — those species were left alone" + "".join(f"\n   [{s}] - {o}\n   {' '*len(s)}   + {n}" for s,k,o,n in lossy[:10]))
still=[c for c in changes if c[3] and SUSPECT.search(c[3])]
print(f"{len(still):,} changed notes still show a dangling number (not a convert template — {{{{val}}}}, {{{{nowrap}}}}, plain text)")
os.makedirs("../_scratch", exist_ok=True)
REPORT=f"../_scratch/convert_reextract_report{'_named' if args else '_sample' if SAMPLE else ''}.json"
json.dump({"changes":changes,"unproven":unproven,"lossy":lossy}, open(REPORT,"w"), ensure_ascii=False, indent=1)
print(f"every before/after: build/{REPORT[3:]}")
random.seed(7)
for sci,kind,o,n in random.sample(changes, min(12,len(changes))):
    print(f"\n  [{sci} · {kind}]\n   - {o}\n   + {n}")

if WRITE and (new_lead or new_notes):
    for f in ("wiki_lead.json","wiki_fame.json"):
        if not os.path.exists(f"{DATA}/{f}.pre-convert-fix"): shutil.copy2(f"{DATA}/{f}", f"{DATA}/{f}.pre-convert-fix")
    sci2sid={v:k for k,v in sid2sci.items()}
    for sci,s in new_lead.items(): lead[sci2sid[sci]]['lead']=s
    for sci,notes in new_notes.items(): fame_by_sci[sci][6]=notes
    json.dump(lead, open(f"{DATA}/wiki_lead.json","w"))
    json.dump(fame, open(f"{DATA}/wiki_fame.json","w"), ensure_ascii=False)
    by_shard={}
    for sci in set(new_lead)|set(new_notes): by_shard.setdefault(djb2(sci),[]).append(sci)
    rows_l=rows_c=0; skipped=[]
    is_cand=lambda row: row[0]==SRC and row[1]=='candidate field note'
    for sh,scis in by_shard.items():
        path=f"{SHARDS}/{sh}.json"; data=json.load(open(path))
        for sci in scis:
            entry=data.get(sci)
            if entry is None: continue
            if sci in new_lead:
                for row in entry:
                    if row[0]==SRC and row[1].startswith('lead sentence'): row[2]=tidy(new_lead[sci]); rows_l+=1
            if sci in new_notes:
                old,new=old_notes[sci],new_notes[sci]
                at=[k for k,row in enumerate(entry) if is_cand(row)]
                if [entry[k][2] for k in at]==old:          # the shard holds exactly the cached list: swap the list
                    data[sci]=[row for row in entry[:at[0]] if not is_cand(row)] \
                             +[[SRC,'candidate field note',n] for n in new] \
                             +[row for row in entry[at[0]:] if not is_cand(row)]
                    rows_c+=len(new)
                elif len(old)==len(new):                     # it holds more (the 6 pilot species' DB rows): fix sentence by sentence
                    swap={o:n for o,n in zip(old,new) if o!=n}
                    for k in at:
                        if entry[k][2] in swap: entry[k][2]=swap[entry[k][2]]; rows_c+=1
                else: skipped.append(sci)
        json.dump(data, open(path,"w"), ensure_ascii=False, separators=(',',':'))
    if skipped: print(f"shard candidates left alone (shipped list differs from the cache): {', '.join(skipped)}")
    print(f"\nWROTE: {len(by_shard)} shards patched ({rows_l:,} lead rows; the candidate lists of {len(new_notes):,} species, {rows_c:,} rows); caches updated, originals kept as data/*.pre-convert-fix")
elif not WRITE:
    print("\nDRY RUN — nothing written. --write patches the caches and the shards.")
