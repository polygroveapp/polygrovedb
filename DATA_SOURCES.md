# PolygroveDB — Data Source Licenses

PolygroveDB is an **open scientific database**: every source must be **CC-BY or CC0**
(commercial-OK, redistributable, interoperable). Non-commercial (CC-BY-NC) sources were
audited out on 2026-08-07 — see "Dropped" below. Attribution for all CC-BY sources flows
through to the cards' source links.

## ✅ In use — CC-BY / CC0

| Source | Powers | License | Link |
|---|---|---|---|
| GBIF Backbone Taxonomy | Taxonomy (Q1) | CC-BY 4.0 | https://doi.org/10.15468/39omei |
| GBIF Occurrences *(filtered to CC0/CC-BY records only)* | Biome / location | CC0 + CC-BY | https://www.gbif.org/occurrence |
| GloBI (Global Biotic Interactions) | Food web (Q4) | CC-BY 4.0 | https://www.globalbioticinteractions.org |
| AVONET (Tobias et al. 2022) | Bird traits | CC-BY 4.0 | https://doi.org/10.6084/m9.figshare.16586228 |
| EltonTraits 1.0 (Wilman et al. 2014) | Mammal/bird diet, mass | CC-BY (Ecol. Archives) | https://doi.org/10.1890/13-1917.1 |
| WCVP (Kew World Checklist of Vascular Plants) | Plant native origin | CC-BY 4.0 | https://powo.science.kew.org |
| AmphiBIO (Oliveira et al. 2017) | Amphibian traits | CC-BY 4.0 | https://doi.org/10.6084/m9.figshare.4644424 |
| ReptTraits (Oskyrko et al. 2024) | Reptile traits | CC-BY 4.0 | https://doi.org/10.6084/m9.figshare.24572683 |
| EOL TraitBank | Body size, plant/fungi height | CC-BY 4.0¹ | https://opendata.eol.org |
| GARD 1.7 (Roll et al. / Meiri) | Reptile ranges → biome | CC0 | https://doi.org/10.5061/dryad.9cnp5hqmb |
| PHYLACINE 1.2 (Faurby et al. 2018) | Mammal ranges → biome | CC0 | https://github.com/MegaPast2Future/PHYLACINE_1.2 |
| RESOLVE Ecoregions 2017 (Dinerstein et al.) | Ecoregion/biome polygons | CC-BY 4.0 | https://ecoregions.appspot.com |
| TetrapodTraits v2 (Moura et al. 2024) | Bird/amphibian/reptile/mammal traits + biome | CC-BY 4.0 | https://zenodo.org/records/18926700 |
| AnimalTraits (Herberstein et al. 2022) | Invertebrate (insect/arachnid/mollusc) body mass | CC-BY 4.0 | https://animaltraits.org |
| LepTraits 1.0 (Shirey et al. 2022) | Butterfly wingspan + hostplant herbivory | CC-BY 4.0 | https://doi.org/10.6084/m9.figshare.c.5899187 |
| Odonate Phenotypic Database (Waller et al. 2019) | Dragonfly/damselfly body length | CC0 (Dryad)³ | https://doi.org/10.5061/dryad.15pm5qc |
| World Spider Trait database (Pekár et al. 2021) | Spider body length | CC-BY 4.0 | https://spidertraits.sci.muni.cz |
| Beukhof et al. 2019 marine fish traits | Fish trophic level, max length, habitat (N Atl/NE Pac shelf) | CC-BY 4.0⁴ | https://doi.org/10.1594/PANGAEA.900866 |
| FishTraits 14.3 (Frimpong & Angermeier, USGS) | US freshwater fish diet + max length | CC0-1.0 | https://www.sciencebase.gov/catalog/item/5a7c6e8ce4b00f54eb2318c0 |
| Parravicini et al. 2020 reef fish guilds | Reef fish trophic guild (30-expert consensus) | MIT (repo) / CC-BY 4.0 (paper)⁵ | https://github.com/valerianoparravicini/Trophic_Fish_2020 |
| FISHMORPH (Brosse et al. 2021) | Freshwater fish max body length | CC-BY 4.0⁶ | https://doi.org/10.6084/m9.figshare.14891412 |
| Wikidata / EBI OLS | Trait-vocabulary crosswalk labels | CC0 | https://www.wikidata.org |
| Wikipedia | Sourced-card sentence + photo (**app runtime only, never stored in the DB**) | CC-BY-SA² | https://www.wikipedia.org |

¹ EOL TraitBank is CC-BY as distributed, but aggregates 50+ sources with per-record licenses — a
   future rigor step is to filter EOL records to CC-BY/CC0 source-resources (some trace to NC sources).
² CC-BY-SA is share-alike (viral to derivatives). Kept out of the CC-BY database; lives only in the
   Polygrove **app** at runtime, satisfied by attribution + a link to the article.
³ Dryad file downloads are now bearer-token-gated; the CC0 dump was obtained from the OPD authors'
   own public app repository (github.com/jhnwllr/shiny-server, `odonates/mergeDataReduced.csv`).
⁴ License verified machine-readably (PANGAEA metadata_jsonld `license` field, 2026-09-09). The
   collection was compiled partly from FishBase, but PANGAEA's publisher license (CC-BY 4.0) governs
   this redistribution.
⁵ Repo LICENSE.md is MIT (permissive, attribution-preserving); the paper (PLoS Biol 3000702) and its
   published data are CC-BY 4.0. We ingest `data/converted_experts_classification.csv` (the 30
   standardized expert classifications), not the RData model outputs.
⁶ License verified via the figshare API (`GET /v2/articles/14891412` → license "CC BY 4.0",
   2026-09-09); the figshare web page itself blocks robots. Authors ask that FISHMORPH and each
   primary dataset be cited — satisfied by the cards' source links.

## ❌ Dropped — non-commercial (CC-BY-NC), incompatible with an open DB

| Source | Was powering | License | Link |
|---|---|---|---|
| CrypticBio | Q6 look-alikes + 54k common names | CC-BY-NC 4.0 | https://huggingface.co/datasets/gmanolache/CrypticBio |
| FishBase | Fish diet/size/habitat | CC-BY-NC 4.0 | https://www.fishbase.org/terms |
| WWF Terrestrial Ecoregions (Olson 2001) | Biome polygons (→ replaced by RESOLVE) | CC-BY-NC 3.0 | https://www.worldwildlife.org/ecoregions |

## 🔒 Evaluated but NOT usable — non-commercial / gated

| Source | Would help | Why not |
|---|---|---|
| BirdLife (BOTW) bird ranges | Birds (biggest gap) | Non-commercial; commercial only via paid IBAT |
| IUCN Red List spatial | Amphibian/mammal ranges | Non-commercial terms + registration-gated |
| TRY plant traits (dataset 81) | More plant heights | Restrictive data policy, request-gated |
| MEOW — Marine Ecoregions of the World (Spalding 2007) | Marine biome (sea turtles, marine life) | CC-BY-NC — no clean CC-BY marine-ecoregion equivalent exists |

## 🔎 Untapped candidate — CC-BY, high value (not yet ingested)

| Source | Would add | License | Link |
|---|---|---|---|
| **TetrapodTraits v2 (Moura et al. 2024)** | Traits **+ biogeography** for all 33,281 tetrapods → could unlock **birds + amphibians** (the current dead-ends), CC-BY | CC-BY 4.0 | https://zenodo.org/records/18926700 |

*Note: TetrapodTraits uses phylogeny-based imputation for gaps — use the measured values, flag/exclude
imputed ones; the biogeography fields are range-based (unbiased).*
