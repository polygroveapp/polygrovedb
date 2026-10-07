# PolygroveDB build pipeline

Percent-format (`# %%`) Python notebooks, organized as a pipeline DAG.
**Execution order lives in one place: `run_all.py`** (the directory numbers are
stages, not step numbers). Run with the miniconda python
(`/opt/homebrew/Caskroom/miniconda/base/bin/python3` — has duckdb/pandas/rasterio).

```
00_substrate/   the foundation everything joins against
  backbone.py       GBIF backbone taxonomy, RESOLVE ecoregions, EOL trait load
  resolver.py       name-resolution v2: gbif_names + name2sid + species hub
10_sources/     ONE notebook per trait source (license in data/LICENSES.md)
  avonet.py         birds            elton.py            mammals
  wcvp.py           plant origin     amphibio.py         amphibians
  repttraits.py     reptiles         eol_height.py       plant/fungi height
  tetrapodtraits.py all tetrapods    animaltraits_globifeed.py  inverts + GloBI guilds
  insect_traits.py  LepTraits + Odonata + spiders        dl_wst.py  spider-DB dump script
20_derive/      transforms that combine substrate + sources
  crosswalks.py normalized_tables.py wiki_fieldnotes.py fieldnote_cleanup.py
  facts_disambiguation.py resolve_rejoin.py (occurrences+GARD) phylacine.py
30_output/      what ships
  generate_catalog.py  → catalog.json (the deck; all quiz logic + provenance)
  audit.py             coverage reporting
  wiki_convert.py      {{convert}} measurements as readable text ("35–46 cm") — shared by every
                       Wikipedia-text extractor; `python3 wiki_convert.py` runs its checks
  reextract_convert_notes.py  re-extract only the notes with cut measurements (index seek, minutes)
archive/        retired notebooks — kept for history, NOT in the chain (see its README)
```

The **clean-rebuild test** (the reproducibility proof): fresh DB file, `python3
run_all.py`, diff the new `30_output/catalog.json` against the shipped one.

Old numbered names → new locations are recorded in `archive/README.md`.
