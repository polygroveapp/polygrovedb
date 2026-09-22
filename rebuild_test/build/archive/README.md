# Archived notebooks — retired from the build chain

Kept for project history; **none of these run in `run_all.py`**, and the three
NC ones must never return (PolygroveDB is CC-BY/CC0 only — see data/LICENSES.md).

| Notebook | Why retired |
|---|---|
| `11_crypticbio_confusions.py` | **CC-BY-NC** (CrypticBio). Q6 look-alikes now derived from GBIF+RESOLVE in the generator. |
| `23_crypticbio_full.py` | **CC-BY-NC** (CrypticBio full ingest). Its dump + DB tables were deleted in the 2026-08 license audit. |
| `20_fishbase.py` | **CC-BY-NC** (FishBase). Would re-contaminate the DB on a re-run — fish left the deck with the audit. |
| `06_occurrences_ecoregions.py` | Superseded by `20_derive/resolve_rejoin.py` (license-filtered occurrences + RESOLVE + GARD). |
| `22_card_generator.py` | Old 15-species demo generator; superseded by `30_output/generate_catalog.py`. Queries dropped NC tables. |
| `10_question_scorecard.py` | Question-viability analysis; conclusions locked (see memory / build plan), code is a snapshot. |
| `12_seasonality_origin.py` | Exploration; origin now comes from WCVP, seasonality unused. |
| `13_size_audio.py` | Exploration; raw EOL size dropped (unitless) in favor of unit-tagged sources. |
| `14_trait_discovery.py` | One-off scan that surfaced the trait sources now in `10_sources/`. |
| `generated_cards.json` | Output of the retired demo generator. |

## Old numbered name → current location

| Old | Now |
|---|---|
| 01_build_substrate | 00_substrate/backbone.py |
| 02_resolve_and_fieldnotes | 20_derive/wiki_fieldnotes.py |
| 03_resolve_names | 00_substrate/resolver.py |
| 04_normalized_tables | 20_derive/normalized_tables.py |
| 05_crosswalks | 20_derive/crosswalks.py |
| 07_audit | 30_output/audit.py |
| 08_fieldnote_cleanup | 20_derive/fieldnote_cleanup.py |
| 09_facts_disambiguation | 20_derive/facts_disambiguation.py |
| 15_avonet_convergence | 10_sources/avonet.py |
| 16_elton_mammals | 10_sources/elton.py |
| 17_wcvp_origin | 10_sources/wcvp.py |
| 19_amphibio | 10_sources/amphibio.py |
| 21_repttraits | 10_sources/repttraits.py |
| 24_generate_catalog | 30_output/generate_catalog.py |
| 25_plant_fungi_size | 10_sources/eol_height.py |
| 26_resolve_rejoin | 20_derive/resolve_rejoin.py |
| 27_phylacine | 20_derive/phylacine.py |
| 28_tetrapodtraits | 10_sources/tetrapodtraits.py |
| 29_animaltraits_globifeed | 10_sources/animaltraits_globifeed.py |
| 30_insect_traits | 10_sources/insect_traits.py |
