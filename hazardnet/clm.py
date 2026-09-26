"""CLM-style congestion on an evacuation: how much of the max-flow capacity
survives when every driver takes their own best route?

Adapted from Crucitti, Latora & Marchiori (2004, Phys. Rev. E 69, 045104):
  - load  = evacuation flow on each arc (not all-pairs betweenness): demand D
            (veh/h) is split over origin vertices by weight and sent along
            each origin's current most-efficient (fastest) path to the targets;
  - capacity = the arc's physical capacity (not alpha x initial load);
  - update = CLM's rule: an overloaded arc's efficiency falls to e0 * C/L,
            i.e. its travel time rises to t0 * L/C; traffic then re-routes.
Iterated until the path set stops changing (or max_iter). Two readings of the
settled state, because a static model cannot say which one an evacuation
follows:
  - strict   D_strict = largest D whose settled state overloads NO arc. With
             routes fixed, the most-throttled origin drains slowest, so
             vehicles / D_strict is the time until the LAST car is out.
  - rationed each overloaded arc serves its capacity, shared pro rata; an
             origin's flow is throttled by the worst arc on its path. The max
             delivered flow over D gives vehicles / delivered = the time for
             the BULK of traffic.
Both are compared with managed_throughput (same origins, same split, any
routing). Found 2026-09-25: with the strict reading alone, one saturated
side street (Eaton: W Howard St, 950 veh/h, 29% of demand) sets the whole
answer.

Static loads, not time-varying departures: a bound on uncoordinated routing,
not a simulation of an evacuation.
"""
from __future__ import annotations

import igraph as ig
import numpy as np


def _with_sink(g: ig.Graph, targets):
    d = g.copy() if g.is_directed() else g.as_directed(mode="mutual")
    n, m = d.vcount(), d.ecount()
    d.add_vertices(1)
    d.add_edges([(int(t), n) for t in targets])
    return d, n, m


def settle(g: ig.Graph, weights: dict, targets, D: float, *, capacity="capacity_vph",
           time="travel_s", max_iter: int = 60) -> dict:
    """Run the CLM-style iteration at demand D.

    If the path set repeats an earlier state, re-routing is oscillating. The
    result is then taken over the WHOLE cycle, so it does not depend on where
    the iteration happens to stop: delivered = mean over the cycle's states,
    ratio = max over them (strict: carried only if no state overloads)."""
    d, sink, m = _with_sink(g, targets)
    t0 = np.asarray(d.es[time][:m], dtype=float)
    cap = np.asarray(d.es[capacity][:m], dtype=float)
    orig = np.fromiter(weights.keys(), dtype=int)
    w = np.fromiter(weights.values(), dtype=float)
    w = w / w.sum()
    t = t0.copy()
    history = []                     # (key, ratio, delivered) per iteration
    index = {}
    converged, cycle = False, None
    for it in range(1, max_iter + 1):
        wt = np.concatenate([t, np.zeros(d.ecount() - m)]).tolist()
        paths = d.get_shortest_paths(sink, to=orig.tolist(), weights=wt, mode="in",
                                     output="epath")
        real = [[e for e in p if e < m] for p in paths]
        load = np.zeros(m)
        for r, wi in zip(real, w):
            load[r] += D * wi
        serve = np.minimum(1.0, cap / np.maximum(load, 1e-9))
        throttle = np.array([serve[r].min() if r else 0.0 for r in real])
        ratio = float(np.max(load / np.maximum(cap, 1e-9))) if m else 0.0
        delivered = float(D * (w * throttle).sum())
        key = hash(tuple(tuple(p) for p in paths))
        if history and key == history[-1][0]:
            converged = True
            break
        if key in index:                       # oscillation: states index[key]..now
            cycle = history[index[key]:]
            break
        index[key] = len(history)
        history.append((key, ratio, delivered))
        t = np.where(load > cap, t0 * load / np.maximum(cap, 1e-9), t0)   # CLM update
    if cycle:
        ratio = max(c[1] for c in cycle)
        delivered = float(np.mean([c[2] for c in cycle]))
    unreachable = float(w[[not p for p in paths]].sum())
    return {"ratio": ratio, "converged": converged, "oscillating": bool(cycle),
            "iterations": it, "load": load, "unreachable": unreachable,
            "delivered": delivered}


def managed_throughput(g: ig.Graph, weights: dict, targets, upper: float, *,
                       capacity="capacity_vph", tol: float = 0.01):
    """Largest total demand D that a perfectly coordinated plan could route
    when origin i must send exactly D * w_i: feasible iff the max-flow with
    super-source arcs of capacity D * w_i saturates them all. This is the
    like-for-like bound for the self-routed readings (same origins, same
    split); plain community max-flow lets demand start anywhere and overstates
    it. Returns (D, binding_arcs): the real arcs in the min cut just above D,
    i.e. the roads that actually limit this evacuation."""
    d, sink, m = _with_sink(g, targets)
    cap = np.concatenate([np.asarray(d.es[capacity][:m], dtype=float),
                          np.full(d.ecount() - m, 1e12)])
    orig = np.fromiter(weights.keys(), dtype=int)
    w = np.fromiter(weights.values(), dtype=float)
    w = w / w.sum()
    d.add_vertices(1)
    src = d.vcount() - 1
    d.add_edges([(src, int(o)) for o in orig])

    def flow(D):
        return d.maxflow(src, sink, capacity=np.concatenate([cap, D * w]).tolist())

    lo, hi = 0.0, float(upper)
    if flow(hi).value >= hi * (1 - 1e-9):
        lo = hi
    else:
        while hi - lo > tol * upper:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if flow(mid).value >= mid * (1 - 1e-9) else (lo, mid)
    f = flow(max(hi, lo * (1 + 2 * tol)))
    binding = [e for e in f.cut if e < m]
    return lo, binding


def selfish_throughput(g: ig.Graph, weights: dict, targets, managed: float, *,
                       capacity="capacity_vph", time="travel_s", tol: float = 0.01,
                       max_iter: int = 60) -> dict:
    """Strict and rationed self-routed throughput (see module docstring)."""
    if managed <= 0 or not weights:
        return {"D_strict": 0.0, "rationed": 0.0, "converged": None}
    kw = dict(capacity=capacity, time=time, max_iter=max_iter)
    # strict: bisection on [0, managed]
    lo, hi, conv = 0.0, float(managed), None
    r = settle(g, weights, targets, hi, **kw)
    if r["ratio"] <= 1 and r["unreachable"] == 0:
        lo, conv = hi, r["converged"]
    else:
        while hi - lo > tol * managed:
            mid = (lo + hi) / 2
            r = settle(g, weights, targets, mid, **kw)
            if r["ratio"] <= 1 and r["unreachable"] == 0:
                lo, conv = mid, r["converged"]
            else:
                hi = mid
    # rationed: best delivered flow over a demand scan up to 3x managed
    best, best_conv = lo, conv
    for D in managed * np.geomspace(0.25, 3.0, 8):
        r = settle(g, weights, targets, D, **kw)
        if r["delivered"] > best:
            best, best_conv = r["delivered"], r["converged"]
    return {"D_strict": lo, "rationed": best, "converged": conv,
            "rationed_converged": best_conv}
