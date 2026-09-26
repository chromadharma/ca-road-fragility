"""Network-wide measures used by removal experiments.

Efficiency follows Latora & Marchiori (2001): E = mean over ordered pairs of
1/d(i,j), with 1/inf = 0, so disconnection counts as zero instead of breaking
the average. Here it is normalised by the ORIGINAL node count, so removed
nodes contribute zero too and curves under removal are comparable.
"""
from __future__ import annotations

import igraph as ig
import numpy as np


def component_sizes(g: ig.Graph) -> np.ndarray:
    """Sizes of connected components, largest first."""
    if g.vcount() == 0:
        return np.array([0, 0])
    s = np.sort(np.asarray(g.connected_components(mode="weak").sizes()))[::-1]
    return s if len(s) > 1 else np.append(s, 0)


def efficiency_sampled(g: ig.Graph, n_original: int, sources: np.ndarray,
                       weights: str | None = None) -> float:
    """Unbiased estimate of global efficiency from shortest paths out of a
    fixed sample of source vertices. `sources` are indices into g (already
    mapped from the original graph by the caller); a source that has been
    removed is passed as -1 and contributes 0."""
    total = 0.0
    live = sources[sources >= 0]
    for s in live:
        d = np.asarray(g.distances(source=[int(s)], weights=weights)[0], dtype=float)
        d = d[np.isfinite(d) & (d > 0)]
        total += (1.0 / d).sum()
    # every sampled source counts in the denominator, removed ones as zero
    return total / (len(sources) * (n_original - 1))


def betweenness_sampled(g: ig.Graph, k: int, seed: int = 0,
                        weights: str | None = None) -> np.ndarray:
    """Vertex betweenness from shortest paths out of k random sources to all
    targets, rescaled by n/k. Exact betweenness is infeasible at 2M nodes; for
    RANKING vertices the sample estimate is what matters."""
    rng = np.random.default_rng(seed)
    src = rng.choice(g.vcount(), size=min(k, g.vcount()), replace=False)
    b = np.asarray(g.betweenness(sources=src.tolist(), targets=None,
                                 weights=weights, directed=False), dtype=float)
    return b * (g.vcount() / len(src))
