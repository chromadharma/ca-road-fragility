"""OSM road graphs via osmnx, converted to a directed igraph RoadGraph.

Carries the three Overpass fixes found on the rkk-gis pipeline (2026-09-20):
  1. identify as this project: gall.openstreetmap.de's Apache front end
     throttles the stock osmnx Referer that every osmnx user shares;
  2. cap osmnx's retry on 429/504, which otherwise recurses forever, silently;
  3. probe the Overpass backends and use one that answers, instead of letting
     osmnx pin whichever IP overpass-api.de resolved to.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import igraph as ig
import numpy as np
import osmnx as ox
import requests

from .roads import RoadGraph

log = logging.getLogger("hazardnet.osm")
UA = "hazardnet/0.1 (ca-road-fragility research; single sequential client)"
MAX_OVERPASS_RETRIES = 2


def configure(cache_dir: Path, logs_dir: Path) -> None:
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_dir)
    ox.settings.log_file = True
    ox.settings.logs_folder = str(logs_dir)
    ox.settings.log_console = False
    ox.settings.requests_timeout = 600
    ox.settings.http_user_agent = UA
    ox.settings.http_referer = UA
    ox.settings.overpass_url = _pick_overpass()

    import osmnx._overpass as _op
    orig = getattr(_op, "_ORIG_REQUEST", _op._overpass_request)
    _op._ORIG_REQUEST = orig

    def guarded(data):
        depth = getattr(guarded, "depth", 0)
        if depth > MAX_OVERPASS_RETRIES:
            raise RuntimeError(f"Overpass refused the query {depth} times (429/504)")
        guarded.depth = depth + 1
        try:
            return orig(data)
        finally:
            guarded.depth = depth
    _op._overpass_request = guarded


BACKENDS = ("https://gall.openstreetmap.de/api", "https://lambert.openstreetmap.de/api",
            "https://overpass-api.de/api")


def _pick_overpass(exclude=()) -> str:
    for base in [b for b in BACKENDS if b not in exclude]:
        try:
            if requests.get(base + "/status", timeout=20,
                            headers={"User-Agent": UA}).status_code == 200:
                log.info("Overpass endpoint: %s", base)
                return base
        except requests.RequestException:
            continue
    return "https://overpass-api.de/api"


def _first(v):
    return v[0] if isinstance(v, list) else v


def _lanes(v) -> float:
    """OSM lanes tag -> number, or nan. Handles lists (merged ways) and '2;3'."""
    vals = v if isinstance(v, list) else [v]
    nums = []
    for x in vals:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            continue
        nums += [float(t) for t in re.findall(r"\d+(?:\.\d+)?", str(x))]
    return min(nums) if nums else np.nan     # conservative: narrowest section


def load_osm(area, *, capacity_table: dict, network_type: str = "drive",
             max_query_km2: float | None = None, pbf: Path | None = None,
             work_dir: Path | None = None, extra: dict | None = None, **_) -> RoadGraph:
    """area: shapely polygon (EPSG:4326). capacity_table: {osm_class:
    {"per_lane_vph": float, "default_lanes_dir": float}} from the study
    config; classes not in the table fall back to its "default" entry."""
    if pbf is not None:
        # local extract instead of Overpass (see osm_pbf.py); drive filter only
        from .osm_pbf import graph_from_pbf
        G = graph_from_pbf(Path(pbf), area, Path(work_dir), extra=extra)
        rg = _finish(G, capacity_table, source=f"osm-pbf:{Path(pbf).name}")
        extra_cls = set(extra["highway"]) if extra else set()
        rg.g.es["is_extra"] = [c in extra_cls for c in rg.g.es["road_class"]]
        rg.edges["is_extra"] = rg.g.es["is_extra"]
        return rg
    if max_query_km2:
        # dense cities: osmnx's default ~2,500 km2 sub-queries time out (504)
        # on Overpass; smaller pieces each finish within the server's limit
        ox.settings.max_query_area_size = max_query_km2 * 1e6
    # A backend that is up can still 504 every query within seconds when it is
    # overloaded (lambert, 2026-09-25). After the retry cap trips, move to the
    # next backend. osmnx caches by full URL, so a switch re-fetches pieces
    # already fetched elsewhere; they are small.
    tried = []
    while True:
        try:
            G = ox.graph_from_polygon(area, network_type=network_type, simplify=True,
                                      retain_all=True)
            break
        except RuntimeError as e:
            tried.append(ox.settings.overpass_url)
            if len(tried) >= len(BACKENDS):
                raise
            ox.settings.overpass_url = _pick_overpass(exclude=tried)
            log.warning("%s; switching Overpass backend to %s", e, ox.settings.overpass_url)
    return _finish(G, capacity_table, source="osm")


def _finish(G, capacity_table: dict, source: str) -> RoadGraph:
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    nodes, edges = ox.graph_to_gdfs(G)
    edges = edges.reset_index()
    idx = {osmid: i for i, osmid in enumerate(nodes.index)}

    cls = edges["highway"].map(_first).fillna("unclassified")
    oneway = edges["oneway"].fillna(False).astype(bool)
    lanes_tot = edges["lanes"].map(_lanes) if "lanes" in edges else np.nan
    # two-way roads are two arcs in osmnx; each carries half the lanes
    lanes_dir = np.where(oneway, lanes_tot, np.floor(lanes_tot / 2))
    lanes_dir = np.where(lanes_dir < 1, 1, lanes_dir)       # a 1-lane 2-way road
    default = capacity_table["default"]
    per_lane = cls.map(lambda c: capacity_table.get(c, default)["per_lane_vph"])
    def_lanes = cls.map(lambda c: capacity_table.get(c, default)["default_lanes_dir"])
    imputed = np.isnan(lanes_tot)
    lanes_dir = np.where(imputed, def_lanes, lanes_dir)

    edges["road_class"] = cls
    edges["lanes_dir"] = lanes_dir
    edges["lanes_imputed"] = imputed
    edges["capacity_vph"] = lanes_dir * per_lane.values
    edges["length_m"] = edges["length"]
    edges["travel_s"] = edges["travel_time"]

    g = ig.Graph(n=len(nodes), directed=True,
                 edges=list(zip(edges["u"].map(idx), edges["v"].map(idx))))
    g.vs["osmid"] = nodes.index.tolist()
    g.vs["x"] = nodes["x"].tolist(); g.vs["y"] = nodes["y"].tolist()
    for a in ("road_class", "lanes_dir", "capacity_vph", "length_m", "travel_s"):
        g.es[a] = edges[a].tolist()
    g.es["lanes_imputed"] = edges["lanes_imputed"].astype(bool).tolist()
    keep = ["u", "v", "key", "osmid", "name", "ref", "road_class", "oneway",
            "lanes_dir", "lanes_imputed", "capacity_vph", "length_m", "travel_s", "geometry"]
    edges = edges[[c for c in keep if c in edges.columns]]
    return RoadGraph(g=g, source=source, crs="EPSG:4326", edges=edges,
                     meta={"share_lanes_imputed": float(imputed.mean()),
                           "n_nodes": len(nodes), "n_arcs": len(edges)})
