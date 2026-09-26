"""Interventions on a road graph, each returning a modified copy.

Used to ask "what does this fix buy?" by recomputing the managed evacuation
bound (hazardnet.clm.managed_throughput) before and after:

    contraflow(g, arcs)      outbound arcs also take their reverse arc's lanes
    widen(g, arc, add_vph)   one more lane on an arc
    managed_flow(...)        per-arc flow of the managed solution, to measure
                             how much of a candidate road an evacuation uses

Nothing here knows about fire or California; capacities to add are passed in.
"""
from __future__ import annotations

import igraph as ig
import numpy as np

from .clm import _with_sink


def reverse_arc(g: ig.Graph, e: int) -> int | None:
    u, v = g.es[e].tuple
    r = g.get_eid(v, u, directed=True, error=False)
    return None if r < 0 else r


def contraflow(g: ig.Graph, arcs, *, capacity: str = "capacity_vph") -> tuple[ig.Graph, float]:
    """Reverse the opposing lanes of each arc: the arc gains its reverse arc's
    capacity and the reverse arc drops to zero. Arcs with no reverse (already
    one-way) are unchanged. Returns (new graph, metres converted)."""
    h = g.copy()
    cap = np.asarray(h.es[capacity], dtype=float)
    length = np.asarray(h.es["length_m"], dtype=float) if "length_m" in h.es.attributes() \
        else np.zeros(h.ecount())
    done = 0.0
    for e in arcs:
        r = reverse_arc(h, e)
        if r is None or cap[r] == 0:
            continue
        cap[e] += cap[r]
        cap[r] = 0.0
        done += length[e]
    h.es[capacity] = cap.tolist()
    return h, done


def widen(g: ig.Graph, arc: int, add_vph: float, *, capacity: str = "capacity_vph") -> ig.Graph:
    h = g.copy()
    cap = np.asarray(h.es[capacity], dtype=float)
    cap[arc] += add_vph
    h.es[capacity] = cap.tolist()
    return h


def managed_flow(g: ig.Graph, weights: dict, targets, D: float, *,
                 capacity: str = "capacity_vph") -> np.ndarray:
    """Per-arc flow (veh/h) of one feasible managed solution at demand D, with
    origin i sending D * w_i. Max-flow solutions are not unique, so read the
    result as 'one plan that works', not 'the plan'."""
    d, sink, m = _with_sink(g, targets)
    cap = np.concatenate([np.asarray(d.es[capacity][:m], dtype=float),
                          np.full(d.ecount() - m, 1e12)])
    orig = np.fromiter(weights.keys(), dtype=int)
    w = np.fromiter(weights.values(), dtype=float)
    w = w / w.sum()
    d.add_vertices(1)
    src = d.vcount() - 1
    d.add_edges([(src, int(o)) for o in orig])
    f = d.maxflow(src, sink, capacity=np.concatenate([cap, D * w]).tolist())
    return np.asarray(f.flow[:m], dtype=float)
