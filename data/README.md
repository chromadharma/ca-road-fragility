# Data

Nothing under `data/raw/` or `data/interim/` is committed. `python scripts/fetch.py all`
downloads every raw file below; the OSM road graphs are pulled by osmnx during
the Part B run and cached in `data/raw/osmnx_cache/`.

| File (under `data/raw/`) | Source | Access | Licence |
|---|---|---|---|
| `snap/roadNet-CA.txt.gz` | SNAP, Stanford: California road network (Leskovec et al. 2009) | https://snap.stanford.edu/data/roadNet-CA.html | None stated. Cite the paper |
| `dimacs/USA-road-d.CAL.{gr,co}.gz` | 9th DIMACS Implementation Challenge, "CAL" (California **and Nevada**) | http://www.diag.uniroma1.it/challenge9/download.shtml | None stated; derived from TIGER/Line |
| `tiger/cb_2024_us_state_500k.zip` | US Census cartographic boundary, states | www2.census.gov/geo/tiger/GENZ2024 (1:500k) | Public domain |
| `tiger/tl_2024_06_place.zip` | TIGER/Line 2024, places, California | www2.census.gov/geo/tiger/TIGER2024/PLACE | Public domain |
| `tiger/tl_2020_06_tabblock20.zip` | TIGER/Line 2020, blocks, California | www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20 | Public domain |
| `census/ca2020.pl.zip` | 2020 Census PL 94-171 redistricting file, California | www2.census.gov/programs-surveys/decennial/2020/data | Public domain |
| `calfire/fhsz_sra_2024.geojson` | CAL FIRE Fire Hazard Severity Zones, SRA, effective 1 Apr 2024 (`FHSZSRA_23_3`) | ArcGIS REST, `services1.arcgis.com/jUJYIo9tSA7EHvfZ` | CC-BY |
| `calfire/fhsz_lra_2025.geojson` | CAL FIRE FHSZ, LRA, recommended 24 Mar 2025 (`FHSZLRA25_v1_All`) | same service root (URL spelled `FHSALRA25_v1_All`) | CC-BY |
| `calfire/fire_perimeters_firep25_1.geojson` | CAL FIRE FRAP fire perimeters, release firep25_1 (Apr 2026) | same service root | CC-BY |
| `la/csa_communities.geojson` | LA County Countywide Statistical Areas | `public.gis.lacounty.gov/.../Political_Boundaries/MapServer/23` | LA County open data |
| `butte_gp/gp2040_p251_HS16.jpg` | Butte County General Plan 2040, Health & Safety Element, Figure HS-16 (for the SB 99 comparison) | `online.encodeplus.com/regs/buttecounty-ca/ereader/20231002generalplan2040/files/mobile/251.jpg` | Public record; not redistributed |
| `osm/socal-latest.osm.pbf` | Geofabrik Southern California extract (LA roads; Overpass failed) | https://download.geofabrik.de/north-america/us/california/socal-latest.osm.pbf | ODbL |
| `osmnx_cache/` | OpenStreetMap via Overpass | osmnx | ODbL |

ACS vehicles-available (table B25044) is requested from the Census API with the
key in `.env` (`CENSUS_API_KEY`), which is not committed.

## Known gaps
- SNAP gives no date or source for its road data.
- DIMACS CAL includes Nevada. Part A clips it with the Census state outline.
- The FRAP perimeter data is, in CAL FIRE's words, incomplete. Two 2018 fires
  are both named "CAMP", so filter by unit (`BTU`), not by name alone.
- The LRA hazard map is "recommended"; local adoption varies.
