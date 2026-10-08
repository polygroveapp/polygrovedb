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
build() {   # build <percent> <precision> <name>
  npx -y -p mapshaper mapshaper-xl 12gb "$RAW" snap -target type=polygon -clip bbox=-180,-85,180,85 \
    -dissolve -rename-layers land -simplify "$1" keep-shapes -clean \
    -rectangle bbox=-180,-85.05,180,85.05 name=world -erase land \
    -o target=world precision="$2" format=geojson "$OUT/$3.geojson"
}
build 12% 0.0001 sea_detail
build 1.5% 0.001 sea_simple
ls -la "$OUT/sea_detail.geojson" "$OUT/sea_simple.geojson"
