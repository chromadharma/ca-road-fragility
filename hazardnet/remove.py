"""Remove elements, then measure. One loop serves both parts of the study:

- Part A: remove NODES in a ranked order at increasing fractions
  (random / degree / betweenness) and record a curve.
- Part B: remove the EDGES a mask selects (e.g. hazard_max >= very high) once,
  and compare a measure before and after.

A measure is any callable `measure(g, kept) -> dict`, where `kept` maps the
new graph's vertex index -> original vertex index (identity for edge removal).
"""
from __future__ import annotations

from typing import Callable

import igraph as ig
import numpy as np
import pandas as pd

from .roads import RoadGraph

Measure = Callable[[ig.Graph, np.ndarray], dict]


def _drop_nodes(g: ig.Graph, removed: np.ndarray) -> tuple[ig.Graph, np.ndarray]:
    keep = np.setdiff1d(np.arange(g.vcount()), removed, assume_unique=False)
    return g.induced_subgraph(keep.tolist(), implementation="create_from_scratch"), keep


def _drop_edges(g: ig.Graph, removed: np.ndarray) -> ig.Graph:
    h = g.copy()
    h.delete_edges(removed.tolist())
    return h


def remove_and_measure(rg: RoadGraph, measure: Measure, *, mask=None,
                       ranking=None, fractions=None, element: str = "node",
                       progress: Callable[[str], None] | None = None):
    """Mask mode (`mask` given): returns {"before": {...}, "after": {...}}.
    Curve mode (`ranking` + `fractions`): returns a DataFrame, one row per
    fraction, with the measure's keys as columns."""
    g = rg.g
    ident = np.arange(g.vcount())

    if mask is not None:
        mask = np.asarray(mask, dtype=bool)
        idx = np.flatnonzero(mask)
        before = measure(g, ident)
        if element == "edge":
            after = measure(_drop_edges(g, idx), ident)
        else:
            h, kept = _drop_nodes(g, idx)
            after = measure(h, kept)
        return {"before": before, "after": after, "n_removed": int(len(idx))}

    if ranking is None or fractions is None:
        raise ValueError("give either mask=, or ranking= and fractions=")
    ranking = np.asarray(ranking)
    total = g.vcount() if element == "node" else g.ecount()
    rows = []
    for f in fractions:
        k = int(round(f * total))
        removed = ranking[:k]
        if element == "edge":
            row = measure(_drop_edges(g, removed), ident)
        else:
            h, kept = _drop_nodes(g, removed)
            row = measure(h, kept)
        rows.append({"fraction": float(f), "n_removed": k, **row})
        if progress:
            progress(f"f={f:.3f} " + " ".join(f"{a}={b:.4g}" for a, b in row.items()))
    return pd.DataFrame(rows)


def map_to_kept(original_idx: np.ndarray, kept: np.ndarray) -> np.ndarray:
    """Original vertex indices -> indices in the reduced graph (-1 if gone).
    `kept` is sorted (as produced by _drop_nodes)."""
    pos = np.searchsorted(kept, original_idx)
    pos = np.clip(pos, 0, len(kept) - 1)
    ok = kept[pos] == original_idx
    return np.where(ok, pos, -1)
