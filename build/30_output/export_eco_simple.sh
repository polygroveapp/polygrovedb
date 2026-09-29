#!/bin/sh
# Phone-sized ecoregion geometry for the app's map (2026-09-26; REBUILT
# 2026-09-29 after "the ecoregions aren't lining up").
# The first version simplified the explorer's ecoregions.geojson — but that
# file is BUFFERED (neighbours overlap instead of sharing an edge), so mapshaper
# saw no shared borders, simplified every polygon on its own, and adjacent
# regions drifted apart by kilometres once you zoomed in.
# Now: the RAW RESOLVE polygons (15M vertices, exact shared borders) go through
# mapshaper's TOPOLOGICAL simplify — a shared border is one arc, simplified
# once — so neighbours always coincide. Two tiers:
#   eco_simple.geojson  ~60k vertices  first paint, world zoom, the mini map
#   eco_detail.geojson  ~300k vertices lazy-loaded by map.html once zoomed in
#   eco_hd/<id>.json    30% of raw, per ecoregion, loaded for what's on screen past z5.5
set -e
cd "$(dirname "$0")"
RAW=../../data/ecoregions_raw.geojson
OUT=../../explorer/data
if [ ! -f "$RAW" ]; then
  /opt/homebrew/Caskroom/miniconda/base/bin/python3 - <<'PY'
import duckdb, time
t0=time.time()
con=duckdb.connect(); con.sql("INSTALL spatial; LOAD spatial;")
con.sql("ATTACH '../../polygrove.duckdb' AS pg (READ_ONLY);")
con.sql("""COPY (SELECT ECO_ID AS eco, ECO_NAME AS name, geom FROM pg.ecoregions WHERE geom IS NOT NULL)
           TO '../../data/ecoregions_raw.geojson'
           WITH (FORMAT GDAL, DRIVER 'GeoJSON', LAYER_CREATION_OPTIONS 'COORDINATE_PRECISION=5')""")
print(f"raw export done ({time.time()-t0:.0f}s)")
PY
fi
ls -la "$RAW"
# eco 0 'Rock and Ice' is the polar/glacier mask, not a playable ecoregion — its
# ring circles the pole; ±85° clip: Mercator ends at 85.05°
# GDAL writes a few non-polygon leftovers, which mapshaper splits into a second
# layer (…2.geojson): the polygons are layer 1, the leftovers are dropped
build() {   # build <percent> <precision> <name>
  npx -y -p mapshaper mapshaper-xl 12gb "$RAW" snap -filter 'eco != 0' -clip bbox=-180,-85,180,85 \
    -simplify "$1" keep-shapes -clean \
    -o precision="$2" format=geojson "$OUT/$3.geojson"
  if [ -f "$OUT/${3}1.geojson" ]; then mv "$OUT/${3}1.geojson" "$OUT/$3.geojson"; rm -f "$OUT/${3}2.geojson"; fi
}
build 2% 0.001 eco_detail
build 0.4% 0.01 eco_simple
ls -la "$OUT/eco_detail.geojson" "$OUT/eco_simple.geojson"
# HIGH DETAIL, one file per ecoregion (2026-09-29: "be accurate"): 30% of the
# raw vertices at ~10 m precision, still topological, so the coast is the
# coast and bay islands stay inside their region. map.html loads the files of
# whatever is on screen once zoomed past 5.5. ~850 files, ~80 MB, max ~2 MB.
mkdir -p "$OUT/eco_hd"
npx -y -p mapshaper mapshaper-xl 14gb "$RAW" snap -target type=polygon -filter 'eco != 0' -clip bbox=-180,-85,180,85 \
  -simplify 30% keep-shapes -clean -split eco \
  -o precision=0.0001 format=geojson extension=json "$OUT/eco_hd/"
ls "$OUT/eco_hd" | wc -l; du -sh "$OUT/eco_hd"
