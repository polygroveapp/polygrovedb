# %% [markdown]
# # PolygroveDB — the WIDE ingest: every usable column of every on-disk source → traits_long
#
# Q3 (size) was axed; the 6th question slot is open. To find its replacement we need to
# SEE what measured, CC-BY/CC0 data actually exists per species — not the ~10% of columns
# the card generator happened to use. This unpivots all of it into one long table:
#   traits_long(species_id, source, trait, value, value_num, unit)
# Measured only: TetrapodTraits imputed flags respected; class/phylum gates everywhere a
# name collision could paste data onto the wrong organism. Wikipedia: none (rule).

# %%
import duckdb, pandas as pd, time, re
t0=time.time()
con=duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
con.sql("CREATE OR REPLACE TABLE traits_long (species_id BIGINT, source VARCHAR, trait VARCHAR, val VARCHAR, value_num DOUBLE, unit VARCHAR)")
REPT="('Squamata','Testudines','Crocodylia','Rhynchocephalia','Sphenodontia')"

def ingest(view, source, sci_col, gate_sql, cols, units=None):
    """cols: list of (column, trait_label). gate_sql: e.g. "s.class='Aves'". Unpivot → traits_long."""
    units=units or {}
    q=lambda c: '"'+c.replace('"','""')+'"'     # identifiers may contain double quotes (ReptTraits)
    sel=" UNION ALL ".join(
        f"SELECT n.species_id, '{lbl}' trait, trim(CAST(v.{q(col)} AS VARCHAR)) val, '{units.get(lbl,'')}' unit "
        f"FROM {view} v JOIN name2sid n ON n.norm_name=norm(CAST(v.{q(sci_col)} AS VARCHAR)) "
        f"JOIN species s ON s.species_id=n.species_id AND ({gate_sql})"
        for col,lbl in cols)
    con.sql(f"""INSERT INTO traits_long
      SELECT species_id, '{source}', trait, val, TRY_CAST(val AS DOUBLE), unit
      FROM ({sel}) WHERE val IS NOT NULL AND val NOT IN ('','NA','NaN','nan','None','null','-','?')""")
    n=con.sql(f"SELECT count(*), count(DISTINCT species_id) FROM traits_long WHERE source='{source}'").fetchone()
    print(f"  {source:18} {n[0]:>9,} rows  {n[1]:>7,} species  ({time.time()-t0:.0f}s)", flush=True)

# ---------- TetrapodTraits (measured only) ----------
con.sql("""CREATE OR REPLACE TEMP VIEW tt AS
  SELECT *,
    CASE WHEN TRY_CAST(ImputedActTime AS INT)=0 THEN Diu END AS Diu_m,
    CASE WHEN TRY_CAST(ImputedActTime AS INT)=0 THEN Noc END AS Noc_m,
    CASE WHEN TRY_CAST(ImputedActTime AS INT)=0 THEN Nocturnality END AS Nocturnality_m,
    CASE WHEN TRY_CAST(ImputedHabitat AS INT)=0 THEN Verticality END AS Verticality_m,
    CASE WHEN TRY_CAST(ImputedEcosystem AS INT)=0 THEN EcoTer END AS EcoTer_m,
    CASE WHEN TRY_CAST(ImputedEcosystem AS INT)=0 THEN EcoFresh END AS EcoFresh_m,
    CASE WHEN TRY_CAST(ImputedEcosystem AS INT)=0 THEN EcoMar END AS EcoMar_m,
    CASE WHEN TRY_CAST(ImputedThreatStatus AS INT)=0 THEN AssessedStatus END AS AssessedStatus_m,
    CASE WHEN SourceLongevity IS NOT NULL THEN MaxLongevity END AS MaxLongevity_m,
    CASE WHEN SourceLitterSize IS NOT NULL THEN LitterSize END AS LitterSize_m,
    CASE WHEN SourceViviparity IS NOT NULL THEN Viviparity END AS Viviparity_m,
    CASE WHEN SourceDirectDev IS NOT NULL THEN DirectDev END AS DirectDev_m,
    CASE WHEN SourceLarvalStage IS NOT NULL THEN LarvalStage END AS LarvalStage_m,
    CASE WHEN SourceDiet IS NOT NULL THEN DietBreadth END AS DietBreadth_m
  FROM read_csv('../../data/tetrapodtraits/TetrapodTraits.csv', header=true, ignore_errors=true, sample_size=-1, all_varchar=true)""")
