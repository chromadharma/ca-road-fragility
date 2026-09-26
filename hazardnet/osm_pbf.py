"""OSM road graph from a local .osm.pbf extract, no Overpass.

Fallback for when the Overpass servers are unreliable (2026-09-25: gall
unreachable, lambert 504 on every query). Selects ways with the SAME filter
osmnx's network_type="drive" sends to Overpass (copied from the query osmnx
logged for the Butte pull), writes them to a small .osm file, and builds the
graph with osmnx itself, so downstream code sees an identical structure:
build -> truncate to the polygon -> simplify, the order graph_from_polygon uses.
"""
from __future__ import annotations

import re
from pathlib import Path

import osmium
import osmnx as ox
import shapely

# osmnx 2.1.1 "drive" filter, as logged in the Overpass query
_HWY_EXCLUDE = re.compile(
    r"abandoned|bridleway|bus_guideway|construction|corridor|cycleway|elevator|escalator|"
    r"footway|no|path|pedestrian|planned|platform|proposed|raceway|razed|rest_area|"
    r"service|services|steps|track")
_SERVICE_EXCLUDE = re.compile(r"alley|driveway|emergency_access|parking|parking_aisle|private")


def drive_ok(tags) -> bool:
    """Overpass regex semantics (`!~` = does not match anywhere in the value)."""
    h = tags.get("highway")
    if h is None or _HWY_EXCLUDE.search(h):
        return False
    if re.search("yes", tags.get("area", "")) or re.search("private", tags.get("access", "")):
        return False
    if re.search("no", tags.get("motor_vehicle", "")) or re.search("no", tags.get("motorcar", "")):
        return False
    return not _SERVICE_EXCLUDE.search(tags.get("service", ""))


def extra_ok(tags, extra: dict) -> bool:
    """Roads the drive filter drops but an emergency could use (fire roads,
    gated service roads). Access tags are ignored on purpose: a locked gate can
    be opened in an evacuation; that is the question being asked."""
    h = tags.get("highway")
    if h not in extra["highway"] or re.search("yes", tags.get("area", "")):
        return False
    if tags.get("service", "") in extra.get("exclude_service", []):
        return False
    return tags.get("tracktype", "") not in extra.get("exclude_tracktype", [])


def extract_xml(pbf: Path, polygon, out: Path, extra: dict | None = None) -> Path:
    """Write the drive ways touching `polygon` (EPSG:4326), with all their
    nodes, to an .osm XML file osmnx can read.

    Filtering happens in pyosmium's C++ layer: nodes only fill the location
    cache and are never handed to Python, and only ways with a highway tag
    reach the loop. BackReferenceWriter then adds each selected way's nodes
    from the source file itself. A plain Python loop over every object in the
    SoCal extract took over 10 minutes and was abandoned."""
    shapely.prepare(polygon)
    minx, miny, maxx, maxy = polygon.bounds
    fp = (osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY)
          .with_locations()
          .with_filter(osmium.filter.EntityFilter(osmium.osm.WAY))
          .with_filter(osmium.filter.KeyFilter("highway")))
    n_sel = n_bad = 0
    with osmium.BackReferenceWriter(str(out), ref_src=str(pbf), overwrite=True) as wr:
        for w in fp:
            if not (drive_ok(w.tags) or (extra and extra_ok(w.tags, extra))):
                continue
            try:
                xs = [n.lon for n in w.nodes]; ys = [n.lat for n in w.nodes]
            except osmium.InvalidLocationError:
                n_bad += 1
                continue
            if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
                continue
            if shapely.intersects_xy(polygon, xs, ys).any():
                wr.add_way(w)
                n_sel += 1
    if n_sel == 0:
        raise RuntimeError(f"no drive ways selected ({n_bad} ways lacked node locations)")
    return out


def graph_from_pbf(pbf: Path, polygon, work: Path, extra: dict | None = None):
    xml = extract_xml(pbf, polygon, work / ("extended_extract.osm" if extra else "drive_extract.osm"),
                      extra=extra)
    G = ox.graph_from_xml(xml, simplify=False, retain_all=True)
    G = ox.truncate.truncate_graph_polygon(G, polygon, truncate_by_edge=False)
    return ox.simplify_graph(G)
