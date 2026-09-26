"""Figures. House style from viz/viz_theme.py (Viridis + Archivo).

    python -m studies.california.figures a1 snap
    python -m studies.california.figures a1 dimacs
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from viz.viz_theme import (FONT_BOLD, FONT_SEMIBOLD, MUTED, TEXT, footer_config,  # noqa: E402
                           setup_style, style_axes, title_block, viridis_categorical)

TABLES, FIGS, INTERIM = ROOT / "outputs" / "tables", ROOT / "outputs" / "figures", ROOT / "data" / "interim"
LABEL = {"snap": "SNAP roadNet-CA (topology only, 1.97M junctions)",
         "dimacs": "DIMACS CAL clipped to California (1.59M junctions)"}
TITLE = {"snap": "Remove the busiest 1% of junctions and 89% of the network is cut off; "
                 "remove a random 1% and 2% is",
         "dimacs": "A second California road graph: busiest-first still collapses it; "
                   "its extra fragility to random loss is partly an artifact"}
SOURCE = {"snap": "SNAP roadNet-CA (Leskovec et al. 2009), no data vintage stated",
          "dimacs": "9th DIMACS Challenge CAL graph (TIGER/Line-derived), clipped with "
                    "Census 1:500k state outline"}


def _ccdf(x):
    x = np.sort(x[x > 0])
    return x, 1.0 - np.arange(len(x)) / len(x)


def a1(which: str) -> Path:
    df = pd.read_csv(TABLES / f"part_a_{which}_curves.csv")
    load = np.load(INTERIM / f"part_a_{which}_load.npz")
    setup_style()
    c_btw, c_deg, c_rnd = viridis_categorical(3, low=0.05, high=0.85)
    fig, axes = plt.subplots(1, 3, figsize=(17, 6.6),
                             gridspec_kw={"width_ratios": [1.15, 1.15, 1]})
    fig.subplots_adjust(left=0.05, right=0.98, top=0.76, bottom=0.17, wspace=0.28)

    node = df[df.element == "node"]
    rnd = node[node.order.str.startswith("random")]
    for ax, col, ylab in ((axes[0], "S1", "Largest connected piece\n(share of all junctions)"),
                          (axes[1], "E", "Global efficiency\n(relative to intact network)")):
        style_axes(ax)
        base = 1.0 if col == "S1" else node.loc[node.fraction == 0, "E"].dropna().iloc[0]
        r = rnd.dropna(subset=[col]).groupby("fraction")[col].agg(["mean", "min", "max"]) / base
        ax.fill_between(r.index, r["min"], r["max"], color=c_rnd, alpha=0.25, lw=0)
        ax.plot(r.index, r["mean"], color=c_rnd, lw=2.2, label="Random junctions")
        for name, c in (("degree", c_deg), ("betweenness", c_btw)):
            s = node[node.order == name].dropna(subset=[col])
            ax.plot(s.fraction, s[col] / base, color=c, lw=2.6,
                    label=f"Most-connected first ({name})" if name == "degree"
                    else "Busiest first (sampled betweenness)")
        if col == "S1":
            e = df[df.element == "edge"]
            ax.plot(e.fraction, e.S1, color=MUTED, lw=1.6, ls=(0, (4, 3)),
                    label="Random road segments")
        ax.set_xlim(0, 0.8 if col == "S1" else 0.6); ax.set_ylim(0, 1.02)
        ax.set_xlabel("Share removed", fontsize=11.5, fontfamily=FONT_SEMIBOLD, color=TEXT)
        ax.set_ylabel(ylab, fontsize=11.5, fontfamily=FONT_SEMIBOLD, color=TEXT)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    axes[0].legend(frameon=False, fontsize=10.5, loc="upper right")

    ax = axes[2]; style_axes(ax)
    for arr, c, lab in ((load["degree"].astype(float), c_deg, "Roads per junction (degree)"),
                        (load["betweenness"], c_btw, "Routes through a junction (betweenness)")):
        x, y = _ccdf(arr / arr[arr > 0].mean())
        step = max(1, len(x) // 4000)
        ax.loglog(x[::step], y[::step], color=c, lw=2.4, label=lab)
    ax.set_xlim(1e-2, 1e4)
    ax.set_xlabel("Value ÷ its average", fontsize=11.5, fontfamily=FONT_SEMIBOLD, color=TEXT)
    ax.set_ylabel("Share of junctions at or above", fontsize=11.5,
                  fontfamily=FONT_SEMIBOLD, color=TEXT)
    ax.legend(frameon=False, fontsize=10.5, loc="lower left")

    for ax, tag in zip(axes, ("How much of the network stays connected",
                              "How easily the rest can reach each other",
                              "Why: connections are even, load is not")):
        ax.text(0, 1.06, tag, transform=ax.transAxes, fontsize=13, fontfamily=FONT_BOLD,
                color=TEXT)
    title_block(fig, TITLE[which],
                LABEL[which] + ". Junctions removed in three orders, each ranked once on the "
                "intact network; re-ranking after each removal usually fails networks faster, "
                "so the busiest-first curve is conservative.", x=0.05, y_title=0.93, y_sub=0.875, title_size=20,
                subtitle_size=12)
    footer_config(fig, f"Source: {SOURCE[which]}. Betweenness and efficiency estimated from "
                       f"sampled source junctions; random band = min–max over seeds.   "
                       f"Chart: Sahasrik Ragani", x=0.05, y=0.03, size=9)
    FIGS.mkdir(parents=True, exist_ok=True)
    out = FIGS / f"a1_fragmentation_{which}.png"
    fig.savefig(out, dpi=200)
    return out


def _selfish_txt(r: dict) -> str:
    b, l = r["clear_h_selfish_bulk"], r["clear_h_selfish_last"]
    rng = f"{b:.1f} h" if abs(b - l) < 0.05 else f"{b:.1f}–{l:.1f} h (bulk–last car)"
    return f"Everyone on their own best route: {rng}"


def b_hero(name: str = "butte") -> Path:
    """Hero: which communities have no way out that avoids Very High hazard,
    and the Paradise ridge's bottleneck in 2018."""
    import json
    import pickle
    import geopandas as gpd
    from viz.viz_theme import GRID, viridis_continuous
    MCRS = "EPSG:3310"
    it = INTERIM / name
    com = gpd.read_file(it / "communities.gpkg")
    cty = gpd.read_file(it / "county.gpkg")
    z = gpd.read_file(it / "fhsz.gpkg")
    rg = pickle.loads((it / "roads.pkl").read_bytes())
    edges = rg.edges.to_crs(MCRS)
    tab = pd.read_csv(TABLES / f"{name}_communities.csv", dtype={"cid": str})
    com["cid"] = com["cid"].astype(str)
    cut = pd.read_csv(TABLES / "retro_camp_ridge_min_cut.csv")
    camp = json.loads((TABLES / "retro_camp_ridge_summary.json").read_text(encoding="utf-8"))
    per = gpd.read_file(ROOT / "data" / "raw" / "calfire" / "fire_perimeters_firep25_1.geojson",
                        bbox=tuple(cty.to_crs(4326).total_bounds))
    per = per[(per.FIRE_NAME == "CAMP") & (per.YEAR_ == 2018) & (per.UNIT_ID == "BTU")].to_crs(MCRS)

    com = com.merge(tab[["cid", "cut_off_nohaz_vh", "capacity_vph", "capacity_nohaz_vh"]],
                    on="cid", how="inner")
    cls = np.where(com.cut_off_nohaz_vh, 0,
                   np.where(com.capacity_nohaz_vh < com.capacity_vph, 1, 2))
    col = {0: viridis_continuous(0.02), 1: viridis_continuous(0.45), 2: viridis_continuous(0.88)}
    lab = {0: "No way out that avoids Very High hazard",
           1: "Some exit capacity crosses Very High hazard",
           2: "Exits avoid Very High hazard"}
    major = edges.road_class.isin(["motorway", "trunk", "primary", "secondary"])

    setup_style()
    fig = plt.figure(figsize=(17, 10.0))
    axL = fig.add_axes([0.03, 0.17, 0.48, 0.65])
    axR = fig.add_axes([0.54, 0.10, 0.44, 0.72])
    for ax in (axL, axR):
        z[z.FHSZ == 3].plot(ax=ax, color=GRID, alpha=0.55, lw=0)
        edges[~major].plot(ax=ax, color="#E6E3DA", lw=0.2)
        edges[major].plot(ax=ax, color=MUTED, lw=0.6)
        ax.set_axis_off(); ax.set_aspect("equal")
    for k in (2, 1, 0):
        sub = com[cls == k]
        if len(sub):
            sub.plot(ax=axL, color=col[k], edgecolor="white", lw=0.4, zorder=3)
    cty.boundary.plot(ax=axL, color=TEXT, lw=0.8, linestyle="--")
    xmin, ymin, xmax, ymax = cty.total_bounds
    axL.set_xlim(xmin - 3000, xmax + 3000); axL.set_ylim(ymin - 3000, ymax + 3000)
    for k in (0, 1, 2):
        n = int((cls == k).sum()); pop = int(com.loc[cls == k, "POP20"].sum())
        axL.scatter([], [], s=160, marker="s", color=col[k],
                    label=f"{lab[k]}  ·  {n} communities, {pop:,} people")
    axL.legend(frameon=False, fontsize=10.5, loc="upper left", bbox_to_anchor=(0.0, -0.01))
    for nm, dx, dy in (("Chico", -40, 18), ("Oroville", 10, 20), ("Paradise", 22, -2),
                       ("Magalia", -58, 10), ("Berry Creek", 16, -14), ("Cohasset", -62, 8),
                       ("Forest Ranch", 14, 10)):
        g = com[com.name == nm]
        if len(g):
            c = g.geometry.iloc[0].representative_point()
            axL.annotate(nm, (c.x, c.y), xytext=(dx, dy), textcoords="offset points",
                         fontsize=10.5, fontfamily=FONT_BOLD, color=TEXT, zorder=6,
                         bbox=dict(facecolor="white", edgecolor="none", pad=0.8, alpha=0.85),
                         arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.6))
    axL.text(0, 1.03, "Butte County communities, by whether a safe exit exists",
             transform=axL.transAxes, fontsize=14, fontfamily=FONT_BOLD, color=TEXT)

    # right: the ridge in 2018 - whole exit roads, bottleneck points marked
    ridge = com[com.name.isin(camp["group"])]
    cut_e = edges.iloc[cut.eid.values]
    frame = pd.concat([ridge.geometry, cut_e.geometry])
    rx0, ry0, rx1, ry1 = frame.total_bounds
    pad = 3500
    axR.set_xlim(rx0 - pad, rx1 + pad); axR.set_ylim(ry0 - pad, ry1 + pad)
    per.plot(ax=axR, color=viridis_continuous(0.62), alpha=0.10, lw=0, zorder=2)
    per.boundary.plot(ax=axR, color=viridis_continuous(0.62), lw=1.0, zorder=2)
    ridge.boundary.plot(ax=axR, color=TEXT, lw=0.9, zorder=3)
    ecol = viridis_continuous(0.02)
    for _, r in cut.iterrows():
        nm = r["name"] if isinstance(r["name"], str) and r["name"] != "nan" else None
        road = edges[edges["name"].astype(str) == nm] if nm else edges[edges["ref"].astype(str) == r["ref"]]
        road.plot(ax=axR, color=ecol, lw=2.2, alpha=0.75, zorder=4)
    for (_, r), geom in zip(cut.iterrows(), cut_e.geometry.values):
        pt = geom.interpolate(0.5, normalized=True)
        axR.scatter([pt.x], [pt.y], s=90, color="white", edgecolor=ecol, lw=2.2, zorder=6)
        nm = r["name"] if isinstance(r["name"], str) and r["name"] != "nan" else r["ref"]
        axR.annotate(f"{nm}  {int(r.capacity_vph):,}", (pt.x, pt.y), xytext=(9, -3),
                     textcoords="offset points", fontsize=9.5, fontfamily=FONT_BOLD, color=TEXT,
                     zorder=7, bbox=dict(facecolor="white", edgecolor="none", pad=0.6, alpha=0.8))
    for nm in camp["group"]:
        g = ridge[ridge.name == nm].geometry.iloc[0].representative_point()
        axR.text(g.x, g.y, nm, fontsize=11.5, fontfamily=FONT_BOLD, color=MUTED, ha="center", zorder=5)
    axR.fill([], [], color=viridis_continuous(0.62), alpha=0.25, label="Camp Fire final perimeter (2018)")
    axR.plot([], [], color=ecol, lw=2.2, label="Exit roads")
    axR.scatter([], [], s=90, color="white", edgecolor=ecol, lw=2.2,
                label="Bottleneck section (minimum cut), veh/h")
    axR.legend(frameon=True, facecolor="white", edgecolor=GRID, fontsize=10, loc="lower left")
    axR.text(0, 1.03, "The Paradise ridge in 2018: the bottleneck on its way out",
             transform=axR.transAxes, fontsize=14, fontfamily=FONT_BOLD, color=TEXT)
    txt = (f"{camp['prefire_population']:,} people, {camp['prefire_vehicles']:,.0f} vehicles (pre-fire)\n"
           f"{camp['n_disjoint']} independent routes, {camp['mincut_capacity_vph']:,.0f} veh/h\n"
           f"Perfectly managed: {camp['sens_2lane_clear_h_managed']:.1f}–{camp['clear_h_managed']:.1f} h "
           f"to clear (low end: untagged roads 2 lanes each way)\n"
           + _selfish_txt(camp))
    axR.text(0.99, 0.99, txt, transform=axR.transAxes, ha="right", va="top", fontsize=10.5,
             fontfamily=FONT_SEMIBOLD, color=TEXT, linespacing=1.55,
             bbox=dict(facecolor="white", edgecolor=GRID, boxstyle="round,pad=0.6"), zorder=8)

    n0 = int((cls == 0).sum()); p0 = int(com.loc[cls == 0, "POP20"].sum())
    title_block(fig, f"{n0} Butte County communities have no way out that avoids "
                     f"Very High fire hazard",
                f"{p0:,} residents (2020). A safe exit = a freeway or major highway outside High "
                f"and Very High hazard zones, at least 5 km from the community. Grey shading: "
                f"Very High hazard.", x=0.03, y_title=0.94, y_sub=0.90, title_size=22,
                subtitle_size=12)
    footer_config(fig, "Sources: © OpenStreetMap contributors (ODbL), Sep 2026 · CAL FIRE FHSZ SRA 2024 + "
                       "LRA 2025 (recommended) · CAL FIRE FRAP perimeters firep25_1 · US Census 2020 "
                       "blocks, TIGER 2024 places, ACS 2014–18 (pre-fire vehicles).\nCapacities imputed "
                       "from HCM values where OSM has no lanes tag (91% of Butte arcs). Clearance "
                       "assumes every vehicle leaves.   Chart: Sahasrik Ragani",
                  x=0.03, y=0.018, size=9)
    out = FIGS / f"b_hero_{name}.png"
    fig.savefig(out, dpi=200)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "a1":
        print(a1(sys.argv[2]))
    elif sys.argv[1] == "hero":
        print(b_hero(sys.argv[2]))
