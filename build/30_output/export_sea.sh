#!/bin/sh
# THE SEA, for the app's colour map (2026-10-07: "why is the sf bay green?" →
# a mask, then "needs some work still": built at runtime from eco_detail, the
# mask followed that file's coast, 3–13 km inside the East Bay shore, and
# painted Oakland as water). The RAW RESOLVE polygons are dissolved into one
# land shape — only the coast survives the dissolve, so it can keep far more
# of its vertices than the ecoregion tiers do — and erased from a world
# rectangle. Two tiers, like the ecoregions: sea_simple for first paint,
# sea_detail swapped in once the colour map is on and the detail has arrived.
# eco 0 'Rock and Ice' (Greenland's interior, Antarctica) is LAND here.
set -e
cd "$(dirname "$0")"
RAW=../../data/ecoregions_raw.geojson
OUT=../../explorer/data
# IN 10° PIECES (2026-10-07, later: the Camp picture showed blue wedges across
# Nevada). As ONE world-sized polygon with thousands of holes, the mask broke
# up in MapLibre's coarse tiles (z2 — the small Camp picture's zoom): the tile
# cutter simplifies and clips each polygon whole. The world is a grid of 10°
# rectangles instead, the land erased from each, so every piece is small and
# has few holes. Two steps: the dissolved land to a temp file, then the erase.
GRID=$(mktemp -t seagrid).geojson
/usr/bin/python3 - "$GRID" <<'PY'
import json, sys
lats = [-85.05] + list(range(-80, 81, 10)) + [85.05]
fs = []
for x in range(-180, 180, 10):
    for y0, y1 in zip(lats, lats[1:]):
        fs.append({"type": "Feature", "properties": {"c": len(fs)},
                   "geometry": {"type": "Polygon", "coordinates": [[[x, y0], [x + 10, y0], [x + 10, y1], [x, y1], [x, y0]]]}})
json.dump({"type": "FeatureCollection", "features": fs}, open(sys.argv[1], "w"))
PY
build() {   # build <percent> <precision> <name>
  LAND=$(mktemp -t sealand).geojson
  npx -y -p mapshaper mapshaper-xl 12gb "$RAW" snap -target type=polygon -clip bbox=-180,-85,180,85 \
    -dissolve -simplify "$1" keep-shapes -clean \
    -o precision="$2" format=geojson "$LAND"
  npx -y -p mapshaper mapshaper-xl 12gb "$GRID" -erase "$LAND" -clean \
    -o precision="$2" format=geojson "$OUT/$3.geojson"
  rm -f "$LAND"
}
build 12% 0.0001 sea_detail
build 1.5% 0.001 sea_simple
ls -la "$OUT/sea_detail.geojson" "$OUT/sea_simple.geojson"
