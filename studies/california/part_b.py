"""Part B: communities, hazard and exits, per study area.

    python -m studies.california.part_b butte prepare      # OSM + hazard overlay + communities
    python -m studies.california.part_b butte targets      # D1 map: three destination rules

Later stages (accessibility, removal, the CLM-style run) are added after the
destination rule has been chosen from the map. Nothing is ranked before then.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml

from hazardnet import load_hazard, overlay

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM = ROOT / "data" / "raw", ROOT / "data" / "interim"
FIGS, TABLES, LOGS = ROOT / "outputs" / "figures", ROOT / "outputs" / "tables", ROOT / "logs"
CFG = yaml.safe_load((Path(__file__).with_name("config.yaml")).read_text(encoding="utf-8"))
MCRS = CFG["crs"]["metric"]


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "part_b.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- inputs ---
def county(fips: str) -> gpd.GeoDataFrame:
    c = gpd.read_file(f"zip://{RAW / 'tiger' / 'cb_2024_us_county_500k.zip'}")
    return c.loc[c.GEOID == fips].to_crs(MCRS)


def fire_perimeter(ref: dict, bbox=None) -> gpd.GeoDataFrame:
    per = gpd.read_file(RAW / "calfire" / "fire_perimeters_firep25_1.geojson", bbox=bbox)
    return per[(per.FIRE_NAME == ref["name"]) & (per.YEAR_ == ref["year"]) &
               (per.UNIT_ID == ref["unit"])].to_crs(MCRS)


def cluster_csas(name: str) -> gpd.GeoDataFrame:
    """LA: CSAs each reference fire touched, dissolved by label, with the
    cluster (fire) name and the share of the CSA's land inside the perimeter."""
    csa = gpd.read_file(RAW / "la" / "csa_communities.geojson").to_crs(MCRS)
    csa = csa.dissolve(by="LABEL", aggfunc="first").reset_index()
    parts = []
    for ref in CFG["areas"][name]["reference_fires"]:
        fire = fire_perimeter(ref, bbox=tuple(csa.to_crs(4326).total_bounds)).union_all()
        hit = csa[csa.intersects(fire)].copy()
        hit["cluster"] = ref["name"]
        hit["burn_share"] = hit.geometry.intersection(fire).area / hit.area
        parts.append(hit)
    return pd.concat(parts, ignore_index=True)


def study_area(name: str):
    a = CFG["areas"][name]
    cty = county(a["county_fips"])
    if a.get("clusters_from_fires"):
        core = cluster_csas(name)
        # not clipped to the county: Malibu's exits run west into Ventura County
        area = core.buffer(a["road_buffer_km"] * 1000).union_all()
        return cty, area
    area = cty.buffer(a["road_buffer_km"] * 1000).union_all()
    return cty, area


def fhsz(area_m) -> gpd.GeoDataFrame:
    """SRA 2024 + LRA 2025 hazard zones intersecting the area, one layer."""
    bbox = tuple(gpd.GeoSeries([area_m], crs=MCRS).to_crs(4326).total_bounds)
    parts = []
    for f in ("fhsz_sra_2024.geojson", "fhsz_lra_2025.geojson"):
        g = gpd.read_file(RAW / "calfire" / f, bbox=bbox)
        g["source_map"] = f.split(".")[0]
        parts.append(g)
    z = pd.concat(parts, ignore_index=True).to_crs(MCRS)
    z["geometry"] = z.geometry.make_valid()
    # LRA map codes non-wildland land as FHSZ = -3 ("NonWildland"): not a hazard level
    z = z[(z.FHSZ >= 1) & z.intersects(area_m)]
    return z[["FHSZ", "FHSZ_Description", "SRA", "source_map", "geometry"]]


