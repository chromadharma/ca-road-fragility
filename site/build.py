"""Build the static site from site/src/content.html.

    python site/build.py

Every number on the page is filled from the result tables here, so the site
cannot drift from the analysis. Writes:
    site/index.html      full document, for GitHub Pages
    site/figures/*.png   figures, downscaled for the web
    site/artifact.html   the same page without the document wrapper (preview link)
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))  # unpickling the road graph needs hazardnet
SITE, TABLES, FIGS = ROOT / "site", ROOT / "outputs" / "tables", ROOT / "outputs" / "figures"
T0 = 6.5                                   # 06:30 ignition, Camp Fire
AXIS = (6.0, 16.0)                         # strip runs 06:00 to 16:00
FIGURES = ["a1_fragmentation_snap", "b_hero_butte", "b_hero_la", "c_ladder", "c_fixes",
           "c_camp_timeline"]


def clock(h: float) -> str:
    m = int(round(h * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def x(h: float) -> str:
    return f"{(h - AXIS[0]) / (AXIS[1] - AXIS[0]) * 100:.2f}"


def w(hours: float) -> str:
    return f"{hours / (AXIS[1] - AXIS[0]) * 100:.2f}"


def tokens() -> dict:
    camp = json.loads((TABLES / "retro_camp_ridge_summary.json").read_text(encoding="utf-8"))
    pal = json.loads((TABLES / "retro_palisades_summary.json").read_text(encoding="utf-8"))
    eat = json.loads((TABLES / "retro_eaton_summary.json").read_text(encoding="utf-8"))
    pb = pd.read_csv(TABLES / "policy_butte.csv").set_index("unit")
    camp_pol = pb.loc["CAMP 2018 group"]
    bt = pd.read_csv(TABLES / "butte_communities.csv")
    la = pd.read_csv(TABLES / "la_foothills_communities.csv")
    la = la[~la.community.str.contains("National Forest")]
    a = pd.read_csv(TABLES / "part_a_snap_curves.csv")
    node = a[a.element == "node"]
    rnd = node[node.order.str.startswith("random")].groupby("fraction").S1.mean()
    busy = node[node.order == "betweenness"].set_index("fraction").S1
    load = np.load(ROOT / "data" / "interim" / "part_a_snap_load.npz")["betweenness"]
    top1 = np.sort(load)[::-1][: len(load) // 100].sum() / load.sum()
    butte_rg = pickle.loads((ROOT / "data" / "interim" / "butte" / "roads.pkl").read_bytes())

    def ratio(df):
        r = (df.clear_h_selfish_last / df.clear_h_managed).replace([np.inf, -np.inf], np.nan)
        return f"{r.dropna().median():.1f}"

    man, man_lo, slf = camp["clear_h_managed"], camp["sens_2lane_clear_h_managed"], \
        camp["clear_h_selfish_last"]
    cut_b = bt[bt.cut_off_nohaz_vh == True]                      # noqa: E712
    pal_c = la[la.community.isin(pal["group"]) | la.community.isin(
        ["Brentwood", "Encino", "Tarzana"])]
    ticks = "".join(f'<div class="tick" style="left:{x(h)}%"><span>{h:02d}:00</span></div>'
                    for h in range(int(AXIS[0]), int(AXIS[1]) + 1))
    t = {
        "camp_veh": f"{camp['prefire_vehicles']:,.0f}",
        "camp_man": f"{man:.1f}", "camp_man_lo": f"{man_lo:.1f}", "camp_self": f"{slf:.1f}",
        "camp_man_clock": clock(T0 + man), "camp_man_lo_clock": clock(T0 + man_lo),
        "camp_self_clock": clock(T0 + slf),
        "camp_lanekm": f"{camp_pol.I3_lane_km:,.0f}", "camp_widen": f"{camp_pol.I3_widen_h:.1f}",
        "x_0630": x(6.5), "x_0725": x(7 + 25 / 60), "x_0744": x(7 + 44 / 60), "x_0830": x(8.5),
        "x_1000": x(10.0), "x_man_lo": x(T0 + man_lo),
        "w_self": w(slf), "w_man_lo": w(man_lo), "w_man_band": w(man - man_lo),
        "strip_ticks": ticks,
        "a_busy_cut": f"{1 - busy.loc[0.01]:.0%}", "a_rand_cut": f"{1 - rnd.loc[0.01]:.0%}",
        "a_rand20": f"{rnd.loc[0.2]:.0%}", "a_load_top1": f"{top1:.0%}",
        "gap_butte": ratio(bt), "gap_la": ratio(la),
        "butte_n_cut": str(len(cut_b)), "butte_pop_cut": f"{int(cut_b.population.sum()):,}",
        "la_pal_pop": f"{int(la[la.community.isin(pal['group']) & (la.cut_off_nohaz_vh == True)].population.sum()):,}",  # noqa: E712,E501
        "pal_man": f"{pal['clear_h_managed']:.1f}", "pal_self": f"{pal['clear_h_selfish_last']:.1f}",
        "eaton_man": f"{eat['clear_h_managed']:.2f}", "eaton_self": f"{eat['clear_h_selfish_last']:.1f}",
        "butte_lanes_missing": f"{butte_rg.meta['share_lanes_imputed']:.0%}",
    }
    del pal_c
    return t


def build() -> None:
    src = (SITE / "src" / "content.html").read_text(encoding="utf-8")
    t = tokens()
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: t[m.group(1)], src)
    left = re.findall(r"\{\{\w+\}\}", out)
    if left:
        raise SystemExit(f"unfilled tokens: {left}")
    (SITE / "artifact.html").write_text(out, encoding="utf-8")
    head, body = out.split('<div class="page">', 1)
    doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           '<meta name="description" content="Which California communities have too little road '
           'capacity to evacuate, how much of it runs through fire hazard, and what would help.">\n'
           '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n'
           f'{head}</head>\n<body>\n<div class="page">{body}</body>\n</html>\n')
    (SITE / "index.html").write_text(doc, encoding="utf-8")
    (SITE / "figures").mkdir(exist_ok=True)
    for f in FIGURES:
        im = Image.open(FIGS / f"{f}.png").convert("RGB")
        if im.width > 2000:
            im = im.resize((2000, round(im.height * 2000 / im.width)), Image.LANCZOS)
        im.save(SITE / "figures" / f"{f}.png", optimize=True)
    print("built:", {k: v for k, v in t.items() if not k.startswith(("x_", "w_", "strip"))})


if __name__ == "__main__":
    build()
