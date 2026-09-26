# Findings log

Results as they come, including null and negative ones. Newest at the bottom
of each section. Dates are when the result was produced.

## Data checks

**2026-09-25. SNAP roadNet-CA matches its published counts.** 1,965,206 nodes,
2,766,607 undirected edges (from 5,533,214 directed lines), largest connected
piece 1,957,027 (99.6%), second 586. Degree range 1 to 12: 321,027 dead ends
(degree 1, 16%), 971,276 degree 3, 454,208 degree 4, and only 14,000 above 4.
This narrow spread is the premise of the Part A prediction.

**2026-09-25. DIMACS "CAL" is California + Nevada; clipped to California.**
Using the Census 1:500k state outline: kept 1,594,761 nodes / 1,958,387
undirected edges (from 4,657,742 arcs), dropped 296,054 nodes (Nevada, plus
any coastal nodes the outline misses). Largest piece 1,594,306. A first run
with the 1:20m outline kept 2,887 fewer nodes and was discarded. DIMACS arc
weights have no documented unit; Part A uses hops for both graphs.

**2026-09-25. Census API needs a key** (redirects to `missing_key.html`
without one). Key obtained and kept in `.env`.

**2026-09-25. Butte County inputs.**
- OSM drive network (county + 15 km): 19,504 nodes, 47,029 directed arcs.
  **90.9% of arcs have no `lanes` tag**, so capacity is mostly imputed by road
  class. The unit-capacity (disjoint paths) ranking is therefore the one to
  trust first. The osmnx `drive` filter excludes `access=private`, `track` and
  `service` roads.
- Population: 2020 block `POP20` sums to 211,632 for Butte, matching the
  official 2020 count. Statewide it sums to 39,538,223, also matching. The
  TIGER block file carries population itself, so the PL 94-171 download is
  redundant. 23,875 residents (11.3%) live outside any 2024 place polygon.
- Hazard: 13,243 of 47,029 arcs (28%) touch Very High, 5,443 High, 2,031
  Moderate. The LRA map codes non-wildland land as `FHSZ = -3`
  ("NonWildland"); it is excluded, not treated as a level.

## Part A: topology baseline

**2026-09-25. The prediction held on SNAP, with a limit.** Largest connected
piece S1 and efficiency E (relative to intact) after removing a share of
junctions (random = mean of 10 seeds; E from 32 sampled sources):

| removed | busiest first (betweenness) | most-connected first (degree) | random |
|---|---|---|---|
| 1% | S1 0.11, E 0.09 | S1 0.98, E 0.85 | S1 0.98, E 0.95 |
| 10% | S1 0.003 | S1 0.80, E 0.35 | S1 0.85, E 0.53 |
| 20% | ~0 | S1 0.003 | S1 0.61, E 0.19 |

- Removing the busiest 1% of junctions (by sampled betweenness) cuts 89% of
  the network off from the main piece; a random 1% cuts off 2%. The ranking
  is computed once on the intact network. Re-ranking after each removal is
  typically more damaging (Holme, Kim, Yoon & Han 2002, *Phys. Rev. E* 65,
  056109), so this figure is conservative.
- Degree-targeted removal tracks random removal up to ~10%, then collapses by
  20%. That is roughly the share of 4-way junctions (23%), so the prediction
  ("degree ≈ random") holds only for small removals.
- Load is concentrated where degree is not: the top 1% of junctions carry 83%
  of sampled shortest-path load (top 0.1%: 49%). Degree runs 1–12.
- Efficiency falls much faster than connectivity: at 10% random removal, 85%
  of junctions are still connected but efficiency is down to 53%. Road networks
  force detours before they split apart, which the connectivity measure misses.
- Random-removal threshold (peak of the second-largest piece): ~25% of
  junctions; ~28% of road segments (bond).

