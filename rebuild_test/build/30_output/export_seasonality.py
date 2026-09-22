# %% [markdown]
# # PolygroveDB — seasonal strips for the explorer (set-based)
#
# Per deck card: 12-month histogram over the card's OWN top-60 ecoregions.
#   raw  — share of records per month ("when people see it")
#   corr — effort-corrected shares ("per unit of looking") — the observer-bias lesson.
# Parquet-only (no DB lock). norm() runs once over the 948k distinct names, not 19.6M rows.

# %%
import duckdb, json, time
t0=time.time()
cards=json.load(open('catalog.json'))
con=duckdb.connect()
con.sql(r"""CREATE TEMP MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("CREATE TEMP TABLE card_eco(cid VARCHAR, k VARCHAR, eco BIGINT)")
con.executemany("INSERT INTO card_eco VALUES (?,?,?)",
  [(c['id'], ' '.join(c['sci'].lower().split()[:2]), e) for c in cards for e in (c.get('ecoregions') or [])])
con.sql("""CREATE TEMP TABLE hist AS
  WITH names AS (SELECT DISTINCT species FROM read_parquet('../../data/species_eco_month.parquet')),
  nm AS (SELECT species, norm(species) k FROM names),
  sem AS (SELECT nm.k, s.ecoregion_id eco, s.month, s.n
          FROM read_parquet('../../data/species_eco_month.parquet') s JOIN nm ON nm.species=s.species),
  j AS (SELECT ce.cid, sem.month, sum(sem.n) raw,
               sum(sem.n / NULLIF(e.eff,0)) corr
        FROM card_eco ce JOIN sem ON sem.k=ce.k AND sem.eco=ce.eco
        LEFT JOIN read_parquet('../../data/effort_eco_month.parquet') e
               ON e.ecoregion_id=ce.eco AND e.month=sem.month
        GROUP BY 1,2)
  SELECT cid, list(month ORDER BY month) AS mo_l,
         list(raw ORDER BY month) AS raw_l, list(corr ORDER BY month) AS corr_l, sum(raw) AS tot
  FROM j GROUP BY 1 HAVING sum(raw) >= 24""")
out={}
for cid, mo_l, raw_l, corr_l, tot in con.sql("SELECT * FROM hist").fetchall():
    raw=[0.0]*12; corr=[0.0]*12
    for mo,r,cv in zip(mo_l,raw_l,corr_l):
        raw[mo-1]=r; corr[mo-1]=cv or 0.0
    t=sum(raw) or 1; ct=sum(corr) or 1
    out[cid]={'raw':[round(x/t,4) for x in raw], 'corr':[round(x/ct,4) for x in corr], 'n':int(tot)}
json.dump(out, open('../../explorer/data/seasonality.json','w'), separators=(',',':'))
print(f"seasonality.json: {len(out):,}/{len(cards):,} cards with a strip ({time.time()-t0:.0f}s)")
