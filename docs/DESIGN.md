# DESIGN — California: who has one way out?

**Repo:** `ca-road-fragility` · **Engine package:** `hazardnet/` · **Author:** Sahasrik Ragani
**Status:** all decisions made (§9), 25 Sep 2026; awaiting your go to build.
Nothing downloaded or built yet.

---

## 1. Question

Which California communities have too little road capacity out, relative to the
people who live there, and how much of that capacity runs through high
fire-hazard land?

This is a planning question more than a fire-science one. Since 2019 California
has required local governments to ask it themselves:

- **SB 99 (2019), Gov. Code §65302(g)(5):** the general plan safety element
  must identify residential developments in hazard areas that lack at least two
  emergency evacuation routes.
  ([bill text](https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=201920200SB99))
- **AB 747 (2019), Gov. Code §65302.15:** the safety element must identify
  evacuation routes and evaluate their capacity, safety and viability under a
  range of scenarios.
  ([bill text](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201920200AB747))

This project runs the same test independently, the same way for every place, so
the results can be compared with what jurisdictions reported. Butte County's
General Plan 2040 answers SB 99 in Figures HS-15 and HS-16. Its text says
several communities have "only one ingress and egress" but does not name them
([page 249](https://online.encodeplus.com/regs/buttecounty-ca/ereader/20231002generalplan2040/files/basic-html/page249.html)).
Those two figures are our first comparison point.

### Why a count of exits isn't enough: Paradise

Paradise (Camp Fire, 8 Nov 2018) had several routes out: Skyway, Clark Road,
Pentz Road and Neal Road. The town was gridlocked because those routes could not
carry everyone leaving at once, not because there was only one road. A metric
that only counts edge-disjoint paths would rank Paradise as fairly safe and miss
the case that motivates the project. The design therefore measures two things:

1. **Redundancy:** how many independent routes out (unit-capacity min cut).
2. **Capacity:** how much traffic those routes can carry (capacity-weighted
   max-flow = min cut, by max-flow/min-cut), compared with the population behind
   them.

### How this relates to cascading failure

There are two separate mechanisms, and the design keeps them apart:

- **Static bottleneck:** more people need to leave than the exit capacity can
  carry. That is enough to explain Paradise and is what the max-flow measure
  captures.
- **Cascade:** fire closes a route, its traffic moves onto the remaining routes,
  and those become overloaded in turn. `remove_and_measure()` captures the first
  step: remove the hazard-exposed edges and recompute capacity (a static N–k
  version).

The two standard cascade models differ in a way that matters for roads:

| | Motter & Lai 2002 | Crucitti, Latora & Marchiori 2004 (CLM) |
|---|---|---|
| Overloaded node | Removed from the network | Kept, but its links are **degraded**: link efficiency × C/L |
| Damage measure | Size of the largest connected piece | **Global efficiency** E (Latora & Marchiori 2001): the average of 1/(path length) over all pairs |
| Load | Betweenness | Betweenness over most-efficient paths |
| Capacity | C = α·L(0) | C = α·L(0) |

**CLM fits evacuation better.** A jammed road doesn't disappear: it slows down,
and drivers who can see that switch to other routes. That is CLM's rule, where
flow avoids congested nodes but they stay in the network. In Paradise the roads
were mostly open but gridlocked, which is degradation, not removal.

What CLM gives this project:

1. **Efficiency as a damage measure (adopted now).** E counts a disconnected pair
   as 1/∞ = 0, so a community cut off by removal adds zero instead of an
   infinite travel time that has to be special-cased. It also registers what
   the largest-component measure misses: road networks rarely split apart; they
   force longer detours. Added to Part A and Part B (§3, §5).
2. **A sharper Part A prediction (adopted now).** CLM found that the western US
   power grid has a narrow, exponential *degree* distribution but a *load*
   distribution close to a power law (their Fig. 4). That made the grid stable
   against random failure but vulnerable to losing its single most-loaded node.
   Road networks are narrow in degree as well; if their load is also highly
   uneven, CLM predicts the same split. Part A therefore plots the load
   distribution, not only the removal curves (§5).
3. **A way to measure the cost of uncoordinated routing (proposed, D7).**
   Max-flow is an upper bound: it assumes traffic is spread perfectly over
   every route. Real evacuees each take their own best route and pile onto the
   same few exits. A CLM-style run on Butte, with **physical capacity**
   (lanes × per-lane value) in place of CLM's α·L(0) and **evacuation load**
   (community → safe destinations) in place of all-pairs betweenness, measures
   the gap between what the network could carry and what it carries when
   everyone takes their own best route. That gap is what phased evacuation
   orders and contraflow are meant to close. Because the model is adapted, it
   is labelled "CLM-style", not a replication.

A full simulation of traffic on the roads (microsimulation) stays out of scope
(§8).

---

## 2. Two parts and how they relate

| | Part A: topology baseline | Part B: spatial analysis |
|---|---|---|
| Graph | SNAP roadNet-CA (no coordinates) | OSM via osmnx (geometry, class, lanes, one-way) |
| Asks | How does a road network of California's size break apart under random vs targeted removal? | Which named communities have little exit capacity, and how much of it is in high hazard? |
| Can say | General robustness properties; where the collapse threshold sits | Places, people, hazard exposure |
| Can't say | Anything about where or who; no capacity, direction or hazard | Nothing about network-wide percolation at the state scale |

**How they connect in code:** both run through the same `remove_and_measure()`
loop in `hazardnet/`. Part A removes nodes by rank (random, degree,
betweenness); Part B removes edges by hazard. One engine, two removal rules.

**How they connect in substance (approved, D3):** the 9th
DIMACS Challenge "CAL" graph (verified downloadable, §4) is a road graph of
similar size *with coordinates*. Running the Part A experiment on it would let
us map the links whose removal breaks the network fastest, and then ask whether
those links sit in high-hazard zones. That turns Part A from a separate
side-study into the statewide context for Part B. Caveats: it covers California
**and Nevada** (clip by coordinates), it is derived from older TIGER/Line data,
and its node IDs cannot be matched to SNAP or OSM. The brief was right not to
assume a match.

**Expected Part A result, stated before testing:** road networks have a narrow
degree range (most junctions join 2–4 roads), so removing high-degree junctions
should look almost the same as random removal. Removal by betweenness should
break the network much faster. That contrast with scale-free networks (Albert,
Jeong & Barabási 2000, *Nature* 406, 378–382) is the point of the figure. The
reason would be CLM's: degree is uniform but load (betweenness) is not. The load
distribution is plotted to test that directly. If the data disagree, that goes
in `FINDINGS.md`.

---

## 3. Engine interface: `hazardnet/`

There is no California-specific code in the package. Study settings (county,
hazard layer, thresholds, target definition) live in `studies/<name>/config.yaml`.
Project 2 (Ahmedabad floods) adds `studies/ahmedabad/` and should not need
changes to `hazardnet/`.

```python
roads = load_roads(area, source="osm")            # or source="edgelist" for SNAP/DIMACS
haz   = load_hazard(path_or_url, kind="polygon",  # or kind="raster" (flood depth)
                    field="FHSZ", levels={1: "moderate", 2: "high", 3: "very_high"})
roads = overlay(roads, haz, how="max")            # per-edge hazard attributes
acc   = accessibility(roads, origins=communities, targets=target_rule,
                      measures=["disjoint_paths", "capacity", "travel_time"])
delta = remove_and_measure(roads, mask=roads.hazard_level >= "very_high",
                           measures=acc.measures)
```

**`load_roads()`** returns a `RoadGraph`: geometry, OSM class, `oneway`, `lanes`,
free-flow speed, and a capacity in vehicles/hour. Capacity is imputed from lanes
× a per-lane value by road class when `lanes` is missing; imputed edges are
flagged and the share imputed is reported. Per-lane values will come from a
cited published source (HCM defaults, verified at build time), not from memory.
Storage is geopandas/GeoPackage; computation converts to **igraph** (python-igraph
1.0.0 on PyPI; works on Windows and Mac). No networkx on the large graphs and no
graph-tool.

**`load_hazard()`** accepts a polygon layer with ordinal classes (fire hazard
zones) **or** a raster with continuous values (flood depth, for Project 2), and
returns an object with one method: hazard values along a line.

**`overlay()`** writes the same attributes to every edge whatever the hazard
type: `hazard_max`, plus the share of edge length in each hazard level.

**`accessibility()`** builds a super-source by contracting a community's nodes
and a super-sink by contracting the target nodes, then computes, per community:
- `n_disjoint`: edge-disjoint paths (unit-capacity max-flow);
- `capacity_vph`: capacity-weighted max-flow;
- `people_per_capacity`: population ÷ `capacity_vph` (the pressure measure);
- `tt_min`: shortest free-flow travel time to the target;
- `exposed_share`: share of min-cut capacity on edges at or above the hazard
  threshold;
- `efficiency`: mean of 1/travel-time from the community's nodes to the target
  (Latora–Marchiori efficiency, so a disconnected pair contributes 0).

**`remove_and_measure()`** takes an edge or node mask (or a ranking plus removal
fractions, for Part A), removes those elements, and recomputes. When removal
disconnects a community, its travel time becomes `inf` and it is counted as cut
off, never silently dropped.

---

## 4. Data sources (verified 25 Sep 2026)

Every URL below returned HTTP 200 today unless noted. Sizes are compressed.

| Source | Use | Access | Size | Licence |
|---|---|---|---|---|
| SNAP roadNet-CA | Part A | https://snap.stanford.edu/data/roadNet-CA.txt.gz | 17.9 MB | None stated; cite Leskovec et al. 2009 |
| DIMACS 9th Challenge CAL (distance graph + coordinates) | Part A spatial bridge (D3) | http://www.diag.uniroma1.it/challenge9/data/USA-road-d/USA-road-d.CAL.gr.gz and `…CAL.co.gz` | 27 + 17 MB | None stated; TIGER-derived |
| OSM roads | Part B | osmnx → Overpass (per county) | small per county | ODbL |
| OSM statewide (only if we scale) | Part B statewide | https://download.geofabrik.de/north-america/us/california-latest.osm.pbf | **1.33 GB: needs your approval** | ODbL |
| Fire Hazard Severity Zones, SRA (effective 1 Apr 2024) | Hazard | `services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/FHSZSRA_23_3/FeatureServer/0` | 18,423 polygons | CC-BY (data.ca.gov) |
| Fire Hazard Severity Zones, LRA (recommended 24 Mar 2025) | Hazard | `…/FHSALRA25_v1_All/FeatureServer/0` (the typo "FHSA" is in CAL FIRE's own URL) | 9,752 polygons | CC-BY |
| CAL FIRE FRAP fire perimeters, firep25_1 (released Apr 2026) | Camp Fire validation; sensitivity check | `…/California_Historic_Fire_Perimeters/FeatureServer/0`; bulk GPKG via [data.ca.gov](https://data.ca.gov/dataset/california-fire-perimeters-all) | 23,334 perimeters | CC-BY |
| TIGER/Line 2024 places, CA | Communities | https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_06_place.zip | 9.8 MB | Public domain |
| 2020 Census PL 94-171, CA (block population) | Population | https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/California/ca2020.pl.zip | 80 MB | Public domain |
| TIGER/Line 2020 blocks, CA | Join population to places and outside places | https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_06_tabblock20.zip | 382 MB | Public domain |

Checked and relevant:
- Both fire hazard layers share a schema (`SRA`, `FHSZ` = 1/2/3, `FHSZ_Description`
  = Moderate/High/Very High), so they merge cleanly into one statewide layer.
- The FRAP Camp Fire record is present: `CAMP`, 2018, unit `BTU`, 153,335.6 GIS
  acres. There is a second, unrelated 13.5-acre "CAMP" fire in 2018 (unit `SLU`),
  so filter by unit, not only by name.
- **The Census API now requires a key** (it redirects to `missing_key.html`).
  The bulk PL 94-171 file above avoids that, so no signup is needed.
- **The fire hazard maps are 2024/2025 versions.** That fits the forward-looking
  question ("where is the next Paradise?"). Using them to explain the 2018 fire
  would be anachronistic, so the Camp Fire validation (§6) uses the fire
  perimeter, not the hazard map. The pre-2018 hazard maps (2007 SRA / 2008–11
  LRA) are approved for a "what planners knew in 2018" comparison (D5). Where
  they can be found is in §9.
- **Local-responsibility-area maps are "recommended", not necessarily adopted.**
  Local adoption varies by jurisdiction; recorded as a caveat.

**Dropped: MTBS / dNBR burn severity.** No measure in this design reads it.
Burn severity at 30 m over a road reflects the vegetation beside it, not whether
the road could be driven, and roads in the Camp Fire were closed by the fire
front, abandoned cars, and downed trees and power lines. The fire perimeter
answers the question we actually have ("did this exit edge fall inside the
fire?"). No Google Earth Engine is needed. If we revive it later, the MTBS bulk
perimeter file (390 MB, `edcintl.cr.usgs.gov/.../mtbs_perimeter_data.zip`) was
verified today; the per-state 2018 severity mosaic URL I tried returned 404 and
would need finding.

---

## 5. Method

### Part A
1. Load SNAP as an undirected igraph graph and check it against the stated
   counts (1,965,206 nodes; 2,766,607 edges; largest WCC 1,957,027).
2. Remove nodes in fractions *f* = 0 → 1 under three orders: random (10 seeds),
   degree (ranked once, with random tie-breaks), and betweenness. Betweenness is
   approximated from a random sample of source nodes (igraph's `sources=`
   subset; confirm in 1.0) and ranked once, not recomputed after each removal
   (too costly at 2M nodes; this limitation is stated in the note).
3. Record the largest-component fraction S(*f*) and the size of the second-largest
   component. The peak of the second curve estimates the percolation threshold.
   Add one random edge-removal run for the bond-percolation threshold.
   Also record **global efficiency E(*f*)**, estimated from shortest paths out
   of a fixed random sample of source nodes (exact all-pairs is infeasible at
   2M nodes).
4. Output **Fig A1**: removal curves for the three orders, with S(*f*) and E(*f*)
   as two panels, plus an inset of the degree vs load (betweenness)
   distributions, as in CLM's Figs 3–4. Add a half-page note on what topology
   alone can and can't say.
5. (D3) Repeat 1–3 on DIMACS CAL, clipped to California, and export the
   top-betweenness edges with coordinates for Part B.

### Part B (Butte County first)
1. **Roads:** osmnx drive network for Butte County plus a buffer, so exits that
   leave the county are included. Merge each divided road's two one-way
   carriageways so it counts as one route (they are not independent exits).
   **Evacuation rule:** keep one-way roads as one-way. Contraflow was used on
   Skyway, but assuming it everywhere would overstate capacity. A contraflow
   sensitivity check is one line in `FINDINGS.md`, not a second analysis.
   Private roads and fire roads are left out of the headline (they are often
   gated or unpaved) and reported as a count.
   **Apply the three Overpass fixes from `rkk-gis/src/osmpull.py`:**
   project-specific Referer and User-Agent, a depth cap on osmnx's
   silent 429 retry, and the Overpass URL pinned to `gall.openstreetmap.de`.
2. **Communities:** 2020 TIGER places (incorporated towns and census-designated
   places) in the county. Population comes from 2020 blocks. Report the share of
   county population living outside any place. Settlements such as Concow that
   are not CDPs are a known gap, stated in the README.
3. **Targets ("the wider highway system"), D1.** This is the most consequential
   choice. A plain "reach any state highway" rule breaks down where a state
   route runs into town: Clark Road into Paradise is signed as SR 191 (to confirm
   in OSM), which would make Paradise's min cut trivial. **Proposed:**
   motorway and trunk nodes (OSM classes) lying **outside the fire hazard zones
   and ≥ 5 km outside the community boundary**, i.e. a safe place on the main
   network, not merely a highway sign. The 5 km figure gets one sensitivity line
   (3 / 10 km).
4. **Measures** as in §3, with the hazard threshold at **Very High** for the
   headline and **High+** as the sensitivity check.
5. **Removal:** remove Very High edges, then recompute capacity, travel time and
   efficiency. Report capacity lost and communities cut off.
5b. **(D7, in v1) CLM-style congestion run, Butte and LA.** Load = evacuation trips
   from each community's population to the safe destinations, sent along the
   most efficient path. Capacity = physical edge capacity. Apply the CLM update
   (efficiency of an overloaded edge × capacity/load) and iterate until it
   settles. Output, per community: the flow achieved vs the max-flow bound
   (the coordination gap), run with all exits open and again with Very High
   edges removed. One run per scenario, no sweep over α: α is replaced by
   real capacity. Iteration count, and whether it converges or oscillates,
   are reported. If it doesn't settle, that is a finding, not something to
   tune away.
6. **Sensitivity on the hazard layer (one line):** re-rank using observed
   fire history (edges inside any FRAP perimeter since 1950) instead of the
   modelled hazard zones. The hazard zones are a model and the perimeters are
   observations; if both give the same ranking, the result is stronger.

### 5a. Second study area: Los Angeles County foothills (D4)
- **Why:** two January 2025 fires in one urban county, with a different setting
  from Butte (urban, mostly local responsibility area, dense arterials).
  Pacific Palisades is the capacity case; Altadena (Eaton Fire) is its
  neighbour. Both perimeters are in the fire perimeter data (verified today:
  PALISADES 2025, 23,448.88 acres, unit LDF; EATON 2025, 14,056.26 acres,
  unit LAC).
- **Community unit: TIGER places don't work in LA.** Pacific Palisades is a
  neighbourhood of the City of Los Angeles, not a Census place, so the Butte
  approach would miss it. Use LA County's official **Countywide Statistical
  Areas** (374 polygons covering cities, unincorporated communities and City of
  LA neighbourhoods; verified to include "Los Angeles - Pacific Palisades",
  "Palisades Highlands" and "Unincorporated - Altadena"):
  `public.gis.lacounty.gov/public/rest/services/LACounty_Dynamic/Political_Boundaries/MapServer/23`.
  The engine takes any polygon layer as communities, so no change to
  `hazardnet/`.
- **Extent:** Countywide Statistical Areas that intersect Very High hazard
  zones in the Santa Monica Mountains and San Gabriel foothills, plus a
  road buffer. Not the whole county.
- **Historical hazard maps:** the LA County archive (2007 SRA / 2008 LRA),
  provenance still to be confirmed (§9 D5).
- Same measures, the same target-rule map check (D1) and the same CLM-style
  run as Butte.

### Scaling
Butte → LA foothills → review with you → statewide by county-wise osmnx pulls
(avoids the 1.33 GB file). Nothing statewide runs until both study areas have
been reviewed.

---

## 6. Validation

1. **Camp Fire retrospective:** what share of Paradise's (and Magalia's)
   min-cut exit capacity lay inside the final Camp Fire perimeter? Limitation:
   FRAP gives the *final* perimeter, not its progression, so this shows which
   exits were exposed, not when they closed.
2. **SB 99 comparison:** our list of single-exit and low-capacity communities
   for Butte vs the areas shown in General Plan 2040 Figures HS-15 and HS-16.
   Agreement supports the method; disagreement is a planning finding if it holds
   up under checking.
3. **Paradise sanity check:** the redundancy measure should show several
   routes; the capacity measure should rank Paradise near the top for
   people per unit capacity. If it doesn't, the capacity imputation is wrong,
   or the premise is, and either goes in `FINDINGS.md`.

---

## 7. Outputs

- `hazardnet/` with the five-function interface and tests on a toy graph where
  min cuts and max-flows are known by hand.
- **Fig A1**: fragmentation curves (Part A) + a short note.
- **Butte County map**: exit routes coloured by hazard, communities shaded by
  people per unit of exit capacity, Paradise labelled. Probable **hero figure**;
  decide after seeing it.
- **Ranked table**: community, population, `n_disjoint`, `capacity_vph`,
  `people_per_capacity`, `exposed_share`, capacity after removal, cut-off flag.
- Charts use `modular-viz-system`; each figure is labelled with its source, date
  and byline.
- Repo-level: README, MIT `LICENSE`, `DATA_LICENSES.md` (OSM ODbL; CAL FIRE
  CC-BY; Census public domain; SNAP/DIMACS no licence stated), `data/README.md`
  plus fetch scripts, and `docs/FINDINGS.md`.

### Proposed layout
```
ca-road-fragility/
  hazardnet/            # engine: roads.py hazard.py overlay.py access.py remove.py
  studies/california/   # config.yaml, run_part_a.py, run_part_b.py, figures.py
  data/                 # README.md only in git; raw/ and interim/ ignored
  scripts/fetch_*.py
  docs/DESIGN.md  docs/FINDINGS.md
  tests/
  environment.yml  Makefile  README.md  LICENSE  DATA_LICENSES.md
```
Use a conda `environment.yml` pinned to Python 3.12. System Python here is 3.14,
and not all of the geospatial stack publishes 3.14 wheels yet. Paths via
`pathlib`; nothing Windows-only.

---

## 8. Risks and limits

| Risk | Handling |
|---|---|
| Target definition drives the result (D1) | One stated rule, one sensitivity line, discussed in the README |
| Missing OSM `lanes` tags means capacity is imputed | Flag imputed edges; publish unit-capacity (redundancy) ranking alongside |
| Residents ≠ people present (Camp Fire began around 6:30 am on a weekday; visitors, workers) | Stated as a limit; night-time residential population is the only consistent basis |
| People per capacity isn't clearance time (needs vehicles per household → ACS → API key) | Report the ratio; clearance hours only if you approve a Census key |
| Local-area hazard maps are "recommended", not everywhere adopted | Caveat in README |
| DIMACS includes Nevada; TIGER-era vintage | Clip by coordinates; state vintage |
| Overpass throttling / silent retry | Fixes from `rkk-gis` (§5 B1) |
| Betweenness at 2M nodes | Sampled, ranked once; stated |

| CLM-style run uses static loads, not time-varying departures | Label it a bound on uncoordinated routing, not a simulation of the evacuation |

**Not in v1:** MTBS/dNBR, Google Earth Engine, Motter–Lai removal cascades (CLM
degradation is the better fit, §1), traffic microsimulation, the CLM-style run
statewide, anything statewide before Butte and LA have been reviewed.

---

## 9. Decisions (log)

| # | Decision | Status (25 Sep 2026) |
|---|---|---|
| D1 | Target rule | **R3 as it stands** (chosen from the Butte map, 25 Sep): motorway/trunk nodes outside High **and** Very High zones, ≥ 5 km from the community. R2 is kept as a one-line check. |
| D2 | Headline hazard threshold | **Yes:** Very High headline, High+ as the check. |
| D3 | DIMACS CAL as spatial Part A | **Yes.** |
| D4 | Second county | **Los Angeles, two fire clusters** (option 1, 25 Sep): the CSAs each 2025 perimeter touched. A whole-foothill-band rule was dropped: the 2025 LRA map puts large parts of urban LA in Very High (Silver Lake 81%, Hollywood 57%), so the band came to 70–110 CSAs / ~8,300 km². |
| D5 | Pre-2018 hazard maps | **Yes.** Where they can be found is below. |
| D6 | Census API key → clearance hours | **Yes.** You sign up; the key lives in `.env`, never in git. |
| D7 | CLM-style congestion run | **In v1**, Butte and LA. |

### D1 background: what "the highway system" means in California
Caltrans signs three kinds of route: **Interstates** (I-5, I-80), **US routes**
(US-101, US-50) and **State Routes** (SR 99, SR 70, SR 191, …). "State highway"
is a legal designation, not a size. Some state routes are six-lane freeways;
others are two-lane mountain roads. Clark Road into Paradise appears to be SR 191,
a two-lane road (to confirm in OSM). OSM classifies by function instead:
`motorway` (freeway), `trunk` (expressway or major arterial highway), `primary`
(most other state routes), `secondary`. The three candidate rules:

- **R1. Any state route:** too lenient; Paradise would count as already "out".
- **R2. Motorway + trunk only:** the high-capacity network. In Butte this is
  roughly SR 99 and parts of SR 70 (to confirm in the data).
- **R3. R2, but only points outside hazard zones and ≥ 5 km from the community**
  (default): the destination must be both high-capacity and safe.

On the map it will be obvious if R3 puts Paradise's destination somewhere
absurd; that is the check.

### D4 recommendation
**Los Angeles County, limited to the Santa Monica Mountains and San Gabriel
foothill communities.** Reasons: (a) the Palisades Fire (January 2025) is a
second, recent case where the failure was road capacity, not the number of
exits; (b) it is urban and mostly local responsibility area, which contrasts
with Butte, which is rural and mostly state responsibility area, and tests the
2025 local-area maps; (c) an archived copy of LA County's 2007 SRA / 2008 LRA
hazard maps is online (below), which covers D5 for that county. Alternatives:
Sonoma (Tubbs 2017) or Shasta (Carr 2018).

### D5: where the pre-2018 maps are
- **2007 SRA map (`fhszs06_3`, adopted 7 Nov 2007) plus the 2008–11 LRA Very
  High recommendations, statewide:** a copy is on
  [Data Basin](https://databasin.org/datasets/fbb8a20def844e168aeb7beb1a7e74bc/)
  (CC-BY 3.0). Download probably needs a free Data Basin account, which you
  would create. No official CAL FIRE download of the 2007 statewide layer
  turned up.
- **LA County only:** `services.arcgis.com/RmCCgQtiZLDCtblq/.../Archive_FHSZSRA`
  and `…/Archive_FHSZLRA` (2007 SRA / 2008 LRA). Hosted by the account
  `Fire_Dspace`; provenance is **not yet confirmed**.
- **Butte extract:** not found online. If Data Basin fails, ask CAL FIRE
  (FHSZinformation@fire.ca.gov); you would need to send that email.

### D6: what the key is for
Sign up at https://api.census.gov/data/key_signup.html (you do this; I can't
create accounts), then put `CENSUS_API_KEY=...` in `.env`, which is listed in
`.gitignore`. Use: ACS 5-year table **B25044** (tenure by vehicles available)
at block-group level → vehicles per household → turns people per unit capacity
into an estimate of clearance hours. Cars per household in the ACS ≠ cars taken
in an evacuation; stated as a limit.

## References (verified)
- Leskovec, J., Lang, K., Dasgupta, A., Mahoney, M. (2009). Community structure
  in large networks. *Internet Mathematics* 6(1), 29–123.
- Motter, A. E., Lai, Y.-C. (2002). Cascade-based attacks on complex networks.
  *Phys. Rev. E* 66, 065102. https://doi.org/10.1103/PhysRevE.66.065102
- Crucitti, P., Latora, V., Marchiori, M. (2004). Model for cascading failures
  in complex networks. *Phys. Rev. E* 69, 045104. arXiv:cond-mat/0309141
  (read in full for this design).
- Latora, V., Marchiori, M. (2001). Efficient behavior of small-world networks.
  *Phys. Rev. Lett.* 87, 198701. https://doi.org/10.1103/PhysRevLett.87.198701
- Crucitti, P., Latora, V., Porta, S. (2006). Centrality measures in spatial
  networks of urban streets. *Phys. Rev. E* 73, 036125. Background for
  centrality on geographic street graphs; not yet read in full.
- Albert, R., Jeong, H., Barabási, A.-L. (2000). Error and attack tolerance of
  complex networks. *Nature* 406, 378–382. https://doi.org/10.1038/35019019

---

## 10. Addendum (26 Sep 2026, approved): the policy layer

**Why.** The diagnosis alone ("14 Butte communities have no safe exit") gives a
reader no way to act. The results already show that the same label covers
different problems with very different price tags (FINDINGS: three fires,
three kinds of failure). This layer asks: **what does each level of safety
cost, and what is the cheapest way to reach it?** It does both of the things
you asked for (26 Sep): a tiered standard that is easier to meet than strict
R3, *and* the cheapest fixes to close the gap. Strict R3 stays visible, so the
report always says who is still at risk under the easier rungs.

### 10.1 The safety ladder (per community)

| Rung | Standard | Basis |
|---|---|---|
| L1 | ≥ 2 edge-disjoint routes to an R3 destination (any hazard) | SB 99 minimum, Gov. Code §65302(g)(5) |
| L2 | Managed clearance ≤ **2 h** | NIST TN 2135 (Maranghides et al. 2021): the Camp Fire's main front reached Pentz Rd ~2 h after ignition |
| L3 | Managed clearance ≤ **1 h** | same source: first spot fires in Paradise at 07:44–07:50, ~75–80 min after ignition |
| L4 | L3 using only exits that avoid Very High (High allowed) | this study |
| L5 | Strict R3: L3 avoiding High and Very High | D1 as chosen |

No state target exists to anchor L2/L3. AB 747 requires "capacity, safety, and
viability" but no number. The state Evacuation Planning Technical Advisory was
still a draft out for comment in April 2025, and its PDF could not be retrieved
(redirect loop), so this is stated as "none found", not "none exists". The NIST
times run from **ignition**; real warning time is shorter, so L2/L3 are
generous, not strict. The principle is Cova (2005, *Natural Hazards Review*
6(3)): evacuation time must fit within lead time.

### 10.2 Interventions, cheapest class first

| # | Intervention | How the engine tests it | Size reported |
|---|---|---|---|
| I1 | **Managed evacuation** (phased orders, traffic control) | already computed: managed vs self-routed (last car out) | none (operational) |
| I2 | **Contraflow** on the binding roads | double outbound capacity of the arcs in the binding cut; recompute managed clearance | km of road |
| I3 | **Targeted widening** | +1 lane per direction on one binding arc at a time, greedy, up to 5 steps or until the next rung is met | lane-km per hour saved |
| I4 | **Second access from existing fire roads** | re-read OSM *including* `highway=track` / gated service roads excluded by the drive filter; add them at 1 lane (950 veh/h); test whether L1 or L4 becomes reachable | km to upgrade |
| I5 | **Where nothing works** | no route can meet L4 even after I1–I4: flag for a new road or a temporary refuge area; not modelled | none (flag only) |

- Fuel treatment along exits is **reported, not modelled**: km of each binding
  road inside Very High, i.e. the corridor to treat. The engine has no
  fire-behaviour model, so it cannot say what treatment buys.
- **Dollars only from a cited source** (Caltrans unit costs, if a usable
  table is found and verified at build time); otherwise physical units only.
  No invented costs.

### 10.3 Outputs
- `outputs/tables/policy_<area>.csv`: community × highest rung met now ×
  cheapest intervention class that reaches the next rung × its size.
- One figure, **"What each fix buys"**, for the three fire groups (Camp,
  Palisades, Eaton) and Butte's cut-off communities: clearance under
  self-routed → managed → + contraflow → + widening → + second access, with
  the L2/L3 lines drawn.
- `docs/POLICY.md`: a one-page note in plain language (for your portfolio
  site; written in your prose style).

### 10.4 Scope and risks
- Butte and the two LA clusters only. No statewide runs, no traffic
  microsimulation.
- I3 inherits the lane-imputation problem (91% of Butte arcs untagged).
  Widening results are reported next to the unit-capacity ranking.
- I4 depends on how completely OSM maps fire roads, which is unknown in
  advance. A community with none mapped reads as "no candidate", not "none exist".
- Contraflow is not feasible on every road (turn lanes, intersections); I2
  says which roads it would need, not that it is ready to use.
- **Data:** I4 needs tracks, which the current graphs dropped. LA: re-read
  the SoCal extract we already have. Butte: Overpass has been unreliable, so the
  Geofabrik NorCal extract (652 MB, under the 1 GB line) instead.

### 10.5 Decisions (26 Sep)
- **P1.** L2 = 2 h, L3 = 1 h, accepted tentatively. Both are config values
  (`policy.rungs`), so the ladder can be rebuilt with other targets in one run.
- **P2.** I4 fire-road test: **yes**. Butte from the Geofabrik NorCal extract.
- **P3.** `docs/POLICY.md`: **yes**, in your prose style.
