#!/usr/bin/env python3
"""PolygroveDB pipeline runner — executes the notebook chain in dependency order.

The clean-rebuild test: point at a fresh DB, run this end-to-end from the local
dumps in data/, and diff the resulting catalog against the shipped one.

    python3 run_all.py             # run everything
    python3 run_all.py --from resolve_rejoin   # resume mid-chain
    python3 run_all.py --list      # show the plan

Each script runs with cwd = its own directory (they use ../../data etc.).
Long steps are marked; the whole chain is hours, dominated by the wiki dump
scan and the spatial joins.
"""
import subprocess, sys, time, os

PY = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"
ROOT = os.path.dirname(os.path.abspath(__file__))

# (script, note) in EXECUTION order — this list IS the pipeline definition.
CHAIN = [
    ("00_substrate/backbone.py",           "GBIF backbone + RESOLVE ecoregions + EOL load (long: big CSVs)"),
    ("20_derive/wiki_fieldnotes.py",       "Wikipedia index + field notes (LONG: 25GB dump scan)"),
    ("00_substrate/resolver.py",           "name resolver v2 (gbif_names / name2sid / species hub)"),
    ("00_substrate/vernacular.py",         "English common names from the backbone dump"),
    ("20_derive/normalized_tables.py",     "species_trophic_roles / species_habitats"),
    ("20_derive/crosswalks.py",            "trait vocab crosswalks (cached; offline after first run)"),
    ("20_derive/fieldnote_cleanup.py",     "field-note heading/measurement/tone cleanup"),
    ("20_derive/facts_disambiguation.py",  "one accepted species per note"),
    # spatial layers BEFORE trait sources: some source notebooks' analysis cells
    # join species_ecoregions (caught by the clean-rebuild test)
    ("20_derive/resolve_rejoin.py",        "occurrences×RESOLVE license-filtered + GARD reptiles (LONG: S3 + spatial)"),
    ("20_derive/phylacine.py",             "PHYLACINE mammal ranges → ecoregions + pure mammal_ranges (LONG: 5,831 rasters)"),
    ("20_derive/gard_ranges.py",           "pure GARD reptile_ranges (spatial join; range filter input)"),
    ("20_derive/ecoregion_area.py",        "ecoregion areas (density tiebreak for primary biome)"),
    ("20_derive/plant_lifeform.py",        "WCVP growth forms -> plant_lifeform (Tree/Shrub/Herb/... deck groups)"),
    ("10_sources/avonet.py",               "birds: AVONET"),
    ("10_sources/elton.py",                "mammals: EltonTraits"),
    ("10_sources/wcvp.py",                 "plants: WCVP native origin"),
    ("10_sources/amphibio.py",             "amphibians: AmphiBIO"),
    ("10_sources/repttraits.py",           "reptiles: ReptTraits"),
    ("10_sources/eol_height.py",           "plant/fungi height from EOL dump"),
    ("10_sources/eol_mollusc_mass.py",     "mollusc body mass from EOL dump"),
    ("10_sources/tetrapodtraits.py",       "TetrapodTraits + bird/amphibian biome"),
    ("10_sources/animaltraits_globifeed.py","AnimalTraits inverts + GloBI-derived feeding"),
    ("10_sources/insect_traits.py",        "LepTraits + OPD + World Spider Traits (needs dl_wst.py dump)"),
    ("10_sources/fish_traits_cc.py",       "CC fish traits: Beukhof (CC-BY) + FishTraits (CC0) + Parravicini (MIT/CC-BY) — the FishBase replacement"),
    ("10_sources/diet_categories.py",      "categorical diet (Elton shares + TetrapodTraits presence) for Q4 fallback"),
    ("10_sources/traits_wide.py",          "WIDE ingest: every usable column of every source → traits_long (question discovery)"),
    # occurrence_points_scan.py (S3 scan, ~2.5h) refreshes data/deck_obs_points.parquet —
    # the 1 km cells the map's Xs draw; ALL FOUR scans must carry the same
    # sightings-only basisofrecord filter (2026-09-27);
    # occurrence_grid_full.py (3h S3 scan) refreshes data/occurrence_ecoregions_full.parquet;
    # the parquet is a versioned derived artifact, so the chain consumes it directly:
    ("20_derive/species_ecoregions_rebuild.py", "species_ecoregions from CLEAN parts: mammal_ranges ∪ reptile_ranges ∪ sightings-only scan"),
    ("20_derive/occurrence_integrate.py",  "merge FULL occurrence run into species_ecoregions"),
    ("20_derive/species_popularity.py",    "observation counts per species (from occ grid)"),
    ("30_output/fetch_wikidata_fame.py",   "global fame = Wikidata sitelinks for deck species (cached; network for new ids)"),
    ("30_output/load_species_fame.py",     "materialize species_fame from cached wiki_fame.json + sitelinks"),
    ("30_output/generate_catalog.py",      "THE catalog generator → 30_output/catalog.json"),
    ("30_output/export_range_fill.py",     "map fill layer: every ecoregion, weighted by record share (no cutoff)"),
    ("30_output/export_eco_meta.py",       "ecoregion name + Wikipedia lead + habitat photo -> explorer (cached inputs)"),
    ("30_output/export_coverage.py",       "coverage.json for the explorer Coverage tab (incl. the Fish synthetic class)"),
    ("30_output/fetch_trails.py",        "NPS Public Trails -> explorer map (cached; network once)"),
    ("30_output/fetch_peaks.py",         "Natural Earth named mountains -> explorer map (cached; network once)"),
    ("30_output/fetch_lakes.py",         "Natural Earth 50m lakes -> explorer maps (cached; network once)"),
    ("30_output/export_park_obs.py",      "observation counts: parks (deck obs cells in-bounds) + ecoregions -> explorer"),
    ("30_output/export_park_species.py",  "park states (NE admin-1) + per-park deck species -> park_species.json"),
    ("30_output/export_photos.py",         "photos.json: card id → Wikimedia CDN thumb for the eco All view (cached; network for new cards)"),
    ("30_output/audit.py",                 "coverage audit (optional, reporting only)"),
]

def main():
    args = sys.argv[1:]
    if "--list" in args:
        for s, note in CHAIN: print(f"  {s:42} {note}")
        return
    start = 0
    if "--from" in args:
        key = args[args.index("--from") + 1]
        start = next(i for i, (s, _) in enumerate(CHAIN) if key in s)
    t0 = time.time()
    for s, note in CHAIN[start:]:
        print(f"\n=== {s} — {note} ({time.time()-t0:.0f}s elapsed)", flush=True)
        r = subprocess.run([PY, os.path.basename(s)], cwd=os.path.join(ROOT, os.path.dirname(s)))
        if r.returncode != 0:
            sys.exit(f"FAILED at {s} (exit {r.returncode}) — resume with: run_all.py --from {os.path.basename(s)[:-3]}")
    print(f"\nDONE ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
