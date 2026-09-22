# %% [markdown]
# # PolygroveDB — full-species search index for the explorer
#
# "Look up ANY species in the database": the >=3-question pool ships whole
# (pool.json, 57k); the TAIL — species 3-5 facts short, ~2.5M — is too big for
# one file, so it's sharded by the first two letters of the name
# (explorer/data/index/xx.json). The site fetches one prefix shard once the
# user has typed 2+ characters. index_meta.json carries the per-tier counts
# for the fold-down headers. Read-only on the DB.

# %%
import duckdb, json, os, time
from collections import defaultdict
t0=time.time()
con = duckdb.connect()
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY); USE pg;")

meta = {str(5-r[0]): r[1] for r in con.sql("""
  SELECT has_feeding+has_size+has_foodweb+has_slot5+has_biome AS lv, count(*)
  FROM card_pool GROUP BY 1""").fetchall()}
json.dump(meta, open("../../explorer/data/index_meta.json","w"))
print("tier counts (facts short -> species):", meta)

rows = con.sql("""
  SELECT canonicalName, class,
         has_feeding*16+has_size*8+has_foodweb*4+has_slot5*2+has_biome AS mask
  FROM card_pool
  WHERE has_feeding+has_size+has_foodweb+has_slot5+has_biome <= 3
    AND canonicalName IS NOT NULL""").fetchall()
print(f"tail species: {len(rows):,}  ({time.time()-t0:.0f}s)", flush=True)

shards=defaultdict(list)
for sci, cls, mask in rows:
    s=''.join(ch for ch in sci[:4].lower() if ch.isalpha())[:2]
    shards[s if len(s)==2 else '_'].append([sci, cls, mask])
outdir="../../explorer/data/index"; os.makedirs(outdir, exist_ok=True)
for p, data in shards.items():
    json.dump(data, open(f"{outdir}/{p}.json","w"), ensure_ascii=False, separators=(',',':'))
biggest=max(shards.items(), key=lambda kv: len(kv[1]))
print(f"wrote {len(shards)} prefix shards; biggest '{biggest[0]}' = {len(biggest[1]):,} rows  ({time.time()-t0:.0f}s)")
con.close()
