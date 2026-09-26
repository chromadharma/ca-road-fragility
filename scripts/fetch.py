"""Fetch raw data into data/raw/. Standard library only, so it runs before the
environment exists. Every source, URL and licence is listed in data/README.md.

    python scripts/fetch.py part_a          # SNAP + DIMACS (~62 MB)
    python scripts/fetch.py census          # TIGER places + PL 94-171 + blocks (~470 MB)
    python scripts/fetch.py osm             # Geofabrik SoCal extract for LA (~670 MB)
    python scripts/fetch.py hazard          # CAL FIRE hazard zones + fire perimeters (REST)
    python scripts/fetch.py all

Files already present with the expected size are skipped.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
UA = {"User-Agent": "ca-road-fragility/0.1 (research)"}

FILES = {
    "part_a": {
        "snap/roadNet-CA.txt.gz": "https://snap.stanford.edu/data/roadNet-CA.txt.gz",
        "dimacs/USA-road-d.CAL.gr.gz":
            "http://www.diag.uniroma1.it/challenge9/data/USA-road-d/USA-road-d.CAL.gr.gz",
        "dimacs/USA-road-d.CAL.co.gz":
            "http://www.diag.uniroma1.it/challenge9/data/USA-road-d/USA-road-d.CAL.co.gz",
        # state outline, to clip Nevada out of DIMACS CAL
        "tiger/cb_2024_us_state_500k.zip":
            "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip",
    },
    "osm": {   # LA roads (Overpass fallback), ~670 MB
        "osm/socal-latest.osm.pbf":
            "https://download.geofabrik.de/north-america/us/california/socal-latest.osm.pbf",
    },
    "census": {
        "tiger/cb_2024_us_county_500k.zip":
            "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip",
        "tiger/tl_2024_06_place.zip":
            "https://www2.census.gov/geo/tiger/TIGER2024/PLACE/tl_2024_06_place.zip",
        "tiger/tl_2020_06_tabblock20.zip":
            "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_06_tabblock20.zip",
        "census/ca2020.pl.zip":
            "https://www2.census.gov/programs-surveys/decennial/2020/data/"
            "01-Redistricting_File--PL_94-171/California/ca2020.pl.zip",
    },
}

AGOL = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services"
LAYERS = {   # ArcGIS FeatureServer layers pulled page by page as GeoJSON
    "hazard": {
        "calfire/fhsz_sra_2024.geojson": f"{AGOL}/FHSZSRA_23_3/FeatureServer/0",
        "calfire/fhsz_lra_2025.geojson": f"{AGOL}/FHSALRA25_v1_All/FeatureServer/0",
        "calfire/fire_perimeters_firep25_1.geojson":
            f"{AGOL}/California_Historic_Fire_Perimeters/FeatureServer/0",
        "la/csa_communities.geojson":
            "https://public.gis.lacounty.gov/public/rest/services/"
            "LACounty_Dynamic/Political_Boundaries/MapServer/23",
    },
}


def _get(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        size = int(r.headers.get("Content-Length") or 0)
        if dest.exists() and size and dest.stat().st_size == size:
            print(f"  have {dest.relative_to(RAW)}")
            return
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    tmp.replace(dest)
    print(f"  got  {dest.relative_to(RAW)} ({dest.stat().st_size/1e6:.1f} MB)")


def _layer(url: str, dest: Path, page: int = 250) -> None:
    """Page through an ArcGIS layer by objectid and write one GeoJSON file."""
    if dest.exists():
        print(f"  have {dest.relative_to(RAW)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)

    def q(params):
        full = url + "/query?" + urllib.parse.urlencode({**params, "f": "json"})
        with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=300) as r:
            return json.load(r)

    ids = sorted(q({"where": "1=1", "returnIdsOnly": "true"})["objectIds"])
    feats = []
    for i in range(0, len(ids), page):
        chunk = ids[i:i + page]
        for attempt in range(4):
            try:
                # POST: 1,000 ids in a GET query string is too long (HTTP 404)
                body = urllib.parse.urlencode({
                    "objectIds": ",".join(map(str, chunk)), "outFields": "*",
                    "outSR": 4326, "f": "geojson"}).encode()
                with urllib.request.urlopen(urllib.request.Request(
                        url + "/query", data=body, headers=UA), timeout=300) as r:
                    feats += json.load(r)["features"]
                break
            except Exception as e:                       # noqa: BLE001
                if attempt == 3:
                    raise
                print(f"    retry {attempt+1} ({e})"); time.sleep(10 * (attempt + 1))
        print(f"    {dest.name}: {len(feats)}/{len(ids)}", end="\r")
    if len(feats) != len(ids):
        raise RuntimeError(f"{dest.name}: got {len(feats)} of {len(ids)} features")
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"  got  {dest.relative_to(RAW)} ({len(feats)} features)          ")


def main(which: str) -> None:
    groups = list(FILES) + list(LAYERS) if which == "all" else [which]
    for grp in groups:
        print(f"[{grp}]")
        for rel, url in FILES.get(grp, {}).items():
            _get(url, RAW / rel)
        for rel, url in LAYERS.get(grp, {}).items():
            _layer(url, RAW / rel)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
