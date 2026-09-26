"""Part A: how a California-sized road graph comes apart under node removal.

    python -m studies.california.run_part_a snap
    python -m studies.california.run_part_a dimacs
    python -m studies.california.run_part_a snap_c      # degree-2 chains contracted
    python -m studies.california.run_part_a dimacs_c    #   (review check; no E curve)

Removal orders: random (several seeds), degree (ties broken at random) and
sampled betweenness, each ranked ONCE on the intact graph (not recomputed
after each removal; too costly at ~2M nodes). Plus one random EDGE-removal run
for bond percolation. Distances are in hops for both graphs so the two are
comparable (SNAP has no lengths).

Outputs
    outputs/tables/part_a_<graph>_curves.csv      S1, S2 (and E where computed)
    data/interim/part_a_<graph>_load.npz          degree + betweenness per node
    data/interim/part_a_dimacs_top_betweenness.csv   (dimacs) top 1% with lon/lat
"""
from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from hazardnet import (betweenness_sampled, clip_to_polygon, component_sizes, contract_degree2,
                       efficiency_sampled, load_roads, map_to_kept, remove_and_measure)

ROOT = Path(__file__).resolve().parents[2]
RAW, INTERIM = ROOT / "data" / "raw", ROOT / "data" / "interim"
TABLES, LOGS = ROOT / "outputs" / "tables", ROOT / "logs"
CFG = yaml.safe_load((Path(__file__).with_name("config.yaml")).read_text(encoding="utf-8"))["part_a"]


def log(msg, fh):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True); fh.write(line + "\n"); fh.flush()


def load(which: str):
    if which.endswith("_c"):
        return contract_degree2(load(which[:-2]))
    if which == "snap":
        return load_roads(source="edgelist", path=RAW / "snap" / "roadNet-CA.txt.gz")
    rg = load_roads(source="dimacs", gr=RAW / "dimacs" / "USA-road-d.CAL.gr.gz",
                    co=RAW / "dimacs" / "USA-road-d.CAL.co.gz")
    states = gpd.read_file(f"zip://{RAW / 'tiger' / 'cb_2024_us_state_500k.zip'}")
    ca = states.loc[states.STATEFP == CFG["dimacs_state_fips"]].to_crs(4326).geometry.iloc[0]
    return clip_to_polygon(rg, ca)


def main(which: str) -> None:
    for d in (INTERIM, TABLES, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    fh = open(LOGS / f"part_a_{which}.log", "a", encoding="utf-8")
    rng = np.random.default_rng(CFG["seed"])

    t0 = time.time()
    rg = load(which)
    g, N = rg.g, rg.n
    cs = component_sizes(g)
    log(f"{which}: n={N} m={rg.m} largest={cs[0]} second={cs[1]} meta={rg.meta} "
        f"({time.time()-t0:.0f}s)", fh)

    # ---- rankings -----------------------------------------------------------
    deg = np.asarray(g.degree())
    cache = INTERIM / f"part_a_{which}_load.npz"
    if cache.exists():
        btw = np.load(cache)["betweenness"]
        log("betweenness: cached", fh)
    else:
        t = time.time()
        btw = betweenness_sampled(g, CFG["betweenness_sources"], seed=CFG["seed"])
        np.savez_compressed(cache, degree=deg, betweenness=btw)
        log(f"betweenness: k={CFG['betweenness_sources']} in {time.time()-t:.0f}s", fh)

    tie = rng.random(N)
    orders = {
        "degree": np.lexsort((tie, -deg)),
        "betweenness": np.lexsort((tie, -btw)),
    }
    for s in range(CFG["random_seeds_s"]):
        orders[f"random_{s}"] = rng.permutation(N)

    e_sources = rng.choice(N, size=CFG["efficiency_sources"], replace=False)

    def s_measure(h, kept):
        c = component_sizes(h)
        return {"S1": c[0] / N, "S2": c[1] / N}

    def se_measure(h, kept):
        return {**s_measure(h, kept),
                "E": efficiency_sampled(h, N, map_to_kept(e_sources, kept))}

    # ---- node removal curves --------------------------------------------------
    frames = []
    for name, order in orders.items():
        t = time.time()
        df = remove_and_measure(rg, s_measure, ranking=order,
                                fractions=CFG["fractions_s"], element="node")
        want_e = name in ("degree", "betweenness") or \
            (name.startswith("random_") and int(name.split("_")[1]) < CFG["random_seeds_e"])
        if want_e:
            de = remove_and_measure(rg, se_measure, ranking=order,
                                    fractions=CFG["fractions_e"], element="node")
            df = df.merge(de[["fraction", "E"]], on="fraction", how="left")
        df.insert(0, "order", name); df.insert(0, "element", "node")
        frames.append(df)
        log(f"node/{name}: {time.time()-t:.0f}s  S1@0.1={df.loc[df.fraction.sub(.1).abs().idxmin(),'S1']:.3f}", fh)
        pd.concat(frames).to_csv(TABLES / f"part_a_{which}_curves.csv", index=False)

    # ---- bond percolation (random edge removal) -------------------------------
    t = time.time()
    df = remove_and_measure(rg, s_measure, ranking=rng.permutation(rg.m),
                            fractions=CFG["fractions_s"], element="edge")
    df.insert(0, "order", "random_0"); df.insert(0, "element", "edge")
    frames.append(df)
    pd.concat(frames).to_csv(TABLES / f"part_a_{which}_curves.csv", index=False)
    log(f"edge/random: {time.time()-t:.0f}s", fh)

    # ---- dimacs: where are the high-load junctions? -----------------------------
    if which == "dimacs":
        top = np.argsort(-btw)[: max(1, N // 100)]
        pd.DataFrame({"lon": np.asarray(g.vs["x"])[top], "lat": np.asarray(g.vs["y"])[top],
                      "betweenness": btw[top], "degree": deg[top]}
                     ).to_csv(INTERIM / "part_a_dimacs_top_betweenness.csv", index=False)
        log(f"exported top {len(top)} betweenness vertices", fh)
    log(f"done in {(time.time()-t0)/60:.1f} min", fh)


if __name__ == "__main__":
    main(sys.argv[1])