def communities(name: str, cty: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Community polygons with 2020 population (block POP20, joined by block
    centroid, so the 2024 place outlines and 2020 blocks need not match)."""
    kind = CFG["areas"][name]["communities"]
    if kind == "tiger_places":
        p = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2024_06_place.zip'}").to_crs(MCRS)
        p = p[p.intersects(cty.geometry.iloc[0])]
        p = p.rename(columns={"NAME": "name", "NAMELSAD": "label", "GEOID": "cid"})
        p["kind"] = np.where(p.CLASSFP.str.startswith("C"), "incorporated", "CDP")
        p = p[["cid", "name", "label", "kind", "geometry"]]
    elif kind == "la_csa":
        p = cluster_csas(name)
        p = p.rename(columns={"LABEL": "label", "CSA_ID": "cid", "CITY_TYPE": "kind"})
        p["name"] = p["label"].str.replace(r"^(Los Angeles|Unincorporated|City of) -? ?", "",
                                           regex=True)
        p = p[["cid", "name", "label", "kind", "cluster", "burn_share", "geometry"]]
    else:
        raise ValueError(kind)
    fips = CFG["areas"][name]["county_fips"][2:]
    # An OGR `where=` filter on this zipped shapefile silently returns 0 rows
    # (any county), so read by the county's bounding box and filter here.
    bbox = tuple(cty.to_crs(4269).total_bounds)
    blocks = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2020_06_tabblock20.zip'}", bbox=bbox,
                           columns=["COUNTYFP20", "GEOID20", "POP20", "HOUSING20"])
    blocks = blocks[blocks.COUNTYFP20 == fips].to_crs(MCRS)
    cent = blocks.set_geometry(blocks.representative_point())
    j = gpd.sjoin(cent, p[["cid", "geometry"]], predicate="within", how="left")
    pop = j.groupby("cid")[["POP20", "HOUSING20"]].sum()
    p = p.merge(pop, left_on="cid", right_index=True, how="left").fillna(
        {"POP20": 0, "HOUSING20": 0})
    outside = int(j.loc[j.cid.isna(), "POP20"].sum())
    log(f"{name}: {len(p)} communities; county pop {int(blocks.POP20.sum()):,}, "
        f"{outside:,} ({outside / blocks.POP20.sum():.1%}) live outside any community polygon")
    return p


# ---------------------------------------------------------------- prepare ---
def roads(name: str):
    """OSM pull, cached as data/interim/<area>/roads_osm.pkl (no hazard yet)."""
    from hazardnet.osm import configure, load_osm
    out = INTERIM / name
    out.mkdir(parents=True, exist_ok=True)
    path = out / "roads_osm.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    _, area = study_area(name)
    area_ll = gpd.GeoSeries([area], crs=MCRS).to_crs(4326).iloc[0]
    configure(RAW / "osmnx_cache", LOGS / "osmnx")
    t = time.time()
    pbf = CFG["areas"][name].get("osm_pbf")
    rg = load_osm(area_ll, capacity_table=CFG["capacity_table"],
                  max_query_km2=CFG["areas"][name].get("overpass_max_query_km2"),
                  pbf=RAW / pbf if pbf else None, work_dir=INTERIM / name)
    log(f"{name}: OSM {rg.meta} in {time.time() - t:.0f}s")
    path.write_bytes(pickle.dumps(rg))
    return rg


def prepare(name: str) -> None:
    out = INTERIM / name
    cty, area = study_area(name)
    rg = roads(name)
    rg_path = out / "roads.pkl"

    z = fhsz(area)
    z.to_file(out / "fhsz.gpkg")
    hz = load_hazard(z, kind="polygon", field="FHSZ", levels=CFG["hazard"]["levels"])
    t = time.time()
    overlay(rg, hz, metric_crs=MCRS)
    hm = np.asarray(rg.g.es["hazard_max"])
    log(f"{name}: overlay {time.time() - t:.0f}s; arcs by hazard_max "
        f"{dict(zip(*np.unique(hm, return_counts=True)))}")
    rg_path.write_bytes(pickle.dumps(rg))
    rg.edges.to_file(out / "edges.gpkg")

    com = communities(name, cty)
    com.to_file(out / "communities.gpkg")
    cty.to_file(out / "county.gpkg")


# ---------------------------------------------------------------- targets ---
def node_table(rg) -> gpd.GeoDataFrame:
    g = rg.g
    nodes = gpd.GeoDataFrame({"vid": np.arange(g.vcount())},
                             geometry=gpd.points_from_xy(g.vs["x"], g.vs["y"]),
                             crs=4326).to_crs(MCRS)
    cls = np.asarray(g.es["road_class"], dtype=object)
    ends = np.asarray(g.get_edgelist())
    for c in ("motorway", "trunk", "primary"):
        on = np.zeros(g.vcount(), bool)
        e = ends[cls == c]
        on[e.ravel()] = True
        nodes[f"on_{c}"] = on
    return nodes


_HAZ_CACHE: dict = {}


def _candidates_in_hazard(nodes, hazard_zones, classes: tuple, level: int) -> np.ndarray:
    """Which destination-class nodes lie in hazard >= level. Cached per graph:
    the answer is the same for every community. The first version rebuilt the
    union of all hazard polygons and tested every node, on every call; with
    LA's intricate polygons and 262k extended-graph nodes that took minutes per
    call and stalled the LA policy run (py-spy, 2026-09-26). Only nodes on the
    destination classes are tested, by spatial join: same answer as testing
    against the union, since a point meets the union iff it meets a polygon."""
    key = (id(nodes), len(nodes), id(hazard_zones), classes, level)
    if key not in _HAZ_CACHE:
        cand = np.zeros(len(nodes), bool)
        for c in classes:
            cand |= nodes[f"on_{c}"].values
        pos = np.flatnonzero(cand)
        polys = hazard_zones.loc[hazard_zones.FHSZ >= level, ["geometry"]]
        pts = gpd.GeoDataFrame({"pos": pos}, geometry=nodes.geometry.values[pos], crs=nodes.crs)
        hit = gpd.sjoin(pts, polys, predicate="intersects", how="inner")["pos"].unique()
        bad = np.zeros(len(nodes), bool)
        bad[hit] = True
        _HAZ_CACHE[key] = bad
    return _HAZ_CACHE[key]


def rule_targets(rule: dict, nodes, hazard_zones, community_geom=None) -> np.ndarray:
    ok = np.zeros(len(nodes), bool)
    for c in rule["classes"]:
        ok |= nodes[f"on_{c}"].values
    if "outside_hazard_level" in rule:
        ok &= ~_candidates_in_hazard(nodes, hazard_zones, tuple(rule["classes"]),
                                     rule["outside_hazard_level"])
    if "min_distance_km" in rule and community_geom is not None:
        ok &= nodes.geometry.distance(community_geom).values >= rule["min_distance_km"] * 1000
    return np.flatnonzero(ok)


def targets_map(name: str, focus: str) -> None:
    """D1 check: where each candidate rule puts 'out'. R3 depends on the
    community, so its panel shows the targets for `focus` (e.g. Paradise)."""
    sys.path.insert(0, str(ROOT))
    import matplotlib.pyplot as plt
    from viz.viz_theme import (BG, FONT_BOLD, FONT_SEMIBOLD, GRID, MUTED, TEXT,
                               footer_config, setup_style, title_block,
                               viridis_continuous)
    out = INTERIM / name
    rg = pickle.loads((out / "roads.pkl").read_bytes())
    edges = gpd.read_file(out / "edges.gpkg").to_crs(MCRS)
    com = gpd.read_file(out / "communities.gpkg")
    cty = gpd.read_file(out / "county.gpkg")
    z = gpd.read_file(out / "fhsz.gpkg")
    nodes = node_table(rg)
    fgeom = com.loc[com.name == focus].geometry.iloc[0]

    rules = CFG["targets"]
    tg = {r: rule_targets(rules[r], nodes, z, fgeom) for r in ("R1", "R2", "R3")}
    summary = {r: len(v) for r, v in tg.items()}
    log(f"{name}: targets per rule (R3 for {focus}) {summary}")

    import matplotlib.patheffects as pe
    setup_style()
    major = edges.road_class.isin(["motorway", "trunk", "primary", "secondary"])
    # Frame: the focus community's own cluster when the study has clusters
    # (LA), the county otherwise. The figure is sized to the frame's aspect, so
    # a wide frame no longer leaves an empty band above short panels.
    if "cluster" in com.columns and com["cluster"].notna().any():
        cl = com.loc[com.name == focus, "cluster"].iloc[0]
        frame = com[com.cluster == cl]
        where = f"{CFG['areas'][name].get('label_short', 'Los Angeles')}, {cl.title()} fire cluster"
    else:
        cl, frame = None, cty
        where = CFG["areas"][name].get("label", name.replace("_", " ").title() + " County")
    pad = 6000
    xmin, ymin, xmax, ymax = frame.total_bounds
    xmin, ymin, xmax, ymax = xmin - pad, ymin - pad, xmax + pad, ymax + pad
    panel_w = 5.6                                          # inches
    panel_h = panel_w * (ymax - ymin) / (xmax - xmin)
    head, foot, gap = 1.75, 0.55, 0.25                     # inches
    fig_w, fig_h = 3 * panel_w + 2 * gap + 0.6, panel_h + head + foot
    fig = plt.figure(figsize=(fig_w, fig_h))
    axes = [fig.add_axes([(0.3 + i * (panel_w + gap)) / fig_w, foot / fig_h,
                          panel_w / fig_w, panel_h / fig_h]) for i in range(3)]
    unit = "community" if cl else "town"
    titles = {
        "R1": ("R1 · any state route", "motorway + trunk + primary"),
        "R2": ("R2 · high-capacity roads", "motorway + trunk only"),
        "R3": (f"R3 · high-capacity, safe, away from {focus}",
               f"R2, outside High/Very High, ≥ 5 km from the {unit}"),
    }
    halo = [pe.withStroke(linewidth=3.5, foreground="white")]
    for ax, r in zip(axes, ("R1", "R2", "R3")):
        z[z.FHSZ == 2].plot(ax=ax, color=viridis_continuous(0.72), alpha=0.28, lw=0)
        z[z.FHSZ == 3].plot(ax=ax, color=viridis_continuous(0.96), alpha=0.45, lw=0)
        edges[~major].plot(ax=ax, color=GRID, lw=0.25)
        edges[major].plot(ax=ax, color=MUTED, lw=0.7)
        cty.boundary.plot(ax=ax, color=TEXT, lw=0.8, linestyle="--")
        com.boundary.plot(ax=ax, color=TEXT, lw=0.4)
        gpd.GeoSeries([fgeom], crs=MCRS).boundary.plot(ax=ax, color=TEXT, lw=1.8, zorder=6)
        pts = nodes.iloc[tg[r]]
        pts.plot(ax=ax, color=viridis_continuous(0.05), markersize=6, zorder=5)
        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal"); ax.set_axis_off(); ax.set_facecolor(BG)
        # titles in points above the axes: fixed spacing whatever the panel height
        ax.annotate(titles[r][0], (0, 1), xycoords="axes fraction", xytext=(0, 26),
                    textcoords="offset points", fontsize=13, fontfamily=FONT_BOLD, color=TEXT)
        ax.annotate(f"{titles[r][1]}  ·  {len(pts):,} destination nodes", (0, 1),
                    xycoords="axes fraction", xytext=(0, 9), textcoords="offset points",
                    fontsize=10, fontfamily=FONT_SEMIBOLD, color=MUTED)
        c = fgeom.representative_point()
        right = c.x > (xmin + xmax) / 2                   # keep the label inside the panel
        ax.annotate(focus, (c.x, c.y), xytext=(-18 if right else 18, 26),
                    textcoords="offset points", ha="right" if right else "left",
                    fontsize=11, fontfamily=FONT_BOLD, color=TEXT, zorder=8, path_effects=halo,
                    arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.9))

    title_block(fig, "Where does “out” begin? Three candidate destination rules",
                f"{where}. Dark dots are the road nodes each rule treats as reaching the wider "
                f"highway system. Shading: CAL FIRE High (green) and Very High (yellow) hazard.",
                x=0.3 / fig_w, y_title=1 - 0.45 / fig_h, y_sub=1 - 0.8 / fig_h, subtitle_size=11.5)
    footer_config(fig, "Sources: © OpenStreetMap contributors (ODbL), pulled Sep 2026 · CAL FIRE Fire "
                  "Hazard Severity Zones, SRA 2024 + LRA 2025 (recommended) · US Census TIGER/Line 2024 "
                  "places; LA County CSAs.   Chart: Sahasrik Ragani", x=0.3 / fig_w, y=0.15 / fig_h)
    FIGS.mkdir(parents=True, exist_ok=True)
    tag = name if cl is None else f"{name}_{cl.lower()}"
    fig.savefig(FIGS / f"d1_target_rules_{tag}.png", dpi=150)
    plt.close(fig)
    log(f"wrote {FIGS / f'd1_target_rules_{tag}.png'}")


# ---------------------------------------------------------------- vehicles ---
def vehicles_by_block(name: str, blocks: gpd.GeoDataFrame) -> pd.Series:
    """ACS 2020-24 5-yr vehicles per block group from B25044 (households by
    vehicles available: sum of k x households, "5 or more" counted as 5, so a
    slight undercount), split to blocks by 2020 housing units. B25046
    (aggregate vehicles) was the first choice but is suppressed for 47 of
    Butte's 200 block groups; B25044 has none missing. Needs CENSUS_API_KEY."""
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    fips = CFG["areas"][name]["county_fips"]
    cache = INTERIM / name / "acs_b25044.csv"
    if cache.exists():
        acs = pd.read_csv(cache, dtype=str)
    else:
        r = requests.get("https://api.census.gov/data/2024/acs/acs5", timeout=120, params={
            "get": ",".join(f"B25044_{i:03d}E" for i in range(1, 16)), "for": "block group:*",
            "in": f"state:{fips[:2]} county:{fips[2:]}", "key": os.environ["CENSUS_API_KEY"]})
        r.raise_for_status()
        rows = r.json()
        acs = pd.DataFrame(rows[1:], columns=rows[0])
        acs.to_csv(cache, index=False)
    acs["bg"] = acs.state + acs.county + acs.tract + acs["block group"]
    a = acs.set_index("bg")
    k = {3: 0, 4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 10: 0, 11: 1, 12: 2, 13: 3, 14: 4, 15: 5}
    veh = sum(pd.to_numeric(a[f"B25044_{i:03d}E"], errors="coerce") * n for i, n in k.items())
    b = blocks[["GEOID20", "HOUSING20"]].copy()
    b["bg"] = b.GEOID20.str[:12]
    share = b.HOUSING20 / b.groupby("bg").HOUSING20.transform("sum").replace(0, np.nan)
    missing = veh.isna().sum()
    if missing:
        log(f"{name}: {missing} block groups with no ACS vehicle estimate (treated as 0)")
    return (share * b.bg.map(veh).fillna(0)).fillna(0).set_axis(blocks.index)


# ---------------------------------------------------------------- ranking ---
def _selfish_fields(g, w, targets, managed, vehicles) -> dict:
    """Managed vs self-routed clearance (hazardnet.clm). Self-routed is a range:
    bulk (rationed) to last car out (strict)."""
    from hazardnet.clm import selfish_throughput
    s = selfish_throughput(g, w, targets, managed)
    inv = lambda x: vehicles / x if x and x > 0 else np.inf   # noqa: E731
    return {"managed_vph": managed, "selfish_strict_vph": s["D_strict"],
            "selfish_rationed_vph": s["rationed"],
            "clear_h_managed": inv(managed),
            "clear_h_selfish_bulk": inv(s["rationed"]),
            "clear_h_selfish_last": inv(s["D_strict"]),
            "gap_bulk": 1 - min(s["rationed"], managed) / managed if managed else np.nan,
            "gap_last": 1 - s["D_strict"] / managed if managed else np.nan,
            "clm_converged": s["converged"], "clm_rationed_converged": s["rationed_converged"]}


def rank(name: str) -> pd.DataFrame:
    """Per-community measures with R3 destinations (D1). Writes
    outputs/tables/<area>_communities.csv."""
    from hazardnet import accessibility, time_to_targets
    from hazardnet.clm import managed_throughput, selfish_throughput
    out = INTERIM / name
    rg = pickle.loads((out / "roads.pkl").read_bytes())
    com = gpd.read_file(out / "communities.gpkg")
    z = gpd.read_file(out / "fhsz.gpkg")
    cty = gpd.read_file(out / "county.gpkg")
    g = rg.g
    nodes = node_table(rg)
    rule = CFG["targets"][CFG["targets"]["default"]]
    hz_thr = CFG["hazard"]["headline_threshold"]
    hz_sens = CFG["hazard"]["sensitivity_threshold"]

    # blocks -> nearest road node, with population and vehicles
    fips = CFG["areas"][name]["county_fips"][2:]
    bbox = tuple(cty.to_crs(4269).total_bounds)
    blocks = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2020_06_tabblock20.zip'}", bbox=bbox,
                           columns=["COUNTYFP20", "GEOID20", "POP20", "HOUSING20"])
    blocks = blocks[(blocks.COUNTYFP20 == fips) & (blocks.POP20 > 0)].to_crs(MCRS)
    blocks["veh"] = vehicles_by_block(name, blocks)
    bpt = blocks.set_geometry(blocks.representative_point())
    bpt = gpd.sjoin(bpt, com[["cid", "geometry"]], predicate="within", how="inner")

    ends = np.asarray(g.get_edgelist())
    hmax = np.asarray(g.es["hazard_max"])
    rows = []
    for _, c in com[com.POP20 > 0].iterrows():
        inside = shapely.contains_xy(c.geometry, nodes.geometry.x.values, nodes.geometry.y.values)
        members = np.flatnonzero(inside)
        b = bpt[bpt.cid == c.cid]
        base = {"cid": c.cid, "community": c["name"], "kind": c.kind,
                "population": int(c.POP20), "vehicles": float(b.veh.sum()),
                "n_nodes": int(len(members))}
        if len(members) == 0:
            rows.append({**base, "note": "no drivable OSM node inside polygon"}); continue
        targets = rule_targets(rule, nodes, z, c.geometry)
        acc = accessibility(g, {c.cid: members}, targets, hazard="hazard_max",
                            threshold=hz_thr, population={c.cid: c.POP20}).iloc[0]
        row = {**base, **{k: acc[k] for k in ("n_disjoint", "capacity_vph", "tt_min",
                                              "efficiency", "exposed_share",
                                              "people_per_capacity", "cut_off")}}
        # hazard-free exits: drop hazardous arcs OUTSIDE the town (keep its own streets)
        internal = inside[ends[:, 0]] & inside[ends[:, 1]]
        for thr, tag in ((hz_thr, "vh"), (hz_sens, "h")):
            h = g.copy()
            h.delete_edges(np.flatnonzero((hmax >= thr) & ~internal).tolist())
            a2 = accessibility(h, {c.cid: members}, targets).iloc[0]
            row[f"n_disjoint_nohaz_{tag}"] = a2.n_disjoint
            row[f"capacity_nohaz_{tag}"] = a2.capacity_vph
            row[f"cut_off_nohaz_{tag}"] = a2.cut_off
        # CLM-style: demand spread over nodes by where vehicles are
        snap = gpd.sjoin_nearest(b[["veh", "geometry"]], nodes.iloc[members][["vid", "geometry"]])
        w = snap.groupby("vid").veh.sum()
        reach = acc.tt_min < np.inf
        # origins with no route to any destination (e.g. isolated OSM fragments)
        # would make every demand level infeasible; report them, route the rest
        t_node = time_to_targets(g, targets)
        stranded = {int(k): float(v) for k, v in w.items() if not np.isfinite(t_node[int(k)])}
        row["stranded_vehicles"] = sum(stranded.values())
        w = {int(k): float(v) for k, v in w.items() if v > 0 and int(k) not in stranded}
        if not reach:
            row["note"] = "no route to any R3 destination"
        elif not w:
            row["note"] = "no ACS vehicles in its blocks; CLM run skipped"
        elif acc.capacity_vph > 0:
            managed, _ = managed_throughput(g, w, targets, acc.capacity_vph)
            row.update(_selfish_fields(g, w, targets, managed, row["vehicles"]))
        rows.append(row)
        log(f"{name}: {c['name']}: {row.get('n_disjoint')} paths, "
            f"{row.get('capacity_vph', 0):,.0f} veh/h, no-VH {row.get('capacity_nohaz_vh', 0):,.0f}, "
            f"clear managed {row.get('clear_h_managed', float('nan')):.1f} h, self-routed "
            f"{row.get('clear_h_selfish_bulk', float('nan')):.1f}-{row.get('clear_h_selfish_last', float('nan')):.1f} h")
    df = pd.DataFrame(rows).sort_values("people_per_capacity", ascending=False)
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / f"{name}_communities.csv", index=False)
    return df


