"""Community -> safe-destination accessibility.

For each community (a set of vertices) and one shared set of target vertices:

    n_disjoint     edge-disjoint directed paths out (unit-capacity max-flow)
    capacity_vph   capacity-weighted max-flow = capacity of the minimum cut
    tt_min         shortest free-flow time from any community vertex to a target (s)
    efficiency     mean over community vertices of 1/(time to nearest target),
                   Latora-Marchiori style: an unreachable vertex contributes 0
    exposed_share  share of the min-cut capacity on hazard-exposed edges

Communities and targets are contracted into a super-source and a super-sink.
The graph is used as DIRECTED: on OSM, two-way roads are two arcs and one-way
roads one, so a divided highway's two carriageways do not double-count exits -
only the outbound one can carry outbound flow. An undirected graph is treated
as two arcs per edge.

The min cut is not unique; `exposed_share` reports the cut igraph returns, and
callers should treat it as indicative.
"""
from __future__ import annotations

import igraph as ig
import numpy as np
import pandas as pd

BIG = 1e12   # "infinite" capacity for super-source/sink arcs


def _directed(g: ig.Graph) -> ig.Graph:
    return g.copy() if g.is_directed() else g.as_directed(mode="mutual")


def time_to_targets(g: ig.Graph, targets, time: str = "travel_s") -> np.ndarray:
    """Seconds from every vertex to its nearest target (inf if none reachable),
    by one Dijkstra from a super-sink on the reversed graph."""
    d = _directed(g)
    n = d.vcount()
    d.add_vertices(1)
    sink = n
    # arcs target -> sink; searching from the sink with mode="in" walks every
    # arc backwards, i.e. gives each vertex's forward time TO the sink
    d.add_edges([(int(t), sink) for t in targets])
    w = np.asarray(d.es[time] if time in d.es.attributes() else [1.0] * d.ecount(),
                   dtype=float)
    w[-len(targets):] = 0.0
    out = d.distances(source=[sink], weights=w.tolist(), mode="in")[0]
    return np.asarray(out[:n], dtype=float)


def _maxflow(d: ig.Graph, members, targets, cap: np.ndarray):
    n = d.vcount()
    h = d.copy()
    h.add_vertices(2)
    s, t = n, n + 1
    h.add_edges([(s, int(v)) for v in members] + [(int(v), t) for v in targets])
    c = np.concatenate([cap, np.full(len(members) + len(targets), BIG)])
    return h.maxflow(s, t, capacity=c.tolist()), h.ecount() - len(members) - len(targets)


def accessibility(g: ig.Graph, communities: dict, targets, *,
                  capacity: str = "capacity_vph", time: str = "travel_s",
                  hazard: str | None = None, threshold: float | None = None,
                  population: dict | None = None) -> pd.DataFrame:
    d = _directed(g)
    targets = np.unique(np.asarray(list(targets), dtype=int))
    t_near = time_to_targets(d, targets, time=time)
    cap = np.asarray(d.es[capacity], dtype=float) if capacity in d.es.attributes() \
        else np.ones(d.ecount())
    unit = np.ones(d.ecount())
    haz = (np.asarray(d.es[hazard], dtype=float) >= threshold) \
        if hazard and hazard in d.es.attributes() else None

    rows = []
    for name, members in communities.items():
        members = np.setdiff1d(np.asarray(list(members), dtype=int), targets)
        if len(members) == 0:
            rows.append({"community": name, "n_vertices": 0}); continue
        f_unit, _ = _maxflow(d, members, targets, unit)
        f_cap, m_real = _maxflow(d, members, targets, cap)
        cut = [e for e in f_cap.cut if e < m_real]      # drop super arcs
        tm = t_near[members]
        row = {
            "community": name,
            "n_vertices": int(len(members)),
            "n_disjoint": int(round(f_unit.value)),
            "capacity_vph": float(f_cap.value) if f_cap.value < BIG / 2 else np.inf,
            "tt_min": float(tm.min()),
            "efficiency": float(np.where(np.isfinite(tm) & (tm > 0), 1.0 / tm, 0.0).mean()),
            "cut_off": bool(not np.isfinite(tm).any()),
        }
        if haz is not None and row["capacity_vph"] > 0 and np.isfinite(row["capacity_vph"]):
            row["exposed_share"] = float(cap[cut][haz[cut]].sum() / cap[cut].sum()) \
                if len(cut) else 0.0
        if population is not None:
            p = population.get(name, np.nan)
            row["population"] = p
            row["people_per_capacity"] = p / row["capacity_vph"] \
                if row["capacity_vph"] > 0 else np.inf
        rows.append(row)
    return pd.DataFrame(rows)
