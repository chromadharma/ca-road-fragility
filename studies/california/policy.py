"""Policy layer (DESIGN §10): the safety ladder and what each fix buys.

    python -m studies.california.policy butte extended   # build roads incl. fire roads (I4)
    python -m studies.california.policy butte run
    python -m studies.california.policy la_foothills extended
    python -m studies.california.policy la_foothills run

Units = every populated community plus each fire group evacuated together
(Camp ridge; Palisades; Eaton). All clearance figures are the managed
(coordinated) bound unless labelled self-routed; they assume every vehicle
leaves. Outputs: outputs/tables/policy_<area>.csv
"""
from __future__ import annotations

import json
import pickle
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from hazardnet import accessibility, load_hazard, overlay, time_to_targets
from hazardnet.clm import managed_throughput
from hazardnet.interventions import contraflow, managed_flow, widen
from studies.california import part_b as pb

CFG, INTERIM, TABLES, RAW, MCRS = pb.CFG, pb.INTERIM, pb.TABLES, pb.RAW, pb.MCRS
POL = CFG["policy"]
log = pb.log


# ------------------------------------------------------------------ graphs ---
def extended(name: str) -> None:
    """Road graph including fire roads / gated service roads (I4), from a local
    extract, with the same hazard overlay as the base graph."""
    from hazardnet.osm import load_osm
    a = CFG["areas"][name]
    pbf = a.get("osm_pbf_extended") or a.get("osm_pbf")
    _, area = pb.study_area(name)
    area_ll = gpd.GeoSeries([area], crs=MCRS).to_crs(4326).iloc[0]
    extra = {"highway": POL["extra_highway"], "exclude_service": POL["extra_exclude_service"],
             "exclude_tracktype": POL["extra_exclude_tracktype"]}
    t = time.time()
    rg = load_osm(area_ll, capacity_table=CFG["capacity_table"], pbf=RAW / pbf,
                  work_dir=INTERIM / name, extra=extra)
    z = gpd.read_file(INTERIM / name / "fhsz.gpkg")
    overlay(rg, load_hazard(z, kind="polygon", field="FHSZ", levels=CFG["hazard"]["levels"]),
            metric_crs=MCRS)
    (INTERIM / name / "roads_ext.pkl").write_bytes(pickle.dumps(rg))
    ex = np.asarray(rg.g.es["is_extra"])
    km = float(np.asarray(rg.g.es["length_m"])[ex].sum() / 1000 / 2)   # ~2 arcs per way
    log(f"{name}: extended graph {rg.meta}; {ex.sum()} extra arcs (~{km:,.0f} km) "
        f"in {time.time() - t:.0f}s")