tt_gate="(v.Class='Aves' AND s.class='Aves') OR (v.Class='Mammalia' AND s.class='Mammalia') OR (v.Class='Amphibia' AND s.class='Amphibia') OR (v.Class='Reptilia' AND s.class IN "+REPT+")"
ingest('tt','TetrapodTraits','Scientific.Name',tt_gate,[
  ('Diu_m','active by day'),('Noc_m','active by night'),('Nocturnality_m','nocturnality'),('Verticality_m','verticality'),
  ('EcoTer_m','ecosystem terrestrial'),('EcoFresh_m','ecosystem freshwater'),('EcoMar_m','ecosystem marine'),
  ('AssessedStatus_m','IUCN status'),('PopulationTrend','population trend'),('RangeSize_km2','range size'),
  ('Insularity','island species'),('AnnuMeanTemp','mean annual temperature'),('AnnuPrecip','annual precipitation'),
  ('Elevation','elevation'),('HumanDensity','human density in range'),('PropUrbanArea','urban share of range'),
  ('MaxLongevity_m','max longevity'),('LitterSize_m','litter size'),('Viviparity_m','live birth'),
  ('DirectDev_m','direct development'),('LarvalStage_m','larval stage'),('DietBreadth_m','diet breadth'),
  ('Afrotropic','realm afrotropic'),('Australasia','realm australasia'),('IndoMalay','realm indomalay'),('Nearctic','realm nearctic'),
  ('Neotropic','realm neotropic'),('Oceania','realm oceania'),('Palearctic','realm palearctic')],
  units={'range size':'km2','mean annual temperature':'C','annual precipitation':'mm','elevation':'m','max longevity':'years'})

# ---------- AVONET (BirdLife taxonomy sheet) ----------
av=pd.read_excel('../../data/avonet.xlsx', sheet_name='AVONET1_BirdLife'); con.register('av_df', av)
ingest('av_df','AVONET','Species1',"s.class='Aves'",[
  ('Beak.Length_Culmen','beak length'),('Beak.Width','beak width'),('Beak.Depth','beak depth'),('Tarsus.Length','tarsus length'),
  ('Wing.Length','wing length'),('Kipps.Distance','kipps distance'),('Hand-Wing.Index','hand-wing index'),('Tail.Length','tail length'),
  ('Habitat','habitat'),('Habitat.Density','habitat density'),('Migration','migration'),('Trophic.Level','trophic level'),
  ('Trophic.Niche','trophic niche'),('Primary.Lifestyle','primary lifestyle'),('Range.Size','range size'),
  ('Min.Latitude','min latitude'),('Max.Latitude','max latitude')],
  units={'beak length':'mm','beak width':'mm','beak depth':'mm','tarsus length':'mm','wing length':'mm','kipps distance':'mm','tail length':'mm','range size':'km2'})