# ---------------------------------------------------------- camp fire check ---
def prefire_vehicles(places: list[str], year: int = 2018) -> pd.DataFrame:
    """ACS 5-yr (2014-18 = pre-fire) population, households and vehicles for
    named places, same B25044 method as vehicles_by_block."""
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    cache = INTERIM / "butte" / f"acs{year}_places.csv"
    if not cache.exists():
        v = ",".join(f"B25044_{i:03d}E" for i in range(1, 16))
        r = requests.get(f"https://api.census.gov/data/{year}/acs/acs5", timeout=120, params={
            "get": f"NAME,B01003_001E,{v}", "for": "place:*", "in": "state:06",
            "key": os.environ["CENSUS_API_KEY"]}).json()
        pd.DataFrame(r[1:], columns=r[0]).to_csv(cache, index=False)
    a = pd.read_csv(cache, dtype=str)
    a["name"] = a.NAME.str.split(",").str[0].str.replace(r" (town|city|CDP)$", "", regex=True)
    k = {3: 0, 4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 10: 0, 11: 1, 12: 2, 13: 3, 14: 4, 15: 5}
    a["vehicles"] = sum(pd.to_numeric(a[f"B25044_{i:03d}E"]) * n for i, n in k.items())
    a["population"] = pd.to_numeric(a.B01003_001E)
    return a[a.name.isin(places)][["name", "place", "population", "vehicles"]]