# ------------------------------------------------------------------- units ---
def units(name: str, com: gpd.GeoDataFrame) -> list[dict]:
    out = [{"unit": r["name"], "kind": "community", "geom": r.geometry, "pop2020": int(r.POP20)}
           for _, r in com[(com.POP20 > 0) & ~com.name.str.contains("National Forest")].iterrows()]
    for f in sorted(TABLES.glob("retro_*_summary.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        if not set(r["group"]) <= set(com.name):
            continue
        out.append({"unit": f"{r['fire']} group", "kind": "fire_group",
                    "geom": com[com.name.isin(r["group"])].union_all(),
                    "vehicles_override": r["prefire_vehicles"],
                    "even_weights": r["note"].find("weights=even") >= 0,
                    "tag": f.stem.replace("retro_", "").replace("_summary", ""),
                    "selfish_last_h": r["clear_h_selfish_last"]})
    return out


def demand(name, u, nodes, members, t_node, blocks):
    """Vehicle weights over member nodes (or even weights), and total vehicles."""
    ok = [int(v) for v in members if np.isfinite(t_node[v])]
    b = blocks[shapely.contains_xy(u["geom"], blocks.geometry.x.values, blocks.geometry.y.values)]
    veh = u.get("vehicles_override", float(b.veh.sum()))
    if u.get("even_weights") or len(b) == 0:
        return {v: 1.0 for v in ok}, veh
    snap = gpd.sjoin_nearest(b[["veh", "geometry"]], nodes.iloc[members][["vid", "geometry"]])
    w = snap.groupby("vid").veh.sum()
    okset = set(ok)
    return {int(k): float(v) for k, v in w.items() if v > 0 and int(k) in okset}, veh


def clear_h(g, w, targets, veh, upper):
    if not w or upper <= 0:
        return np.inf, []
    D, binding = managed_throughput(g, w, targets, upper)
    return (veh / D if D > 0 else np.inf), binding


def without(g, mask):
    h = g.copy()
    h.delete_edges(np.flatnonzero(mask).tolist())
    return h


def i4_unit(name, u, rgx, nodes_x, z, rule, blocks, veh) -> dict:
    """I4 for one unit on the extended graph, compared like for like: demand is
    placed only on nodes of the ordinary drive network (a node with at least
    one non-extra arc) that can reach a destination without extra roads. The
    first version snapped demand to any node, often one on a service road, so
    removing the extra roads stranded origins and every 'without' case read as
    infinite, even Biggs'."""
    gx = rgx.g
    ex = np.asarray(gx.es["is_extra"])
    hx = np.asarray(gx.es["hazard_max"])
    ends_x = np.asarray(gx.get_edgelist())
    ins_x = shapely.contains_xy(u["geom"], nodes_x.geometry.x.values, nodes_x.geometry.y.values)
    drive_node = np.zeros(gx.vcount(), bool)
    drive_node[ends_x[~ex].ravel()] = True
    mem_x = np.flatnonzero(ins_x & drive_node)
    if len(mem_x) == 0:
        return {}
    tgt_x = pb.rule_targets(rule, nodes_x, z, u["geom"])
    int_x = ins_x[ends_x[:, 0]] & ins_x[ends_x[:, 1]]
    g_wo = without(gx, ex)
    t_wo = time_to_targets(g_wo, tgt_x)
    wx, _ = demand(name, u, nodes_x, mem_x, t_wo, blocks)
    a_with = accessibility(gx, {0: mem_x}, tgt_x).iloc[0]
    a_wo = accessibility(g_wo, {0: mem_x}, tgt_x).iloc[0]
    gx_vh = without(gx, (hx >= 3) & ~int_x)
    vh_with, _ = clear_h(gx_vh, wx, tgt_x, veh, a_with.capacity_vph)
    vh_wo, _ = clear_h(without(gx_vh, np.asarray(gx_vh.es["is_extra"])), wx, tgt_x, veh,
                       a_wo.capacity_vph)
    used_km = 0.0
    if np.isfinite(vh_with) and wx:
        f = managed_flow(gx_vh, wx, tgt_x, veh / vh_with)
        use = (f > 1e-6) & np.asarray(gx_vh.es["is_extra"])
        used_km = float(np.asarray(gx_vh.es["length_m"])[use].sum() / 1000)
    return {"I4_n_disjoint_without": int(a_wo.n_disjoint),
            "I4_n_disjoint_with": int(a_with.n_disjoint),
            "I4_vh_free_h_without": vh_wo, "I4_vh_free_h_with": vh_with,
            "I4_fire_road_km_used": used_km}


def _load_i4(name: str) -> dict:
    out = INTERIM / name
    rgx = pickle.loads((out / "roads_ext.pkl").read_bytes())
    com = gpd.read_file(out / "communities.gpkg")
    fips = CFG["areas"][name]["county_fips"][2:]
    blocks = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2020_06_tabblock20.zip'}",
                           bbox=tuple(com.to_crs(4269).total_bounds),
                           columns=["COUNTYFP20", "GEOID20", "POP20", "HOUSING20"])
    blocks = blocks[(blocks.COUNTYFP20 == fips) & (blocks.POP20 > 0)].to_crs(MCRS)
    blocks["veh"] = pb.vehicles_by_block(name, blocks)
    return {"rgx": rgx, "nodes_x": pb.node_table(rgx), "z": gpd.read_file(out / "fhsz.gpkg"),
            "rule": CFG["targets"][CFG["targets"]["default"]],
            "blocks": blocks.set_geometry(blocks.representative_point()),
            "veh": pd.read_csv(TABLES / f"policy_{name}.csv").set_index("unit")["vehicles"]}


def _init_i4(name: str) -> None:
    global _S
    _S = _load_i4(name)


def _work_i4(args):
    name, u = args
    t0 = time.time()
    r = i4_unit(name, u, _S["rgx"], _S["nodes_x"], _S["z"], _S["rule"], _S["blocks"],
                _S["veh"].loc[u["unit"]])
    log(f"policy-i4 {name}: {u['unit']}: {r} [{time.time() - t0:.0f}s]")
    return u["unit"], r


def i4(name: str, workers: int | None = None) -> pd.DataFrame:
    """Recompute only the I4 columns and merge them into policy_<area>.csv."""
    workers = workers or POL.get("workers", 1)
    com = gpd.read_file(INTERIM / name / "communities.gpkg")
    pol = pd.read_csv(TABLES / f"policy_{name}.csv").set_index("unit")
    pol = pol.drop(columns=[c for c in pol.columns if c.startswith("I4_")])
    us = [u for u in units(name, com) if u["unit"] in pol.index]
    rows = dict(_map(name, _work_i4, _init_i4, us, workers))
    pol = pol.join(pd.DataFrame.from_dict(rows, orient="index"))
    pol.reset_index().to_csv(TABLES / f"policy_{name}.csv", index=False)
    return pol


# --------------------------------------------------------------------- run ---
# Units are independent, so they run in parallel worker processes (config
# policy.workers). Each worker loads the shared state once. Serial and parallel
# runs give identical rows; parallel only changes the wall-clock time.
_S = None


def _load(name: str) -> dict:
    out = INTERIM / name
    rg = pickle.loads((out / "roads.pkl").read_bytes())
    g = rg.g
    com = gpd.read_file(out / "communities.gpkg")
    z = gpd.read_file(out / "fhsz.gpkg")
    cty = gpd.read_file(out / "county.gpkg")
    nodes = pb.node_table(rg)
    rule = CFG["targets"][CFG["targets"]["default"]]
    ranks = pd.read_csv(TABLES / f"{name}_communities.csv")
    ranks = ranks.set_index("community")

    fips = CFG["areas"][name]["county_fips"][2:]
    blocks = gpd.read_file(f"zip://{RAW / 'tiger' / 'tl_2020_06_tabblock20.zip'}",
                           bbox=tuple(com.to_crs(4269).total_bounds),
                           columns=["COUNTYFP20", "GEOID20", "POP20", "HOUSING20"])
    blocks = blocks[(blocks.COUNTYFP20 == fips) & (blocks.POP20 > 0)].to_crs(MCRS)
    blocks["veh"] = pb.vehicles_by_block(name, blocks)
    blocks = blocks.set_geometry(blocks.representative_point())

    ext_path = out / "roads_ext.pkl"
    rgx = pickle.loads(ext_path.read_bytes()) if ext_path.exists() else None
    nodes_x = pb.node_table(rgx) if rgx else None

    ends = np.asarray(g.get_edgelist())
    hmax = np.asarray(g.es["hazard_max"])
    length = np.asarray(g.es["length_m"], dtype=float)
    cls = np.asarray(g.es["road_class"], dtype=object)
    per_lane = np.array([CFG["capacity_table"].get(c, CFG["capacity_table"]["default"])
                         ["per_lane_vph"] for c in cls], dtype=float)
    L2, L3 = POL["rungs"]["L2_clear_h"], POL["rungs"]["L3_clear_h"]
    e_m = rg.edges.to_crs(MCRS)
    mid = e_m.geometry.interpolate(0.5, normalized=True).values
    nm = e_m["name"].astype(str).where(e_m["name"].notna(), None)
    ref = e_m["ref"].astype(str).where(e_m["ref"].notna(), None) if "ref" in e_m else None
    road_key = np.array([n if n and n != "nan" else (r if r and r != "nan" else None)
                         for n, r in zip(nm, ref if ref is not None else [None] * len(nm))],
                        dtype=object)

    return {k: v for k, v in locals().items()}


def _unit(name: str, S: dict, u: dict):
    g, nodes, z, rule, ranks, blocks = S["g"], S["nodes"], S["z"], S["rule"], S["ranks"], S["blocks"]
    rg, rgx, nodes_x, ends, hmax = S["rg"], S["rgx"], S["nodes_x"], S["ends"], S["hmax"]
    length, cls, per_lane, mid, road_key = S["length"], S["cls"], S["per_lane"], S["mid"], S["road_key"]
    L2, L3 = S["L2"], S["L3"]
    t0 = time.time()
    inside = shapely.contains_xy(u["geom"], nodes.geometry.x.values, nodes.geometry.y.values)
    members = np.flatnonzero(inside)
    if len(members) == 0:
        return None
    targets = pb.rule_targets(rule, nodes, z, u["geom"])
    t_node = time_to_targets(g, targets)
    w, veh = demand(name, u, nodes, members, t_node, blocks)
    acc = accessibility(g, {u["unit"]: members}, targets).iloc[0]
    upper = float(acc.capacity_vph)
    internal = inside[ends[:, 0]] & inside[ends[:, 1]]
    row = {"unit": u["unit"], "kind": u["kind"], "vehicles": veh,
           "n_disjoint": int(acc.n_disjoint)}

    base_h, binding = clear_h(g, w, targets, veh, upper)
    g_vh = without(g, (hmax >= 3) & ~internal)
    g_h = without(g, (hmax >= 2) & ~internal)
    vh_h, _ = clear_h(g_vh, w, targets, veh, upper)
    h_h, _ = clear_h(g_h, w, targets, veh, upper)
    rung = {"L1": acc.n_disjoint >= 2, "L2": base_h <= L2, "L3": base_h <= L3,
            "L4": vh_h <= L3, "L5": h_h <= L3}
    met = 0
    for k in ("L1", "L2", "L3", "L4", "L5"):
        if not rung[k]:
            break
        met += 1
    row.update({"clear_h_managed": base_h, "clear_h_vh_free": vh_h, "clear_h_h_free": h_h,
                **{f"meets_{k}": bool(v) for k, v in rung.items()}, "ladder_rung": met})

    # I1: managed vs self-routed (last car out), from the earlier runs
    selfish = u.get("selfish_last_h")
    if selfish is None and u["unit"] in ranks.index:
        selfish = ranks.loc[u["unit"], "clear_h_selfish_last"]
    row["I1_selfish_last_h"] = selfish

    # I2: contraflow on successive binding cuts
    # applied only where it helps: reversing a two-way road also removes
    # capacity other outbound traffic used the other way (Kinneloa Mesa got
    # worse). Divided roads have no same-node reverse arc, so contraflow
    # does not reach them here: a stated limitation (Palisades Dr).
    # Every round reverses the current binding cut (cumulatively); the best
    # state over all rounds is kept. Stopping at the first round that does not
    # help was wrong: on the Camp ridge round 1 alone gains nothing but rounds
    # 1-3 together cut clearance to 2.9 h.
    gc, km, cur_c, km_best = g, 0.0, base_h, 0.0
    for _ in range(POL["contraflow_rounds"]):
        _, b = clear_h(gc, w, targets, veh, upper * 2)
        gc, m = contraflow(gc, b)
        km += m / 1000
        h_c, _ = clear_h(gc, w, targets, veh, upper * 2)
        if h_c < cur_c - 1e-6:
            cur_c, km_best = h_c, km
    km = km_best
    row["I2_contraflow_h"], row["I2_contraflow_km"] = cur_c, km

    # I3: widen whole named roads, greedily. Widening one section at a time
    # fails when several sections of a road are equally tight (Camp: no gain
    # at all), and it is not how the policy works: an agency widens a road.
    # A road = every arc sharing the binding arc's name (or ref) within
    # 15 km of the unit; one lane added to each of its arcs.
    near = shapely.dwithin(mid, u["geom"], 15000)
    gw, lane_km, steps, cur = g, 0.0, [], base_h
    for _ in range(POL["widen_steps"]):
        if cur <= L3:
            break
        _, b = clear_h(gw, w, targets, veh, upper * 3)
        best = None
        # sorted, ties broken by the cheaper road: iterating a set of names
        # depends on per-process string hashing, so parallel runs picked
        # different roads at exact ties (Chico, step 2)
        for k in sorted({road_key[e] for e in b if isinstance(road_key[e], str)}):
            arcs = np.flatnonzero((road_key == k) & near)
            cap_w = np.asarray(gw.es["capacity_vph"], dtype=float)
            cap_w[arcs] += per_lane[arcs]
            cand = gw.copy(); cand.es["capacity_vph"] = cap_w.tolist()
            h_new, _ = clear_h(cand, w, targets, veh, upper * 3)
            lk_ = length[arcs].sum() / 1000
            if best is None or (h_new, lk_) < (best[0], best[3]):
                best = (h_new, k, cand, lk_)
        if best is None or best[0] >= cur - 1e-6:
            break
        cur, k, gw, lk = best
        lane_km += lk
        steps.append(f"{k} (+{lk:.1f} lane-km -> {cur:.2f} h)")
    row.update({"I3_widen_h": cur, "I3_lane_km": lane_km, "I3_steps": "; ".join(steps)})

    # I4: fire roads / gated service roads as extra exits (extended graph)
    if rgx is not None:
        row.update(i4_unit(name, u, rgx, nodes_x, z, rule, blocks, veh))
    log(f"policy {name}: {u['unit']}: rung {met}, managed {base_h:.2f} h, "
        f"contraflow {row['I2_contraflow_h']:.2f} h, widen {cur:.2f} h "
        f"(+{lane_km:.1f} lane-km) [{time.time() - t0:.0f}s]")
    return row


def _init(name: str) -> None:
    global _S
    _S = _load(name)


def _work(args):
    name, u = args
    return _unit(name, _S, u)


def _map(name: str, fn, init, us: list, workers: int) -> list:
    if workers <= 1:
        init(name)
        return [fn((name, u)) for u in us]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=workers, initializer=init, initargs=(name,)) as ex:
        return list(ex.map(fn, [(name, u) for u in us]))


def run(name: str, workers: int | None = None) -> pd.DataFrame:
    workers = workers or POL.get("workers", 1)
    com = gpd.read_file(INTERIM / name / "communities.gpkg")
    rows = [r for r in _map(name, _work, _init, units(name, com), workers) if r]
    df = pd.DataFrame(rows)
    df.to_csv(TABLES / f"policy_{name}.csv", index=False)
    return df


if __name__ == "__main__":
    area, stage = sys.argv[1], sys.argv[2]
    kw = {"workers": int(sys.argv[3])} if len(sys.argv) > 3 and stage != "extended" else {}
    {"extended": extended, "run": run, "i4": i4}[stage](area, **kw)
