# %% [markdown]
# # PolygroveDB — seasonality + origin from GBIF (step 12)
#
# Two candidates I'd asserted without data. Both are columns in the GBIF
# occurrence Parquet (`month`, `establishmentmeans`), so we pull them from a
# sample and actually score them:
#
# - **Seasonality** — "what month are you most likely to see it?" A good question
#   needs species whose sightings **cluster** in a peak month (migratory birds,
#   flowering plants) vs. year-round residents (no answer). Metric: peak-month share.
# - **Origin** — native range from `establishmentmeans='NATIVE'`. We *measure*
#   how sparse it is instead of asserting.

# %%
import duckdb
con = duckdb.connect("../polygrove.duckdb")
con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-east-1';")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")

SNAP="s3://gbif-open-data-us-east-1/occurrence/2026-08-01/occurrence.parquet"
parts=[r[0] for r in con.sql(f"SELECT file FROM glob('{SNAP}/*') LIMIT 60").fetchall()]
psql="["+",".join(f"'{p}'" for p in parts)+"]"

# pull species + month + establishmentmeans (one pass over the sample)
con.sql(f"""
CREATE OR REPLACE TEMP TABLE occ2 AS
SELECT species, month, establishmentmeans AS em, countrycode AS cc
FROM read_parquet({psql})
WHERE species IS NOT NULL AND lower(taxonrank)='species';
""")
print("occurrence records in sample:", con.sql("SELECT count(*) FROM occ2").fetchone()[0])

# %% [markdown]
# ## Seasonality — peak-month concentration per species

# %%
con.sql("""
CREATE OR REPLACE TEMP TABLE seas AS
WITH per AS (
  SELECT species, month, count(*) c FROM occ2 WHERE month BETWEEN 1 AND 12 GROUP BY 1,2
),
tot AS (SELECT species, sum(c) n, max(c) peak FROM per GROUP BY 1)
SELECT species, n, round(1.0*peak/n,3) AS peak_share FROM tot WHERE n >= 20;
""")
con.sql("""
SELECT count(*) AS species_judged,
  round(100.0*avg((peak_share>=0.30)::int),1) AS pct_seasonal_peak30,
  round(100.0*avg((peak_share>=0.50)::int),1) AS pct_strong_peak50,
  round(avg(peak_share),3) AS avg_peak_share
FROM seas
""").show()

# %% [markdown]
# ## Origin — how much establishmentMeans actually exists

# %%
con.sql("SELECT coalesce(em,'(null)') AS establishment, count(*) AS records FROM occ2 GROUP BY 1 ORDER BY 2 DESC LIMIT 8").show()
con.sql("""
SELECT count(DISTINCT species) AS species_in_sample,
  count(DISTINCT CASE WHEN upper(em)='NATIVE' THEN species END) AS species_with_native_tag,
  round(100.0*count(DISTINCT CASE WHEN upper(em)='NATIVE' THEN species END)/count(DISTINCT species),1) AS pct_with_origin
FROM occ2
""").show()

# %%
con.close()
