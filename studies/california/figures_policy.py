"""Policy-layer figures (DESIGN §10). House style from viz/viz_theme.py.

    python -m studies.california.figures_policy camp_timeline
    python -m studies.california.figures_policy fixes
    python -m studies.california.figures_policy ladder
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from viz.viz_theme import (FONT_BOLD, FONT_SEMIBOLD, GRID, MUTED, TEXT,  # noqa: E402
                           footer_config, setup_style, style_axes, title_block,
                           viridis_categorical, viridis_continuous)

TABLES, FIGS = ROOT / "outputs" / "tables", ROOT / "outputs" / "figures"
BYLINE = "Chart: Sahasrik Ragani"


def _clock(h: float) -> str:
    m = int(round(h * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def camp_timeline() -> Path:
    """Time available (NIST TN 2135) vs time needed (this study), Camp Fire."""
    camp = json.loads((TABLES / "retro_camp_ridge_summary.json").read_text(encoding="utf-8"))
    pol = pd.read_csv(TABLES / "policy_butte.csv").set_index("unit").loc["CAMP 2018 group"]
    t0 = 6.5                                                   # 06:30 ignition
    bars = [("Everyone on their own best route", camp["clear_h_selfish_last"], None),
            ("Perfectly managed", camp["clear_h_managed"], camp["sens_2lane_clear_h_managed"]),
            ("Managed + contraflow on the binding roads", pol.I2_contraflow_h, None),
            (f"Managed + {pol.I3_lane_km:,.0f} lane-km of widening", pol.I3_widen_h, None)]
    events = [(6.5, "06:30  Ignition near Pulga"),
              (7 + 25 / 60, "07:25  Structures burning in Concow"),
              (7 + 44 / 60, "07:44  First spot fires in Paradise"),
              (8.5, "08:30  Main front reaches Pentz Rd"),
              (10.0, "10:00  Civilians trapped in traffic on Pentz, Bille, Pearson")]
    setup_style()
    fig, ax = plt.subplots(figsize=(15, 7.6))
    fig.subplots_adjust(left=0.27, right=0.97, top=0.62, bottom=0.13)
    style_axes(ax, grid_axis="x")
    cols = viridis_categorical(4, low=0.05, high=0.80)
    for i, ((lab, h, lo), c) in enumerate(zip(bars, cols)):
        y = len(bars) - 1 - i
        ax.barh(y, h, left=t0, height=0.52, color=c, zorder=3)
        note = f"done {_clock(t0 + h)}"
        if lo is not None:
            ax.barh(y, h - lo, left=t0 + lo, height=0.52, color="white", alpha=0.5,
                    hatch="///", edgecolor=c, lw=0, zorder=4)
            note += f"  (or {_clock(t0 + lo)} if untagged roads are 2 lanes each way)"
        ax.text(t0 + h + 0.08, y, note, va="center", fontsize=10.5,
                fontfamily=FONT_SEMIBOLD, color=TEXT, zorder=5)
        ax.text(t0 - 0.12, y, lab, va="center", ha="right", fontsize=11.5,
                fontfamily=FONT_BOLD, color=TEXT)
    ytop = len(bars) - 0.4
    for x, _ in events:
        ax.axvline(x, color=viridis_continuous(0.9) if x > 6.5 else MUTED, lw=1.4,
                   ls="--" if x > 6.5 else "-", zorder=2)
    for k, (x, lab) in enumerate(events):
        ax.annotate(lab, (x, ytop), xytext=(4, 8 + 17 * (len(events) - 1 - k)),
                    textcoords="offset points", ha="left", fontsize=10,
                    fontfamily=FONT_SEMIBOLD, color=TEXT, annotation_clip=False)
    ax.set_xlim(6, 16.3)
    ax.set_ylim(-0.6, len(bars) - 0.4)
    ax.set_yticks([])
    ax.set_xticks(range(6, 17))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(6, 17)])
    ax.set_xlabel("8 November 2018", fontsize=11, fontfamily=FONT_SEMIBOLD, color=TEXT)
    title_block(fig, "Ordered at ignition, a perfect evacuation of the Paradise ridge would still "
                     "have been on the road when the fire arrived",
                f"{camp['prefire_vehicles']:,.0f} pre-fire vehicles (Paradise, Magalia, Concow). Every "
                f"bar assumes the order came at 06:30; any delay moves it right. Dashed lines: the "
                f"fire, as reconstructed by NIST.", x=0.03, y_title=0.935, y_sub=0.885,
                title_size=18, subtitle_size=11.5)
    footer_config(fig, "Sources: fire timeline, NIST TN 2135 (Maranghides et al. 2021). Clearance: this "
                       "study; OSM roads (Sep 2026), ACS 2014–18 vehicles, HCM capacities; static bound, "
                       f"every vehicle leaves.   {BYLINE}", x=0.03, y=0.025, size=9)
    out = FIGS / "c_camp_timeline.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fixes() -> Path:
    """What each fix buys, for the three fire groups."""
    pb_ = pd.read_csv(TABLES / "policy_butte.csv").set_index("unit")
    pl_ = pd.read_csv(TABLES / "policy_la_foothills.csv").set_index("unit")
    groups = [("Camp 2018\nParadise ridge", pb_.loc["CAMP 2018 group"]),
              ("Palisades 2025", pl_.loc["PALISADES 2025 group"]),
              ("Eaton 2025\nAltadena, Sierra Madre", pl_.loc["EATON 2025 group"])]
    steps = [("I1_selfish_last_h", "Self-routed (last car out)"), ("clear_h_managed", "Managed"),
             ("I2_contraflow_h", "+ contraflow"), ("I3_widen_h", "+ widening")]
    cols = viridis_categorical(4, low=0.05, high=0.85)
    setup_style()
    fig, ax = plt.subplots(figsize=(15, 7.0))
    fig.subplots_adjust(left=0.17, right=0.97, top=0.70, bottom=0.19)
    style_axes(ax, grid_axis="x")
    def fmt(v):
        return f"{v:.2f} h" if v < 1 else f"{v:.1f} h"

    offs = [0.16, 0.05, -0.06, -0.17]      # one row per step, so equal values stay visible
    for gi, (lab, r) in enumerate(groups):
        y = len(groups) - 1 - gi
        xs = [r[k] for k, _ in steps]
        ax.plot([min(xs), max(xs)], [y, y], color=GRID, lw=6, solid_capstyle="round", zorder=1)
        for c, x_, dy in zip(cols, xs, offs):
            ax.scatter([x_], [y + dy], s=150, color=c, edgecolor="white", lw=1.3, zorder=4)
        ax.text(-0.35, y, lab, ha="right", va="center", fontsize=12, fontfamily=FONT_BOLD,
                color=TEXT)
        ax.annotate(f"self-routed {fmt(r['I1_selfish_last_h'])}", (r["I1_selfish_last_h"], y + offs[0]),
                    xytext=(0, 10), textcoords="offset points", ha="right", fontsize=10,
                    fontfamily=FONT_SEMIBOLD, color=TEXT)
        ax.annotate(f"managed {fmt(r['clear_h_managed'])}", (r["clear_h_managed"], y + offs[1]),
                    xytext=(12, 0), textcoords="offset points", ha="left", va="center",
                    fontsize=10, fontfamily=FONT_SEMIBOLD, color=TEXT)
        if r["I3_lane_km"] > 0:
            ax.annotate(f"{fmt(r['I3_widen_h'])} after {r['I3_lane_km']:,.0f} lane-km",
                        (r["I3_widen_h"], y + offs[3]), xytext=(0, -16), textcoords="offset points",
                        ha="center", fontsize=9.5, fontfamily=FONT_SEMIBOLD, color=MUTED)
    for h, lab, dy in ((1, "1 h: first spot fires in Paradise", 0.30),
                       (2, "2 h: main front at Pentz Rd", 0.10)):
        ax.axvline(h, color=viridis_continuous(0.9), lw=1.4, ls="--", zorder=0)
        ax.text(h + 0.08, len(groups) - 1 + dy + 0.18, lab, fontsize=9.5, fontfamily=FONT_SEMIBOLD,
                color=MUTED, va="bottom")
    for (_, s), c in zip(steps, cols):
        ax.scatter([], [], s=140, color=c, label=s)
    ax.legend(frameon=False, ncol=4, fontsize=11, loc="upper left", bbox_to_anchor=(0, -0.1))
    ax.set_xlim(-0.2, 14.5)
    ax.set_ylim(-0.6, len(groups) - 0.25)
    ax.set_yticks([])
    ax.set_xlabel("Hours to clear every vehicle", fontsize=11.5, fontfamily=FONT_SEMIBOLD,
                  color=TEXT)
    title_block(fig, "Coordinating traffic saved 6 to 13 hours; 150–175 lane-km of new road saved little more than one",
                "Clearance for each fire's evacuation group, one fix added at a time. Widening adds "
                "a lane to whole named roads, greedily, up to five.\nContraflow is applied only where "
                "it helps and cannot reach divided roads such as Palisades Drive.",
                x=0.03, y_title=0.935, y_sub=0.845, title_size=20, subtitle_size=11.5)
    footer_config(fig, "Source: this study. OSM roads (Sep 2026), CAL FIRE FHSZ and FRAP perimeters, ACS "
                       "vehicles (2014–18 for Camp, 2020–24 for LA), HCM capacities; static managed bound "
                       f"vs CLM-style self-routing.   {BYLINE}", x=0.03, y=0.025, size=9)
    out = FIGS / "c_fixes.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def ladder() -> Path:
    """Residents by highest rung of the safety ladder met, per study area."""
    rungs = {0: "Fails SB 99 (fewer than 2 routes)", 1: "2+ routes, over 2 h to clear",
             2: "Clears in 1–2 h", 3: "Within 1 h, but only through Very High",
             4: "Within 1 h avoiding Very High", 5: "Within 1 h avoiding High and Very High"}
    areas = [("Butte County", "butte"), ("LA fire clusters", "la_foothills")]
    setup_style()
    fig, ax = plt.subplots(figsize=(15, 5.2))
    fig.subplots_adjust(left=0.17, right=0.97, top=0.76, bottom=0.30)
    style_axes(ax, grid_axis=None)
    for ai, (lab, a) in enumerate(areas):
        p = pd.read_csv(TABLES / f"policy_{a}.csv")
        r = pd.read_csv(TABLES / f"{a}_communities.csv")[["community", "population"]]
        p = p[p.kind == "community"].merge(r, left_on="unit", right_on="community")
        g = p.groupby("ladder_rung").agg(n=("unit", "size"), pop=("population", "sum"))
        tot = g["pop"].sum()
        y = len(areas) - 1 - ai
        left = 0.0
        for k in range(6):
            if k not in g.index:
                continue
            w = g.loc[k, "pop"] / tot
            ax.barh(y, w, left=left, height=0.58, color=viridis_continuous(0.04 + 0.18 * k),
                    edgecolor="white", lw=1.5)
            if w > 0.07:
                n = int(g.loc[k, "n"])
                who = p.loc[p.ladder_rung == k, "unit"].iloc[0] if n == 1 else f"{n} places"
                ax.text(left + w / 2, y, f"{w:.0%}\n{who}",
                        ha="center", va="center", fontsize=10, fontfamily=FONT_BOLD,
                        color="white" if k < 3 else TEXT)
            left += w
        ax.text(-0.01, y, f"{lab}\n{int(tot):,} residents", ha="right", va="center",
                fontsize=11.5, fontfamily=FONT_BOLD, color=TEXT)
    for k in range(6):
        ax.barh([0], [0], color=viridis_continuous(0.04 + 0.18 * k), label=f"{k}  {rungs[k]}")
    ax.legend(frameon=False, ncol=3, fontsize=10, loc="upper left", bbox_to_anchor=(0, -0.05))
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    title_block(fig, "Fewer than three in ten residents can get out within an hour without "
                     "crossing Very High fire hazard",
                "Residents (2020) by the highest rung of the safety ladder their community meets. "
                "Rungs build on each other; clearance is the managed bound, every vehicle leaving.",
                x=0.03, y_title=0.925, y_sub=0.855, title_size=20, subtitle_size=11.5)
    footer_config(fig, "Source: this study. Rung 1 and above meet SB 99 (Gov. Code §65302(g)(5)); 1 h and 2 h targets "
                       "from the Camp Fire timeline (NIST TN 2135). US Census 2020, OSM, CAL FIRE FHSZ.   "
                       f"{BYLINE}", x=0.03, y=0.03, size=9)
    out = FIGS / "c_ladder.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def la_hero() -> Path:
    """LA companion to the Butte hero: the two 2025 fire clusters side by side."""
    import pickle
    import geopandas as gpd
    import matplotlib.patheffects as pe
    mcrs = "EPSG:3310"
    it = ROOT / "data" / "interim" / "la_foothills"
    com = gpd.read_file(it / "communities.gpkg").to_crs(mcrs)
    z = gpd.read_file(it / "fhsz.gpkg").to_crs(mcrs)
    rg = pickle.loads((it / "roads.pkl").read_bytes())
    edges = rg.edges.to_crs(mcrs)
    tab = pd.read_csv(TABLES / "la_foothills_communities.csv", dtype={"cid": str})
    com["cid"] = com["cid"].astype(str)
    com = com.merge(tab[["cid", "cut_off_nohaz_vh", "capacity_vph", "capacity_nohaz_vh"]],
                    on="cid", how="left")
    cls = pd.Series(2, index=com.index)
    cls[com.capacity_nohaz_vh < com.capacity_vph] = 1
    cls[com.cut_off_nohaz_vh.fillna(False).astype(bool)] = 0
    col = {0: viridis_continuous(0.02), 1: viridis_continuous(0.45), 2: viridis_continuous(0.88)}
    lab = {0: "No way out that avoids Very High hazard",
           1: "Some exit capacity crosses Very High hazard",
           2: "Exits avoid Very High hazard"}
    per_all = gpd.read_file(ROOT / "data" / "raw" / "calfire" / "fire_perimeters_firep25_1.geojson",
                            bbox=tuple(com.to_crs(4326).total_bounds))
    major = edges.road_class.isin(["motorway", "trunk", "primary", "secondary"])
    halo = [pe.withStroke(linewidth=3, foreground="white")]

    red = "#C8435A"
    label_pos = {   # label -> offset (points) from the community's representative point
        "Pacific Palisades": (40, -46), "Palisades Highlands": (-30, 58),
        "Mandeville Canyon": (60, 40), "Malibu": (0, -30), "Santa Monica Mountains": (-40, 40),
        "Brentwood": (40, 10), "Tarzana": (-10, 30), "Encino": (30, 30),
        "Altadena": (-70, 50), "Pasadena": (-80, -40), "Sierra Madre": (90, 60),
        "Kinneloa Mesa": (-30, 80), "Arcadia": (40, -40), "Monrovia": (50, -10)}
    setup_style()
    fig = plt.figure(figsize=(17, 9.2))
    panels = [("PALISADES", "palisades", "LDF", [0.03, 0.14, 0.46, 0.60],
               "Palisades 2025: one road binds"),
              ("EATON", "eaton", "LAC", [0.52, 0.14, 0.45, 0.60],
               "Eaton 2025: the roads exist; the traffic would not flow")]
    used = set()
    for fire, tag, unit, box, head in panels:
        ax = fig.add_axes(box)
        r = json.loads((TABLES / f"retro_{tag}_summary.json").read_text(encoding="utf-8"))
        bind = pd.read_csv(TABLES / f"retro_{tag}_binding.csv")
        sub = com[(com.cluster == fire) & ~com.name.str.contains("National Forest")]
        per = per_all[(per_all.FIRE_NAME == fire) & (per_all.YEAR_ == 2025) &
                      (per_all.UNIT_ID == unit)].to_crs(mcrs)
        x0, y0, x1, y1 = sub.total_bounds
        pad = 2000
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
        z[z.FHSZ == 3].plot(ax=ax, color=GRID, alpha=0.55, lw=0)
        edges[~major].plot(ax=ax, color="#E6E3DA", lw=0.2)
        edges[major].plot(ax=ax, color=MUTED, lw=0.6)
        for k in (2, 1, 0):
            s_ = sub[cls[sub.index] == k]
            if len(s_):
                s_.plot(ax=ax, color=col[k], alpha=0.8, edgecolor="white", lw=0.6, zorder=3)
                used.add(k)
        per.boundary.plot(ax=ax, color=TEXT, lw=1.3, linestyle="--", zorder=4)
        for _, b in bind.iterrows():
            road = edges[(edges["name"].astype(str) == str(b["name"]))]
            road = road[road.intersects(sub.union_all().buffer(3000))]
            road.plot(ax=ax, color=red, lw=3.2, zorder=6)
            gm = edges.geometry.values[int(b.eid)]
            p = gm.interpolate(0.5, normalized=True)
            ax.scatter([p.x], [p.y], s=160, facecolor="white", edgecolor=red, lw=2.6, zorder=7)
            ax.annotate(f"{b['name']}: {int(b.capacity_vph):,} veh/h\nthe section that binds",
                        (p.x, p.y), xytext=(-150, -58) if tag == "palisades" else (40, -52),
                        textcoords="offset points", fontsize=10.5, fontfamily=FONT_BOLD,
                        color=red, zorder=9, path_effects=halo,
                        arrowprops=dict(arrowstyle="-", color=red, lw=1.2))
        for _, c in sub.iterrows():
            if c["name"] not in label_pos:
                continue
            pt = c.geometry.representative_point()
            ax.annotate(c["name"], (pt.x, pt.y), xytext=label_pos[c["name"]],
                        textcoords="offset points", fontsize=10, fontfamily=FONT_SEMIBOLD,
                        color=TEXT, ha="center", zorder=8, path_effects=halo,
                        arrowprops=dict(arrowstyle="-", color=TEXT, lw=0.6))
        ax.set_axis_off(); ax.set_aspect("equal")
        fig.text(box[0], 0.81, head, fontsize=14, fontfamily=FONT_BOLD, color=TEXT)
        fig.text(box[0], 0.782,
                 f"{r['prefire_vehicles']:,.0f} vehicles in the evacuation group · managed "
                 f"{r['clear_h_managed']:.1f} h · self-routed {r['clear_h_selfish_last']:.1f} h "
                 f"to the last car", fontsize=10.5, fontfamily=FONT_SEMIBOLD, color=MUTED)
    for k in sorted(used):
        fig.axes[0].scatter([], [], s=150, marker="s", color=col[k], label=lab[k])
    fig.axes[0].plot([], [], color=red, lw=3.2, label="Binding road of the managed evacuation")
    fig.axes[0].plot([], [], color=TEXT, lw=1.3, ls="--", label="2025 fire perimeter")
    fig.legend(frameon=False, ncol=4, fontsize=10.5, loc="lower left", bbox_to_anchor=(0.03, 0.06))
    title_block(fig, "Two Los Angeles fires, two different failures",
                "In the Palisades a single road set the pace for 43,000 vehicles. Around Altadena "
                "the capacity was there, but drivers left to themselves would have jammed the local "
                "streets for half a day.\nGrey shading: Very High hazard. Angeles National Forest "
                "(near-unpopulated) not shaded.",
                x=0.03, y_title=0.945, y_sub=0.875, title_size=22, subtitle_size=12)
    footer_config(fig, "Sources: © OpenStreetMap contributors (ODbL), Geofabrik SoCal extract Sep 2026 · "
                       "CAL FIRE FHSZ SRA 2024 + LRA 2025 (recommended), FRAP perimeters firep25_1 · US Census "
                       "2020, ACS 2020–24 · LA County CSAs. Static bounds; every vehicle leaves.   "
                       f"{BYLINE}", x=0.03, y=0.02, size=9)
    out = FIGS / "b_hero_la.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(globals()[sys.argv[1]]())
