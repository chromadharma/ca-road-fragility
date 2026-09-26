"""Road graphs: one container, three loaders (plain edge list, DIMACS, OSM).

Everything downstream works on `RoadGraph.g`, an igraph Graph. Edge attributes
the engine understands (all optional except where a measure needs them):

    length_m      edge length in metres
    travel_s      free-flow travel time in seconds
    capacity_vph  vehicles per hour the edge can carry
    road_class    OSM highway class, or None
    hazard_*      written by overlay()

No study-specific values live here: capacities per road class, for example,
are passed in by the study config.
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path

import igraph as ig
import numpy as np


@dataclass
class RoadGraph:
    g: ig.Graph
    source: str
    crs: str | None = None          # CRS of node x/y and edge geometry, if any
    edges: object | None = None     # GeoDataFrame aligned to g.es by row, if any
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return self.g.vcount()

    @property
    def m(self) -> int:
        return self.g.ecount()


def _open(path: Path):
    return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)


def _undirected_unique(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Collapse a directed pair list (each road listed both ways) to unique
    undirected pairs with no self-loops."""
    a, b = np.minimum(u, v), np.maximum(u, v)
    keep = a != b
    pairs = np.unique(np.stack([a[keep], b[keep]], axis=1), axis=0)
    return pairs


def load_edgelist(path: Path) -> RoadGraph:
    """SNAP-style whitespace edge list, '#' comments. Node ids are relabelled
    to 0..n-1; the original id is kept as vertex attribute 'orig_id'."""
    arr = np.loadtxt(path, comments="#", dtype=np.int64)
    pairs = _undirected_unique(arr[:, 0], arr[:, 1])
    ids, inv = np.unique(pairs, return_inverse=True)
    g = ig.Graph(n=len(ids), edges=inv.reshape(-1, 2).tolist(), directed=False)
    g.vs["orig_id"] = ids.tolist()
    return RoadGraph(g=g, source=f"edgelist:{Path(path).name}",
                     meta={"raw_lines": int(arr.shape[0])})


def load_dimacs(gr_path: Path, co_path: Path) -> RoadGraph:
    """9th DIMACS Challenge .gr (arcs 'a u v w') + .co (nodes 'v id x y',
    x/y in millionths of a degree). Arcs come in both directions; they are
    collapsed to undirected edges keeping the smaller weight. The weight's unit
    is not documented on the download page, so it is stored as 'w_raw' and
    never treated as metres."""
    us, vs, ws = [], [], []
    with _open(gr_path) as f:
        for line in f:
            if line.startswith("a "):
                _, u, v, w = line.split()
                us.append(int(u)); vs.append(int(v)); ws.append(int(w))
    u = np.asarray(us, dtype=np.int64); v = np.asarray(vs, dtype=np.int64)
    w = np.asarray(ws, dtype=np.int64)
    a, b = np.minimum(u, v), np.maximum(u, v)
    keep = a != b
    a, b, w = a[keep], b[keep], w[keep]
    order = np.lexsort((w, b, a))
    a, b, w = a[order], b[order], w[order]
    first = np.ones(len(a), dtype=bool)
    first[1:] = (a[1:] != a[:-1]) | (b[1:] != b[:-1])
    a, b, w = a[first], b[first], w[first]

    xs, ys = {}, {}
    with _open(co_path) as f:
        for line in f:
            if line.startswith("v "):
                _, i, x, y = line.split()
                xs[int(i)] = int(x) / 1e6
                ys[int(i)] = int(y) / 1e6
    n = max(xs)                          # DIMACS ids are 1..n
    g = ig.Graph(n=n, edges=np.stack([a - 1, b - 1], axis=1).tolist(), directed=False)
    g.vs["x"] = [xs.get(i + 1, np.nan) for i in range(n)]
    g.vs["y"] = [ys.get(i + 1, np.nan) for i in range(n)]
    g.es["w_raw"] = w.tolist()
    return RoadGraph(g=g, source=f"dimacs:{Path(gr_path).name}", crs="EPSG:4326",
                     meta={"raw_arcs": int(len(us))})


def load_roads(area=None, source: str = "osm", **kw) -> RoadGraph:
    """Single entry point.

    source="edgelist": kw path=
    source="dimacs":   kw gr=, co=
    source="osm":      area = shapely polygon in EPSG:4326; kw see hazardnet.osm
    """
    if source == "edgelist":
        return load_edgelist(Path(kw["path"]))
    if source == "dimacs":
        return load_dimacs(Path(kw["gr"]), Path(kw["co"]))
    if source == "osm":
        from .osm import load_osm
        return load_osm(area, **kw)
    raise ValueError(f"unknown source {source!r}")


def contract_degree2(rg: RoadGraph) -> RoadGraph:
    """Series reduction: replace every chain of degree-2 vertices with one edge
    between the chain's two end junctions, then drop duplicate edges and
    self-loops. Repeats until no degree-2 vertex is left (collapsing duplicates
    can create new ones). Degree-2 vertices are often shape points tracing a
    road's curve, not junctions, and removing one cuts the road. So removal
    experiments that count "junctions" depend on how many such points a graph
    was built with. Undirected graphs only; vertex attribute 'orig_index'
    records each kept vertex's index in the input graph."""
    g = rg.g.copy()
    g.vs["orig_index"] = list(range(g.vcount()))
    rounds = 0
    while True:
        deg = np.asarray(g.degree())
        two = np.flatnonzero(deg == 2)
        if len(two) == 0:
            break
        rounds += 1
        is2 = np.zeros(g.vcount(), bool); is2[two] = True
        sub = g.induced_subgraph(two.tolist())
        comp = np.asarray(sub.connected_components().membership)
        # each chain touches up to two outside vertices; link them
        ends = {}
        for e in g.es:
            a, b = e.tuple
            for x, y in ((a, b), (b, a)):
                if is2[x] and not is2[y]:
                    ends.setdefault(comp[np.searchsorted(two, x)], []).append(y)
        new = [tuple(v) for v in ends.values() if len(v) == 2 and v[0] != v[1]]
        g.add_edges(new)
        g.delete_vertices(two.tolist())
        g.simplify(multiple=True, loops=True)
    return RoadGraph(g=g, source=rg.source + ":contracted", crs=rg.crs,
                     meta={**rg.meta, "contract_rounds": rounds,
                           "contracted_n": g.vcount(), "contracted_m": g.ecount()})


def clip_to_polygon(rg: RoadGraph, polygon) -> RoadGraph:
    """Keep vertices whose x/y fall inside `polygon` (same CRS as the vertex
    coordinates), e.g. to drop Nevada from DIMACS CAL. A bounding box would not
    do: Nevada lies inside California's box."""
    import shapely
    x = np.asarray(rg.g.vs["x"]); y = np.asarray(rg.g.vs["y"])
    inside = shapely.contains_xy(polygon, x, y)
    keep = np.flatnonzero(inside)
    sub = rg.g.induced_subgraph(keep.tolist(), implementation="create_from_scratch")
    return RoadGraph(g=sub, source=rg.source + ":clipped", crs=rg.crs,
                     meta={**rg.meta, "clip_kept": int(len(keep)),
                           "clip_dropped": int(rg.n - len(keep))})