**2026-09-25/26. SNAP and DIMACS disagree under random loss; the gap is
part artifact, part real (checked by contraction, at a reviewer's prompt).**
DIMACS has far more degree-2 nodes (26% vs 10%), many of them shape points
tracing a road's curve; removing one cuts a road that has no junction there.
Both graphs were rerun with every degree-2 chain contracted to a single edge
(`hazardnet.contract_degree2`):

| graph | random 10%: largest piece | junction threshold | segment threshold | busiest 1% |
|---|---|---|---|---|
| SNAP | 0.85 | 25% | 28% | 0.11 |
| SNAP contracted | 0.86 | 28% | 35% | 0.09 |
| DIMACS | 0.20 | 10% | 10% | 0.17 |
| DIMACS contracted | 0.62 | 14% | 22% | 0.09 |

(threshold = peak of the second-largest piece; random = mean of 10 seeds)
- **Part artifact.** Contraction more than doubles DIMACS's segment threshold
  (10% → 22%) and triples what survives 10% random loss.
- **Part real.** Contracted against contracted, DIMACS still falls apart at
  about half SNAP's damage (14% vs 28% of junctions). The remainder reflects
  how the two graphs were built. SNAP states no source or vintage, so it
  cannot be attributed further.
- **Robust.** Busiest-first removal is devastating on all four graphs:
  removing the top 1% leaves at most 17% of the network connected. This is
  the Part A result that survives every change of representation.

## Part B: Butte County (destination rule R3, D1)

**2026-09-25. 14 of 30 communities, 18,293 residents (2020), have no way out
that avoids Very High hazard.** With every Very High road outside the
community closed, they cannot reach a safe destination. At High+ it is 18
communities and 23,719 people. Berry Creek and Cohasset have a single route
out. Of the 14, 9 have been touched by a fire perimeter since 2008 (CAMP 2018,
NORTH COMPLEX 2020, DIXIE 2021, PARK 2024 among them).

**2026-09-25. Ordering by people per unit of capacity puts Chico first**
(103,910 people, 18,150 veh/h, 4.3 h to clear if perfectly managed). That's
real, but Chico is mostly on the valley floor. The headline ordering is
therefore by hazard (no safe route first), with people per capacity second.

**2026-09-25. Camp Fire check: the model finds the real exits.** The ridge
(Paradise + Magalia + Concow) was run as ONE evacuation, since separate runs
double-count shared exits. Its minimum cut, found with no hand-picking, is
Skyway, Clark Road (CA 191), Pentz, Neal, Honey Run, CA 70 and CA 32 (Deer
Creek Hwy), the roads named in accounts of the evacuation. Six independent
routes, 9,650 veh/h. 47% of that capacity lies inside the final perimeter.
- Pre-fire (ACS 2014–18): 40,143 people, 32,198 vehicles. Paradise alone
  fell from 26,218 (2010 census) to 4,764 (2020 census) because of the fire,
  so the 2020-based ranking understates the ridge as it was in 2018.
- Clearance if every vehicle leaves: **2.5–3.5 h perfectly managed**. The
  range is lane-count uncertainty: 3.5 h with HCM defaults on untagged roads,
  2.5 h if every untagged arterial is really 2 lanes each way (both on the
  managed bound). And
  **9.3 h if every driver takes their own best route** (CLM-style run;
  self-routed throughput 3,477 veh/h, a 62.5% coordination loss).
- Limits: final perimeter, not progression; demand spread evenly over ridge
  nodes, because 2020 housing is post-fire; ACS "5+ vehicles" counted as 5.

**2026-09-25. Coordination gap: revised twice; report it as a range.**
1. The first version compared self-routed throughput against plain community
   max-flow, which lets demand start anywhere (Durham showed 95%). Replaced by
   a like-for-like managed bound: same origins, same split.
2. The LA Eaton run then gave a 94% loss in a street grid with 34 routes out.
   Diagnosis: with I-210 excluded by R3, free-flow routing sends 79% of the
   group to the I-710 terminus and 29% down one local street (W Howard St,
   950 veh/h). CLM's rule only slows an overloaded arc by L/C (+22%), too
   little to divert anyone, and a "no arc overloaded" test lets that single
   street cap the whole group. That strict number is really the time until
   the LAST car is out on fixed routes. So self-routed clearance is now
   reported as a range: bulk (each overloaded arc serves its capacity pro
   rata) to last car out (strict).
3. Re-routing can oscillate. Stopping at iteration 60 made the bulk figure
   depend on where in the cycle the run stopped (Camp: 9.3 h vs 7.0 h). Now,
   when the path set repeats, the result is taken over the whole cycle (mean
   delivered, max overload), and repeated runs give identical output. A
   "converged" flag that always reported True was also fixed.
Managed clearance (an exact max-flow bound) is the robust number; the
self-routed range is indicative.

**2026-09-25. SB 99 comparison (Butte GP 2040 Fig. HS-16): qualitative
agreement, different unit.** HS-16 marks residential *parcels* in hazard zones
with limited evacuation access. Its red clusters sit in the same foothill belt
as our 14 communities (SR 32 corridor, Magalia ridge, Concow/Yankee Hill,
Berry Creek/Forbestown). The county flags pockets inside Kelly Ridge, Palermo
and Oroville East that our community-level measure rates as having hazard-free
routes: a real masking effect of working at community scale. HS-16 covers only
unincorporated land, so the Town of Paradise is blank there. The county
figure's method is not described beyond "PlaceWorks, 2021".

**2026-09-25. Vehicles: ACS B25046 (aggregate vehicles) is suppressed for 47
of Butte's 200 block groups**; switched to B25044 (households by vehicles),
which has none missing. Chico has 1,429 vehicles on OSM fragments with no
route to any destination ("stranded"), reported rather than routed.

## Part B: Los Angeles

**2026-09-25. The 2025 LRA hazard map covers much of urban LA.** Share of CSA
land in Very High: Silver Lake 81%, Echo Park 73%, Hollywood 57%; Altadena only
31% (most of it on its northern edge). Any "touches Very High" extent rule
therefore selects 70–110 CSAs. Scope was cut to the two 2025 fire clusters
(D4 option 1).

**2026-09-25. LA roads come from a local OSM extract, not Overpass.** Three
Overpass attempts failed: osmnx's default ~2,500 km² sub-queries 504'd over
dense LA; with 100 km² pieces, 17 downloaded before lambert began returning
504 within ~9 s on every query; gall stopped answering; `overpass-api.de`
resolved to lambert again. The capped retry made each failure loud instead of
a silent hang. LA now uses the Geofabrik SoCal extract (671 MB, dated
25 Sep 2026) read with pyosmium, applying the exact `drive` filter osmnx sent
to Overpass for Butte and the same build → truncate → simplify order. Butte
(Overpass) and LA (extract) therefore select roads the same way, from OSM
snapshots a few hours apart.

**2026-09-25. LA ranking (R3, 14 CSAs; Angeles National Forest excluded as
near-unpopulated).** All five Palisades-cluster CSAs, 56,841 people (2020),
have no way out that avoids Very High hazard: Pacific Palisades, Palisades
Highlands, Mandeville Canyon, Malibu, Santa Monica Mountains. Every Eaton-cluster
CSA keeps some Very-High-free exit capacity (Altadena 36,950 of 47,250 veh/h).
LA's OSM data is better tagged than Butte's: 70% of arcs have no lanes tag,
against 91%.

**2026-09-25. Three fires, three kinds of failure.** Each group evacuated as
one, pre-fire vehicles, R3 destinations; "binding" = the roads in the min cut
of the like-for-like managed problem, i.e. what actually limits it:

| fire | vehicles | managed clearance | self-routed, last car out | binding roads |
|---|---|---|---|---|
| Eaton 2025 (Altadena, Sierra Madre, Kinneloa Mesa) | 39,597 | 0.85 h | 13.6 h | Eaton Canyon Dr (950 veh/h) |
| Palisades 2025 (Pac. Palisades, Highlands, Mandeville, Malibu, SMM) | 42,798 | 3.0 h | 13.7 h | Palisades Dr (950 veh/h), inside perimeter |
| Camp 2018 (Paradise, Magalia, Concow) | 32,198 | 2.5–3.5 h | 9.3 h | Skyway, Clark, Pentz, Neal, Honey Run, Jordan Hill, CA 32 (8,900 veh/h; 43% inside perimeter) |

- **Eaton: an operations problem.** The capacity exists (under an hour if
  managed); self-routed traffic funnels onto a few local streets.
- **Palisades: a structural problem.** Under a proportional evacuation, the
  Highlands' one practical road (Palisades Dr) sets the whole group's
  clearance; the rest could leave in under an hour. Plain min cut (50,700
  veh/h, far from the fire) hides this, which is why the binding cut of the
  demand-weighted problem is now reported.
- **Camp: both.** Too little capacity, and a large coordination loss.
- Self-routed takes a median of 3.0x the managed clearance time across Butte
  communities and 5.2x across LA (max 10.7x and 18.3x).
- These are static bounds (every vehicle leaves; fixed demand shares; final
  perimeter). They say which kind of fix each place needs, not how the
  evacuation unfolded hour by hour.

## Policy layer (DESIGN §10)

**2026-09-26. The safety ladder.** Residents (2020) by highest rung met
(rungs build on each other; managed clearance):
- Butte: rung 0 (fails SB 99) Berry Creek, Cohasset (1%); rung 1 Chico alone
  (55%: 4.3 h managed); rung 2 Magalia (4%); rung 3, within 1 h but only
  through Very High, 14 communities (11%); rungs 4–5, 12 communities (29%).
- LA fire clusters: rung 1 Palisades Highlands (1%); rung 2, 5 CSAs (29%);
  rung 3, 5 CSAs (47%); rung 5 Arcadia, Monrovia, Sierra Madre (23%).
- **Fewer than three in ten residents can get out within an hour without
  crossing Very High hazard** (Butte 29%, LA 23%).
- The 1 h / 2 h rungs are anchored on the Camp Fire (NIST TN 2135: first spot
  fires in Paradise 07:44, main front at Pentz Rd ~08:30, ignition ~06:30).
  No state target was found; the state's evacuation guidance was still a
  draft in 2025 and its PDF could not be retrieved.

**2026-09-26. What each fix buys (fire groups).**

| group | self-routed | managed | + contraflow | + widening |
|---|---|---|---|---|
| Camp ridge | 9.3 h | 3.5 h (2.5 h lane sensitivity) | 2.9 h | 2.3 h after 174 lane-km (Neal x3; Pentz; Clark) |
| Palisades | 13.7 h | 3.0 h | 3.0 h (Palisades Dr is divided: not reachable) | 1.6 h after 157 lane-km (Palisades Dr; PCH; Cornell Rd x2; Las Virgenes Rd) |
| Eaton | 13.6 h | 0.85 h | no gain | not needed |

- Coordination saved 6–13 h; 157–174 lane-km of widening saved ~1.2–1.4 h. (The Palisades widening first read 203 lane-km; ties are now broken toward the cheaper road, which found the same 1.64 h for 157.)
- **Camp ridge cannot reach the 2 h rung by roads alone** at its 2018
  population, even after 174 lane-km. That points to measures outside the
  network model: earlier (forecast-based) triggers, refuge areas, and Cova's
  (2005) maximum occupancy.
- Widening first worked arc by arc and showed zero gain for Camp, because
  several sections of a road bind equally. Replaced by widening whole named
  roads (the policy unit), with lane-km reported.
- Contraflow first made Kinneloa Mesa slightly worse (reversing a two-way road
  removes capacity other outbound traffic used). It is now applied only where
  it helps. It cannot reach divided roads (no same-node reverse arc), a stated
  limit.

**2026-09-26. Fire roads (I4, Butte): SB 99 yes, hazard-free no.** Counting
tracks and gated service roads at one lane, Berry Creek and Cohasset each go
from 1 route to 3 (enough for SB 99); Concow 2→4, Clipper Mills 2→5, Camp
ridge 6→9. But **none of the 14 cut-off communities gains an exit that avoids
Very High hazard**: the fire roads run through the same forest. The first I4
version snapped demand to any node of the extended graph, often a service-road
node, so removing extra roads stranded origins and every "without" case read
as infinite. Demand is now placed only on drive-network nodes.

**2026-09-26. Fire roads (I4, LA): same answer.** Tracks and service roads add
routes everywhere (Santa Monica Mountains 12→18, Malibu 6→9, Palisades group
19→25), but no CSA that lacks a Very-High-free exit gains one. Known
inconsistency: I4 runs on a separately extracted graph (drive + extra roads),
whose "without extra roads" route counts do not exactly match the main graph
(Palisades Highlands 5 vs 2; Pasadena 58 vs 56), because the two builds split
ways at different nodes. The with/without comparison inside I4 is consistent;
its baseline is not identical to the main analysis.

**2026-09-26. The LA policy run stalled for an hour; the cause was
`rule_targets`**, which rebuilt the union of all hazard polygons and tested
every node on every call (py-spy). It now tests only destination-class nodes,
by spatial join, cached per graph: identical targets in both areas, LA call
53 s → 1.7 s cached, and the full LA policy run took ~6 min instead of stalling.

## Method changes from DESIGN.md

**2026-09-25. Divided highways need no merging.** DESIGN §5 B1 planned to
merge a divided road's two carriageways so they would not count as two exits.
The engine does flow on a directed graph instead: only the outbound
carriageway can carry outbound flow, so the double count cannot happen.

**2026-09-25. Engine checked against hand-solved graphs** (`tests/`, 9 tests, incl. two for the CLM module):
max-flow 110 veh/h and 2 disjoint paths on a 6-node toy, capacity falls to 30
when the hazard arc is removed, a cut-off community has efficiency 0, path-graph
efficiency 5/6. The first run caught a real bug: the reverse Dijkstra's
super-sink arcs pointed the wrong way and every travel time came back infinite.

**2026-09-25. Three pipeline traps, fixed.** (1) CAL FIRE's ArcGIS service
404s on a GET with 1,000 object ids; the fetch uses POST. (2) An OGR `where=`
filter on the zipped TIGER block shapefile silently returns 0 rows for any
county; blocks are read by bounding box and filtered in pandas. (3) The hazard
overlay stalled on polygons of up to 178,844 vertices; tiling them to 2 km
(6,687 tiles, total area unchanged) cut it to under a minute.

**2026-09-26. Runtime and determinism.** The policy stage now runs units in
parallel worker processes (`policy.workers`, default 4; about 1 GB of RAM per
LA worker). Butte went from ~30 min to ~10. Making it parallel exposed two real
problems, both fixed: (1) widening picked among tied roads in the iteration
order of a Python set of names, which depends on per-process string hashing,
so runs could disagree at exact ties (Chico, step 2). Candidates are now sorted
and ties go to the cheaper road; two processes with different hash seeds now
give byte-identical rows. (2) A "stop contraflow at the first round that does
not help" rule threw away the Camp ridge's gain (round 1 alone gains nothing,
rounds 1–3 give 2.9 h). The best state over all rounds is now kept. A
determinism check that first reported "identical" was comparing two empty
files from crashed runs (NaN road names broke the sort); caught and fixed.

## Open items
- HCM per-lane capacities in `config.yaml` are standard figures not yet
  checked against the manual page by page.
- Windows default encoding (cp1252) broke a UTF-8 read; all file IO in the
  pipeline is now explicit UTF-8 so behaviour is the same on the Mac.