# ---------- EltonTraits ----------
con.sql("CREATE OR REPLACE TEMP VIEW eb AS SELECT * FROM read_csv('../../data/elton_BirdFuncDat.txt', delim='\\t', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
ingest('eb','EltonTraits','Scientific',"s.class='Aves'",[
  ('ForStrat-watbelowsurf','forages below water surface'),('ForStrat-wataroundsurf','forages at water surface'),('ForStrat-ground','forages on ground'),
  ('ForStrat-understory','forages in understory'),('ForStrat-midhigh','forages mid-high'),('ForStrat-canopy','forages in canopy'),
  ('ForStrat-aerial','forages aerially'),('PelagicSpecialist','pelagic specialist'),('Nocturnal','nocturnal')])
con.sql("CREATE OR REPLACE TEMP VIEW em AS SELECT * FROM read_csv('../../data/elton_MamFuncDat.txt', delim='\\t', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
ingest('em','EltonTraits','Scientific',"s.class='Mammalia'",[
  ('ForStrat-Value','foraging stratum'),('Activity-Nocturnal','active by night'),('Activity-Crepuscular','active at twilight'),('Activity-Diurnal','active by day')])

# ---------- AmphiBIO ----------
con.sql("CREATE OR REPLACE TEMP VIEW am AS SELECT * FROM read_csv('../../data/AmphiBIO_v1.csv', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
ingest('am','AmphiBIO','Species',"s.class='Amphibia'",[
  ('Fos','fossorial'),('Ter','terrestrial'),('Aqu','aquatic'),('Arb','arboreal'),('Leaves','eats leaves'),('Flowers','eats flowers'),('Seeds','eats seeds'),
  ('Fruits','eats fruit'),('Arthro','eats arthropods'),('Vert','eats vertebrates'),('Diu','active by day'),('Noc','active by night'),('Crepu','active at twilight'),
  ('Wet_warm','active wet-warm season'),('Wet_cold','active wet-cold season'),('Dry_warm','active dry-warm season'),('Dry_cold','active dry-cold season'),
  ('Age_at_maturity_min_y','age at maturity min'),('Age_at_maturity_max_y','age at maturity max'),('Longevity_max_y','max longevity'),
  ('Litter_size_min_n','litter size min'),('Litter_size_max_n','litter size max'),('Reproductive_output_y','reproductive output per year'),
  ('Offspring_size_min_mm','offspring size min'),('Offspring_size_max_mm','offspring size max'),('Dir','direct development'),('Lar','larval stage'),('Viv','live birth')],
  units={'age at maturity min':'years','age at maturity max':'years','max longevity':'years','offspring size min':'mm','offspring size max':'mm'})

# ---------- ReptTraits ----------
rt=pd.read_excel('../../data/repttraits.xlsx', sheet_name='Data'); rt.columns=[str(c).strip() for c in rt.columns]; con.register('rt_df', rt)
ingest('rt_df','ReptTraits','Species',"s.class IN "+REPT,[
  ('Main biogeographic region','biogeographic region'),('Microhabitat','microhabitat'),('Habitat type','habitat type'),
  ('Minimal elevation (m)','elevation min'),('Maximum elevation (m)','elevation max'),('Mean Annual Temperature (°C)','mean annual temperature'),
  ('Insular/endemic (yes or no)','island endemic'),('Venomous (yes or no)','venomous'),('Diet','diet'),('Active time','active time'),
  ('Dorsal colour','dorsal colour'),('Dorsal pattern','dorsal pattern'),('Foraging mode','foraging mode'),('Pupil Shape','pupil shape'),('Fangs','fangs'),
  ('Maximum Longevity (years)','max longevity'),('Maximum body mass (g)','max body mass'),('Maximum total length ("TL", mm)','max total length'),
  ('Reproductive mode','reproductive mode'),('Sex-determining mechanism (GSD or TSD)','sex determination'),
  ('Mean number of offspring per litter or number of eggs per clutch','clutch size mean'),('Smallest clutch size','clutch size min'),('Largest clutch size','clutch size max'),
  ('Number of litters or clutches produced per year','clutches per year'),('Egg length (mm)','egg length'),('Egg width (mm)','egg width'),
  ('Mean Tb','body temperature'),('IUCN redlist assessment','IUCN status'),('IUCN population trend','population trend')],
  units={'elevation min':'m','elevation max':'m','mean annual temperature':'C','max longevity':'years','max body mass':'g','max total length':'mm','egg length':'mm','egg width':'mm','body temperature':'C'})

# ---------- LepTraits ----------
con.sql("CREATE OR REPLACE TEMP VIEW lt AS SELECT * FROM read_csv('../../data/leptraits/LepTraits-main/consensus/consensus.csv', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
ingest('lt','LepTraits','Species',"s.class='Insecta'",[(m,f'flies in {m}') for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']]+[
  ('FlightDuration','flight season length'),('DiapauseStage','diapause stage'),('Voltinism','broods per year'),('OvipositionStyle','egg-laying style'),
  ('CanopyAffinity','canopy affinity'),('EdgeAffinity','edge affinity'),('MoistureAffinity','moisture affinity'),('DisturbanceAffinity','disturbance affinity'),
  ('NumberOfHostplantFamilies','hostplant families'),('PrimaryHostplantFamily','primary hostplant family')], units={'flight season length':'months'})

# ---------- WCVP (plants): lifeform + climate ----------
con.sql("""CREATE OR REPLACE TEMP VIEW wn AS SELECT * FROM read_csv('../../data/wcvp_names.csv', delim='|', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)
  WHERE taxon_status='Accepted' AND taxon_rank='Species'""") if __import__('os').path.exists('../../data/wcvp_names.csv') else \
con.sql("""CREATE OR REPLACE TEMP VIEW wn AS SELECT * FROM read_csv('../../_scratch/wcvp_names.csv', delim='|', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)
  WHERE taxon_status='Accepted' AND taxon_rank='Species'""")
ingest('wn','WCVP','taxon_name',"s.kingdom='Plantae'",[('lifeform_description','plant lifeform'),('climate_description','climate')])

# ---------- Odonate Phenotypic DB ----------
con.sql("CREATE OR REPLACE TEMP VIEW od AS SELECT * FROM read_csv('../../data/opd/OPD_mergeDataReduced.csv', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
ingest('od','Odonate Phenotypic DB','GenusSpecies',"s.class='Insecta'",[
  ('body_colors','body colour'),('body_patterns','body pattern'),('flight_mode','flight mode'),('territoriality','territoriality'),('mate_guarding','mate guarding'),
  ('aquatic_habitats','aquatic habitat'),('habitat_openness','habitat openness'),('sex_dimorphisms','sex dimorphism'),('has_wing_pigment','wing pigment'),('wing_pigment_color','wing pigment colour')])

# ---------- World Spider Traits (non-morphometric categories) ----------
con.sql("""CREATE OR REPLACE TEMP VIEW ws AS
  SELECT taxonomy.genus||' '||taxonomy.species AS sci, trait.name AS tname, trait.category.name AS cat,
         coalesce(CAST(value AS VARCHAR), '') AS val
  FROM read_json('../../data/spidertraits/wst_records.jsonl', format='newline_delimited', ignore_errors=true)
  WHERE trait.category.name <> 'Morphometry'""")
con.sql("""INSERT INTO traits_long
  SELECT n.species_id, 'World Spider Traits', lower(w.tname), mode(w.val), TRY_CAST(mode(w.val) AS DOUBLE), ''
  FROM ws w JOIN name2sid n ON n.norm_name=norm(w.sci) JOIN species s ON s.species_id=n.species_id AND s.class='Arachnida'
  WHERE w.val<>'' GROUP BY 1,2,3""")
n=con.sql("SELECT count(*), count(DISTINCT species_id) FROM traits_long WHERE source='World Spider Traits'").fetchone()
print(f"  {'World Spider Traits':18} {n[0]:>9,} rows  {n[1]:>7,} species  ({time.time()-t0:.0f}s)", flush=True)

# ---------- EOL numeric predicates, labeled via terms.csv ----------
con.sql("CREATE OR REPLACE TEMP VIEW terms AS SELECT * FROM read_csv('../../data/trait_bank/terms.csv', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
con.sql("""INSERT INTO traits_long
  SELECT n.species_id, 'EOL TraitBank', lower(coalesce(tm.name, regexp_replace(t.predicate,'^.*[/#]',''))), t.normal_measurement,
         TRY_CAST(t.normal_measurement AS DOUBLE), coalesce(t.normal_units,'')
  FROM read_csv('../../data/trait_bank/traits.csv', header=true, quote='"', ignore_errors=true, all_varchar=true) t
  JOIN name2sid n ON n.norm_name=norm(t.scientific_name)
  LEFT JOIN terms tm ON tm.uri=t.predicate
  WHERE TRY_CAST(t.normal_measurement AS DOUBLE) IS NOT NULL
    AND t.predicate NOT LIKE '%decimalLatitude%' AND t.predicate NOT LIKE '%decimalLongitude%'""")
n=con.sql("SELECT count(*), count(DISTINCT species_id) FROM traits_long WHERE source='EOL TraitBank'").fetchone()
print(f"  {'EOL TraitBank':18} {n[0]:>9,} rows  {n[1]:>7,} species  ({time.time()-t0:.0f}s)", flush=True)

r=con.sql("SELECT count(*), count(DISTINCT species_id), count(DISTINCT trait) FROM traits_long").fetchone()
print(f"\ntraits_long TOTAL: {r[0]:,} rows · {r[1]:,} species · {r[2]:,} distinct traits  ({time.time()-t0:.0f}s)")
con.close()

# %% [markdown]
# ## EOL categorical predicates (added after the coverage audit found them untapped:
# circadian rhythm, plant growth form, conservation status reach plants/inverts that
# no other source covers)

# %%
con=duckdb.connect("../../polygrove.duckdb")
con.sql(r"""CREATE OR REPLACE MACRO norm(s) AS
  lower(array_to_string(list_filter(string_split(regexp_replace(coalesce(s,''),'\([^)]*\)','','g'),' '),
  x -> x <> '' AND lower(x) NOT IN ('subsp.','ssp.','var.','f.','subvar.'))[1:2],' '));""")
t1=time.time()
con.sql("DELETE FROM traits_long WHERE source='EOL categorical'")
con.sql("CREATE OR REPLACE TEMP VIEW terms AS SELECT * FROM read_csv('../../data/trait_bank/terms.csv', header=true, ignore_errors=true, all_varchar=true, sample_size=-1)")
con.sql("""INSERT INTO traits_long
  SELECT n.species_id, 'EOL categorical', tm.name, coalesce(tv.name, t.literal), NULL, ''
  FROM read_csv('../../data/trait_bank/traits.csv', header=true, quote='"', ignore_errors=true, all_varchar=true) t
  JOIN name2sid n ON n.norm_name=norm(t.scientific_name)
  JOIN terms tm ON tm.uri=t.predicate
  LEFT JOIN terms tv ON tv.uri=t.value_uri
  WHERE tm.name IN ('behavioral circadian rhythm','plant growth form','life cycle habit','shedability',
                    'conservation status','population trend','motility','parental care','social system',
                    'mating system','body shape','trophic level')
    AND coalesce(tv.name, t.literal) IS NOT NULL AND trim(coalesce(tv.name, t.literal)) <> ''""")
n=con.sql("SELECT count(*), count(DISTINCT species_id) FROM traits_long WHERE source='EOL categorical'").fetchone()
print(f"  {'EOL categorical':18} {n[0]:>9,} rows  {n[1]:>7,} species  ({time.time()-t1:.0f}s)")
con.close()
