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
