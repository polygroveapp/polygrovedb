#!/bin/sh
# Phone-sized ecoregion geometry for the app's map picker (2026-09-26):
# the explorer's 10MB ecoregions.geojson simplified to 2% (keep-shapes so no
# ecoregion vanishes) at 0.01° precision → ~850KB, 847 features, props eco+name.
set -e
cd "$(dirname "$0")/../../explorer/data"
# eco 0 'Rock and Ice' is the polar/glacier mask, not a playable ecoregion — its
# ring circles the pole (-180→180) and MapKit draws it as lines across the globe
npx -y mapshaper ecoregions.geojson -filter 'eco != 0' -simplify 2% keep-shapes \
  -o precision=0.01 format=geojson eco_simple.geojson
ls -la eco_simple.geojson
