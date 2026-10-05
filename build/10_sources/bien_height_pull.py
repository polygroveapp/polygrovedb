# %% [markdown]
# # PolygroveDB — pull plant heights from BIEN (2026-10-05)
#
# BIEN publishes its trait data (CC BY) through a public, read-only PostgreSQL
# that its R package connects to; this asks the same database the same way,
# but aggregates on the server so ten million height records come back as one
# row per species × unit × access (count, median, max). Network step: run once,
# the result is `data/bien_height.csv` (gitignored data/, like every dump).
# The query is heavy on their side — allow an hour.

# %%
import psycopg2, csv, time
t = time.time()
con = psycopg2.connect(host='vegbiendev.nceas.ucsb.edu', dbname='public_vegbien',
                       user='public_bien', password='bien_public', connect_timeout=30)   # BIEN's published public access (see the BIEN R package)
cur = con.cursor(); cur.execute("SET statement_timeout = 7200000")
cur.execute(r"""
SELECT scrubbed_species_binomial, unit, access, count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY val) AS h_med, max(val) AS h_max
FROM (SELECT scrubbed_species_binomial, unit, access, trait_value::numeric AS val
      FROM agg_traits
      WHERE trait_name IN ('whole plant height','maximum whole plant height')
        AND scrubbed_species_binomial IS NOT NULL AND trait_value ~ '^[0-9]*\.?[0-9]+$') t
GROUP BY 1,2,3""")
rows = cur.fetchall()
with open('../../data/bien_height.csv', 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['sci', 'unit', 'access', 'n', 'h_med', 'h_max']); w.writerows(rows)
print(f"{len(rows):,} species×unit×access rows in {time.time()-t:.0f}s")
