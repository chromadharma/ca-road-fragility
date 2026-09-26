"""Hazard layers and the road overlay.

A Hazard is either
  - polygons with an ORDINAL level field (CAL FIRE fire hazard zones: 1-3), or
  - a raster with CONTINUOUS values (flood depth, for Project 2) plus the bin
    edges that turn values into ordinal levels.

overlay() writes the same edge attributes whatever the kind:
    hazard_max        highest level the edge touches (0 = none)
    hazard_share_<k>  share of edge length at level k
so nothing downstream needs to know which kind it came from.
"""
from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd


@dataclass
class Hazard:
    kind: str                     # "polygon" | "raster"
    levels: dict                  # level int -> label, e.g. {1: "moderate", ...}
    gdf: gpd.GeoDataFrame | None = None   # polygon: columns level, geometry
    raster_path: str | None = None
    bins: list | None = None      # raster: value edges for levels 1..k
    sample_step_m: float = 25.0   # raster: spacing of samples along an edge


def load_hazard(src, *, kind: str = "polygon", field: str | None = None,
                levels: dict | None = None, bins=None, layer=None) -> Hazard:
    if kind == "polygon":
        gdf = src if isinstance(src, gpd.GeoDataFrame) else gpd.read_file(src, layer=layer)
        gdf = gdf[[field, "geometry"]].rename(columns={field: "level"})
        gdf["level"] = gdf["level"].astype(int)
        return Hazard(kind="polygon", levels=levels or {}, gdf=gdf)
    if kind == "raster":
        return Hazard(kind="raster", levels=levels or {}, raster_path=str(src),
                      bins=list(bins))
    raise ValueError(kind)


def _tile(polys: gpd.GeoDataFrame, tile_m: float) -> gpd.GeoDataFrame:
    import shapely
    xmin, ymin, xmax, ymax = polys.total_bounds
    xs = np.arange(xmin, xmax + tile_m, tile_m)
    ys = np.arange(ymin, ymax + tile_m, tile_m)
    out_geom, out_level = [], []
    for geom, lvl in zip(polys.geometry.values, polys["level"].values):
        gx0, gy0, gx1, gy1 = geom.bounds
        for x0 in xs[(xs + tile_m > gx0) & (xs < gx1)]:
            for y0 in ys[(ys + tile_m > gy0) & (ys < gy1)]:
                piece = shapely.clip_by_rect(geom, x0, y0, x0 + tile_m, y0 + tile_m)
                if not piece.is_empty:
                    out_geom.append(piece); out_level.append(lvl)
    return gpd.GeoDataFrame({"level": out_level}, geometry=out_geom, crs=polys.crs)


def _overlay_polygon(edges: gpd.GeoDataFrame, hz: Hazard, metric_crs: str,
                     tile_m: float = 2000.0) -> pd.DataFrame:
    e = edges[["geometry"]].to_crs(metric_crs).copy()
    e["eid"] = np.arange(len(e))
    e["len"] = e.length
    # Individual polygons, not a dissolve: a few huge multipolygons defeat the
    # spatial index and made this ~100x slower. Overlapping polygons of the
    # same level can double-count length; shares are clipped to 1 below.
    import shapely
    polys = hz.gdf.to_crs(metric_crs)[["level", "geometry"]].copy()
    polys["geometry"] = polys.geometry.make_valid()
    # Hazard polygons can carry 100k+ vertices, and every intersects/intersection
    # test against one is O(vertices). Cutting them into tiles first keeps each
    # test small; clip_by_rect is linear and exact for area inside the tile.
    polys = _tile(polys, tile_m)
    polys = polys.reset_index(drop=True)
    pairs = gpd.sjoin(e[["eid", "geometry"]], polys, predicate="intersects", how="inner")
    lines = e.geometry.values[pairs["eid"].values]
    shapes = polys.geometry.values[pairs["index_right"].values]
    pairs["ilen"] = shapely.length(shapely.intersection(lines, shapes))
    share = pairs.groupby(["eid", "level"])["ilen"].sum().unstack(fill_value=0.0)
    share = share.reindex(index=e["eid"], fill_value=0.0)
    share = share.div(e["len"].replace(0, np.nan).values, axis=0).fillna(0.0).clip(0, 1)
    return share


def _overlay_raster(edges: gpd.GeoDataFrame, hz: Hazard, metric_crs: str) -> pd.DataFrame:
    import rasterio
    with rasterio.open(hz.raster_path) as r:
        e = edges[["geometry"]].to_crs(metric_crs)
        rows = []
        for geom in e.geometry:
            n = max(2, int(geom.length // hz.sample_step_m) + 1)
            pts = [geom.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
            pts = gpd.GeoSeries(pts, crs=metric_crs).to_crs(r.crs)
            vals = np.array([v[0] for v in r.sample([(p.x, p.y) for p in pts])], float)
            if r.nodata is not None:
                vals[vals == r.nodata] = np.nan
            lvl = np.digitize(np.nan_to_num(vals, nan=-np.inf), hz.bins)  # 0 below first bin
            rows.append(np.bincount(lvl, minlength=len(hz.bins) + 1)[1:] / n)
    share = pd.DataFrame(rows, columns=range(1, len(hz.bins) + 1))
    return share


def overlay(rg, hz: Hazard, *, metric_crs: str):
    """Attach hazard attributes to rg.g's edges (rg.edges must hold geometry
    aligned with g.es). Returns rg for chaining."""
    if rg.edges is None:
        raise ValueError("overlay needs edge geometry (rg.edges)")
    share = _overlay_polygon(rg.edges, hz, metric_crs) if hz.kind == "polygon" \
        else _overlay_raster(rg.edges, hz, metric_crs)
    levels = sorted(set(hz.levels) | set(share.columns))
    share = share.reindex(columns=levels, fill_value=0.0)
    hmax = np.zeros(len(share), dtype=int)
    for k in levels:
        hmax = np.where(share[k].values > 0, k, hmax)
    rg.g.es["hazard_max"] = hmax.tolist()
    for k in levels:
        rg.g.es[f"hazard_share_{k}"] = share[k].values.tolist()
        rg.edges[f"hazard_share_{k}"] = share[k].values
    rg.edges["hazard_max"] = hmax
    return rg