def retro(name: str, ref: dict, group: list, *, tag: str, vehicles: str = "blocks",
          weights: str = "vehicles") -> dict:
    """Fire retrospective for one group of communities evacuated TOGETHER (run
    as one origin; separate runs would count shared exits twice). Destinations
    R3 from the group as a whole; exposure against the FINAL perimeter (FRAP
    gives no progression).
      vehicles="blocks":  ACS 2020-24 B25044 apportioned to 2020 blocks (pre-fire
                          for the 2025 fires); weights="vehicles" spreads demand
                          over nodes where those vehicles are.
      vehicles="places2018": ACS 2014-18 by place (pre-fire for Camp 2018, whose
                          2020 blocks are post-fire); use with weights="even"."""
    import json
    from hazardnet import accessibility, time_to_targets
    from hazardnet.clm import managed_throughput, selfish_throughput
    out = INTERIM / name
    rg = pickle.loads((out / "roads.pkl").read_bytes())
    g = rg.g
    com = gpd.read_file(out / "communities.gpkg")
    z = gpd.read_file(out / "fhsz.gpkg")
    nodes = node_table(rg)
    grp = com[com.name.isin(group)]
    ridge_geom = grp.union_all()
    inside = shapely.contains_xy(ridge_geom, nodes.geometry.x.values, nodes.geometry.y.values)
    members = np.flatnonzero(inside)
    targets = rule_targets(CFG["targets"][CFG["targets"]["default"]], nodes, z, ridge_geom)

    fire = fire_perimeter(ref, bbox=tuple(gpd.GeoSeries([ridge_geom], crs=MCRS)
                                          .to_crs(4326).total_bounds)).union_all()

    acc = accessibility(g, {"ridge": members}, targets).iloc[0]
    # which min-cut arcs lie inside the final perimeter?
    d = g.copy()
    n = d.vcount(); d.add_vertices(2); s, t = n, n + 1
    d.add_edges([(s, int(v)) for v in members] + [(int(v), t) for v in targets])
    cap = np.asarray(g.es["capacity_vph"], dtype=float)
    f = d.maxflow(s, t, capacity=np.concatenate(
        [cap, np.full(len(members) + len(targets), 1e12)]).tolist())
    cut = [e for e in f.cut if e < g.ecount()]
    edges = rg.edges.to_crs(MCRS)
    in_fire = edges.geometry.values[cut]
    burned = shapely.intersects(fire, in_fire)
    cut_tbl = pd.DataFrame({"eid": cut, "name": edges.iloc[cut]["name"].astype(str).values,
                            "ref": edges.iloc[cut]["ref"].astype(str).values if "ref" in edges else "",
                            "road_class": edges.iloc[cut]["road_class"].values,
                            "capacity_vph": cap[cut], "lanes_imputed": edges.iloc[cut]["lanes_imputed"].values,
                            "hazard_max": np.asarray(g.es["hazard_max"])[cut],
                            "inside_camp_perimeter": burned})
    cut_tbl.to_csv(TABLES / f"retro_{tag}_min_cut.csv", index=False)

    t_node = time_to_targets(g, targets)
    if vehicles == "places2018":
        pre = prefire_vehicles(list(group))
        veh, pop = float(pre.vehicles.sum()), int(pre.population.sum())
    else:
        cty = gpd.read_file(out / "county.gpkg")
        fips = CFG["areas"][name]["county_fips"][2:]
        bl = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2020_06_tabblock20.zip'}",
                           bbox=tuple(gpd.GeoSeries([ridge_geom], crs=MCRS).to_crs(4269).total_bounds),
                           columns=["COUNTYFP20", "GEOID20", "POP20", "HOUSING20"])
        bl = bl[(bl.COUNTYFP20 == fips) & (bl.POP20 > 0)].to_crs(MCRS)
        bl["veh"] = vehicles_by_block(name, bl)
        bl = bl.set_geometry(bl.representative_point())
        bl = bl[shapely.contains_xy(ridge_geom, bl.geometry.x.values, bl.geometry.y.values)]
        veh, pop = float(bl.veh.sum()), int(bl.POP20.sum())
    if weights == "even":
        w = {int(v): 1.0 for v in members if np.isfinite(t_node[v])}
    else:
        snap = gpd.sjoin_nearest(bl[["veh", "geometry"]], nodes.iloc[members][["vid", "geometry"]])
        ws = snap.groupby("vid").veh.sum()
        w = {int(k): float(v) for k, v in ws.items() if v > 0 and np.isfinite(t_node[int(k)])}
    managed, binding = managed_throughput(g, w, targets, acc.capacity_vph)
    b_geom = edges.geometry.values[binding]
    pd.DataFrame({"eid": binding, "name": edges.iloc[binding]["name"].astype(str).values,
                  "ref": edges.iloc[binding]["ref"].astype(str).values if "ref" in edges else "",
                  "road_class": edges.iloc[binding]["road_class"].values,
                  "capacity_vph": cap[binding],
                  "lanes_imputed": edges.iloc[binding]["lanes_imputed"].values,
                  "hazard_max": np.asarray(g.es["hazard_max"])[binding],
                  "inside_final_perimeter": shapely.intersects(fire, b_geom)}
                 ).to_csv(TABLES / f"retro_{tag}_binding.csv", index=False)
    res = {
        "fire": f"{ref['name']} {ref['year']}", "group": list(group), "prefire_population": pop,
        "prefire_vehicles": veh, "n_disjoint": int(acc.n_disjoint),
        "mincut_capacity_vph": float(acc.capacity_vph),
        "mincut_share_inside_final_perimeter": float(cap[cut][burned].sum() / cap[cut].sum()),
        "clear_h_mincut": veh / acc.capacity_vph,
        **_selfish_fields(g, w, targets, managed, veh),
        "binding_capacity_vph": float(cap[binding].sum()),
        "binding_share_inside_final_perimeter":
            float(cap[binding][shapely.intersects(fire, b_geom)].sum() / cap[binding].sum())
            if len(binding) else None,
        "note": f"final perimeter, not progression; vehicles={vehicles}, weights={weights}; "
                "ACS B25044 with 5+ counted as 5; assumes every vehicle leaves",
    }
    # sensitivity: untagged primary/secondary/tertiary arcs given 2 lanes per
    # direction (the min cut lands on narrow sections, which are mostly untagged)
    h = g.copy()
    wide = np.isin(np.asarray(h.es["road_class"], dtype=object),
                   ["primary", "secondary", "tertiary"]) & np.asarray(h.es["lanes_imputed"])
    c2 = cap.copy(); c2[wide] *= 2
    h.es["capacity_vph"] = c2.tolist()
    acc2 = accessibility(h, {"ridge": members}, targets).iloc[0]
    res["sens_2lane_mincut_vph"] = float(acc2.capacity_vph)
    res["sens_2lane_clear_h_mincut"] = veh / acc2.capacity_vph
    # same sensitivity on the managed bound, so it pairs with clear_h_managed
    m2, _ = managed_throughput(h, w, targets, acc2.capacity_vph)
    res["sens_2lane_managed_vph"] = m2
    res["sens_2lane_clear_h_managed"] = veh / m2 if m2 > 0 else None
    (TABLES / f"retro_{tag}_summary.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    log(f"retro {tag}: {json.dumps(res)}")
    return res



def camp(name: str = "butte") -> dict:
    return retro(name, CFG["areas"][name]["reference_fires"][0],
                 ["Paradise", "Magalia", "Concow"], tag="camp_ridge",
                 vehicles="places2018", weights="even")


def retro_la(name: str = "la_foothills") -> list:
    com = gpd.read_file(INTERIM / name / "communities.gpkg")
    out = []
    for ref in CFG["areas"][name]["reference_fires"]:
        grp = com[(com.cluster == ref["name"]) & (com.POP20 > 0) &
                  (com.burn_share >= CFG["areas"][name]["retro_min_share"])]
        log(f"{name}: {ref['name']} group = {list(grp.name)}")
        out.append(retro(name, ref, list(grp.name), tag=ref["name"].lower()))
    return out

if __name__ == "__main__":
    area, stage = sys.argv[1], sys.argv[2]
    if stage == "roads":
        roads(area)
    elif stage == "prepare":
        prepare(area)
    elif stage == "camp":
        camp(area)
    elif stage == "retro":
        retro_la(area)
    elif stage == "rank":
        rank(area)
    elif stage == "targets":
        targets_map(area, sys.argv[3] if len(sys.argv) > 3 else "Paradise")
